"""
Tools exposed to the discovery agent.

Each tool is an async function with a docstring and type hints; DSPy derives the
tool schema from them, so closed sets of values are ``Literal`` types (rendered as
enums) rather than free strings. Tools return compact JSON so long trajectories
stay within the context window, and they never raise for user-level mistakes:
errors come back as text the agent can react to.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.services.discovery.expression import ALLOWED_FUNCTIONS, ExpressionError
from backend.services.discovery.session import (
    ALLOWED_BINARY,
    ALLOWED_UNARY,
    NOTE_KINDS,
    SINDY_FUNCTIONS,
    BudgetExhausted,
    DiscoverySession,
)

logger = logging.getLogger(__name__)

MAX_OBSERVATION_CHARS = 4000

TargetTransform = Literal["none", "log", "log1p", "sqrt"]
UnaryOp = Literal[ALLOWED_UNARY]
BinaryOp = Literal[ALLOWED_BINARY]
NoteKind = Literal[NOTE_KINDS]
SindyFunction = Literal[SINDY_FUNCTIONS]
Problem = Literal["static", "dynamic"]


class NoteEntry(BaseModel):
    kind: NoteKind
    text: str = Field(description="The finding, specific and with numbers")
    model_ids: list[str] = Field(default_factory=list, description="Model ids this rests on")


def _dump(obj: Any) -> str:
    text = json.dumps(obj, default=str, separators=(",", ":"))
    if len(text) > MAX_OBSERVATION_CHARS:
        text = text[:MAX_OBSERVATION_CHARS] + "...(truncated)"
    return text


def _transform(value: str | None) -> str | None:
    return None if value in (None, "", "none", "None") else value


def build_tools(
    session: DiscoverySession,
) -> list[Callable[..., Awaitable[str]]]:
    """
    Create the tool functions bound to ``session``.

    Rate-law tools (set_dynamics, fit_ode, start_sindy_search) work once the agent
    confirms that the rows are measurements over time.

    Exploration is blind to existing knowledge: there is no tool for the classic
    catalog or the literature, so the agent derives its forms from the data. Known
    laws are fitted and compared afterwards (``relate.py``).
    """

    async def guarded(name: str, fn: Callable[[], Awaitable[Any]]) -> str:
        try:
            session.check_budget()
            return _dump(await fn())
        except BudgetExhausted as e:
            return f"BUDGET EXHAUSTED ({e}). Call finish now and write the report."
        except (ValueError, ExpressionError) as e:
            return f"Error: {e}"
        except Exception as e:
            logger.warning(f"Discovery tool {name} failed: {e}", exc_info=True)
            return f"Error: {type(e).__name__}: {e}"

    # ------------------------------------------------------------------ data

    async def describe_data() -> str:
        """Full per-feature table (DATA_OVERVIEW is a summary of it): ranges, positivity, kind
        (continuous or categorical code), Pearson/Spearman correlation with the target, mutual
        information, permutation importance, SHAP share, collinear pairs, the noise ceiling and
        SHAP interactions/partial-effect shapes."""

        async def run():
            return await session.ensure_profile()

        return await guarded("describe_data", run)

    async def profile_shape(feature: str) -> str:
        """Shape of the target along one feature (alias): binned target means (marginal shape)
        and, when available, the SHAP partial effect (shape with the other features accounted
        for — prefer it when features are correlated). Labels such as 'saturating increasing',
        'peaked', 'sigmoidal' or 'roughly linear' describe the curve, not a model to use. For
        categorical codes it returns the mean of the target per level."""

        async def run():
            out = await asyncio.to_thread(session.shape, feature)
            label = out.get("shape") or out.get("note", "")
            await session.emit("tool", f"Shape of target vs {feature}: {label}")
            return out

        return await guarded("profile_shape", run)

    # --------------------------------------------------------------- fitting

    async def fit_formula(
        expression: str,
        label: str = "",
        initial_params: dict[str, float] | None = None,
        target_transform: TargetTransform = "none",
    ) -> str:
        """Fit your own formula. Use feature aliases exactly (case-sensitive) as variables; every
        other identifier is a free parameter (max 12) fitted by least squares — an identifier that
        looks like a misspelled alias is rejected. Allowed: + - * / ^, numbers, the constants pi and
        e (Euler's number, never a parameter name), and functions {functions}. Categorical codes may
        only appear as level(x, k) indicators.
        With target_transform, the expression models the TRANSFORMED target (e.g. 'log' means
        log(y) = expression) and predictions are back-transformed, so do not wrap it in exp().
        Example: 'a + b*x1^c * exp(d*x2)'. Give initial_params for nonlinear parameters when you
        can (default 1.0). Returns cross-validated R2 with its standard error, a verdict (good /
        adequate / poor / no_signal / failed) and the diagnosed reasons the form falls short."""

        async def run():
            m = await asyncio.to_thread(
                session.fit_custom, expression, initial_params, _transform(target_transform), label
            )
            if m.error:
                await session.emit("fit", f"Formula {label or expression[:60]} failed: {m.error}")
            else:
                cv = f"{m.cv_r2:.3f}" if m.cv_r2 is not None else "n/a"
                await session.emit(
                    "fit",
                    f"Fitted {label or 'formula'} {m.fitted_expression[:80]} ({m.model_id}, CV R2 {cv})",
                    **m.event_fields(),
                )
            return m.brief() | {"parameters": list(m.params)}

        return await guarded("fit_formula", run)

    async def inspect_model(model_id: str) -> str:
        """Full details of a fitted model: parameters with standard errors, all diagnostics
        (shape misfit per feature, missing variables, heteroscedasticity, weak or non-significant
        parameters, outliers, gap to the noise ceiling) and every diagnosed reason."""

        async def run():
            m = session.models.get(model_id)
            if m is None:
                raise ValueError(f"Unknown model_id {model_id!r}")
            d = m.brief()
            d["params"] = {k: float(f"{v:.5g}") for k, v in m.params.items()}
            d["param_se"] = {
                k: (float(f"{v:.3g}") if v is not None else None) for k, v in m.param_se.items()
            }
            d["train_r2"] = m.train_r2 and round(m.train_r2, 4)
            d["diagnostics"] = m.diagnostics
            d["reasons"] = m.reasons
            if m.target_transform:
                d["transformed_space_expression"] = m.fitted_core
            if m.problem == "dynamic":
                d["rate"] = f"{session.dynamics.rate} = {m.fitted_expression}"
            return d

        return await guarded("inspect_model", run)

    async def leaderboard(top: int = 10, problem: Problem = "static") -> str:
        """Fitted models ranked by cross-validated R2, with the standard error used to decide
        ties. problem='static': your formulas and PySR equations for the target. problem='dynamic':
        rate laws (fit_ode and SINDy), ranked by CV R2 on the derivative, with simulation R2."""

        async def run():
            ceiling = session._space(problem)[1].ceiling_r2
            return {
                "noise_ceiling_r2": ceiling and round(ceiling, 4),
                "models": session.leaderboard(top=min(max(top, 1), 30), problem=problem),
            }

        return await guarded("leaderboard", run)

    # ------------------------------------------------------------------ PySR

    async def start_pysr_search(
        features: list[str],
        unary_operators: list[UnaryOp],
        binary_operators: list[BinaryOp],
        maxsize: int = 20,
        niterations: int | None = None,
        target_transform: TargetTransform = "none",
        guesses: list[str] | None = None,
        guess_model_ids: list[str] | None = None,
        rationale: str = "",
        template: str | None = None,
    ) -> str:
        """Launch a PySR symbolic-regression search on the HPC cluster (non-blocking; queue + run
        take minutes). Returns a search_id. Keep fitting your own formulas meanwhile.
        maxsize 7-40 (complexity cap). niterations 50-5000 or null for auto.
        Seeds: guess_model_ids takes ids of your best fits (resolved in the right target space);
        guesses takes up to 5 closed formulas with numeric constants. Without seeds, the strongest
        SHAP interaction among the features seeds the search (a*b, a/b). A seed using an operator you
        did not enable is rejected (the reply lists rejected seeds and why). Restrict features to
        the ones your diagnostics say matter, pick operators matching the shapes you found, and
        explain the purpose in rationale.
        template fixes the structure and lets PySR search each part: subexpressions called on
        features and combined with + - * / and numbers, e.g. "f(CO2, Tm) + g(PDSI_l1, NAO_l2)"
        (current drivers plus a separate memory term) or "f(T) * g(W)" (multiplicative
        limitation). Every feature must go to some subexpression; seeds are dropped. Its
        equations come back as one formula and are scored like any other."""

        async def run():
            record = await session.start_search(
                features=features,
                unary_operators=list(unary_operators),
                binary_operators=list(binary_operators),
                maxsize=maxsize,
                niterations=niterations,
                target_transform=_transform(target_transform),
                guesses=guesses or [],
                guess_model_ids=guess_model_ids or [],
                rationale=rationale,
                template=template,
            )
            out = {
                "search_id": record.search_id,
                "config": record.config,
                "accepted_guesses": record.guesses,
                "rejected_guesses": record.rejected_guesses,
                "budget": session.budget_status(),
            }
            if record.seeded_from_shap:
                out["seeded_from_shap"] = True
            weak = session.weak_features(features)
            if weak:
                out["weak_features"] = (
                    f"{weak} carry a negligible SHAP share and no permutation importance; they "
                    "enlarge the search space without signal (drop them unless diagnostics flag them)"
                )
            return out

        return await guarded("start_pysr_search", run)

    async def search_status() -> str:
        """Status of all searches, PySR and SINDy (queued / ingesting / completed / failed / cancelled; an upper
        bound on when each will be done) and the remaining budget."""

        async def run():
            return {
                "searches": [s.summary(session.models) for s in session.searches.values()],
                "budget": session.budget_status(),
            }

        return await guarded("search_status", run)

    async def wait_for_searches(
        search_ids: list[str] | None = None, max_wait_minutes: float | None = None
    ) -> str:
        """Block until ANY of the given searches (default: all running) finishes, or
        max_wait_minutes passes (default: as long as the budget allows). Use it only when you have
        nothing useful left to fit. Returns the finished searches; then read them with search_results."""

        async def run():
            cap = (max_wait_minutes * 60) if max_wait_minutes else session.remaining_s
            await session.emit("wait", "Waiting for symbolic regression results")
            finished = await session.wait_any(search_ids, cap)
            return {
                "finished": [s.summary(session.models) for s in finished],
                "still_running": [s.search_id for s in session.searches.values() if not s.done],
                "next": "call search_results(search_id) for each completed search",
            }

        return await guarded("wait_for_searches", run)

    async def cancel_search(search_id: str) -> str:
        """Cancel a running search (frees a slot for a better-targeted one)."""

        async def run():
            record = await session.cancel_search(search_id)
            return record.summary(session.models)

        return await guarded("cancel_search", run)

    async def search_results(search_id: str, top: int = 8) -> str:
        """Equations found by a completed search, re-scored like your formulas (constants
        refit in cross-validation): Pareto front of complexity vs error with CV R2, verdicts and
        reasons (for SINDy: rate laws, CV R2 on the derivative, simulation R2 where simulated).
        Reading a search marks it as reviewed."""

        async def run():
            record = session._get_search(search_id)
            if record.status != "completed":
                return record.summary(session.models)
            session.mark_read(search_id)
            models = [session.models[m] for m in record.model_ids if m in session.models]
            front = session.pareto([m for m in models if not m.error])
            return {
                "search": record.summary(session.models),
                "pareto_front": [m.brief() for m in front[: min(max(top, 1), 15)]],
            }

        return await guarded("search_results", run)

    # -------------------------------------------------------------- dynamics

    async def describe_time_structure() -> str:
        """Whether the rows are measurements over time: the detected time column, trajectory
        column (sample, jar, plot...), number of trajectories, points per trajectory, how smoothly
        the target changes along time (evidence) and alternative candidates. For a long series
        (regime "series") also the lagged features added to the data, the screening of every
        candidate lag (gain = drop of the CV error) and the residual autocorrelation with and
        without them. Detection is a proposal; confirm rate-law discovery with set_dynamics."""

        async def run():
            ts = session.time_structure
            return {
                "detected": ts.to_dict() if ts and ts.time_column else None,
                "series": session.series,
                "confirmed": session.dynamics.summary() if session.dynamics else None,
                "note": "A smooth curve along a column that is not time-like is just a static "
                "shape; treat the data as dynamics only when the column really is time.",
            }

        return await guarded("describe_time_structure", run)

    async def set_dynamics(time_column: str, group_column: str | None = None) -> str:
        """Confirm that the rows are measurements over time and set up rate-law discovery:
        d(target)/dt is estimated per trajectory by local smoothing, and the other continuous
        features become inputs of the rate law. group_column separates trajectories (null for
        a single series). Columns may be original names or aliases. Required before fit_ode and
        start_sindy_search; calling it again replaces the setup."""

        async def run():
            dyn = await asyncio.to_thread(session.set_dynamics, time_column, group_column)
            await session.emit(
                "tool",
                f"Dynamics: {dyn.n_trajectories} trajectories along {dyn.structure.time_column}",
            )
            return dyn.summary()

        return await guarded("set_dynamics", run)

    async def fit_ode(
        expression: str, label: str = "", initial_params: dict[str, float] | None = None
    ) -> str:
        """Fit your own rate law: expression is the right-hand side of d(target)/dt, using the
        target alias as the state and the input aliases from set_dynamics; other identifiers are
        free parameters (max 12). Example: 'k*(a - y)' or 'r*y*(1 - y/K)'. Returns CV R2 on the
        derivative, the simulation R2 (the law integrated from each training trajectory's start
        and compared with the measured target) and the diagnosed reasons."""

        async def run():
            m = await asyncio.to_thread(
                session.fit_custom, expression, initial_params, None, label, problem="dynamic"
            )
            if m.error:
                await session.emit("fit", f"Rate law {label or expression[:60]} failed: {m.error}")
            else:
                cv = f"{m.cv_r2:.3f}" if m.cv_r2 is not None else "n/a"
                await session.emit(
                    "fit",
                    f"Fitted rate law {label or ''} d/dt = {m.fitted_expression[:80]} "
                    f"({m.model_id}, dydt CV R2 {cv}, simulation R2 {m.simulation.get('r2')})",
                    **m.event_fields(),
                )
            return m.brief() | {"parameters": list(m.params)}

        return await guarded("fit_ode", run)

    async def start_sindy_search(
        features: list[str],
        degree: int = 2,
        extra_functions: list[SindyFunction] | None = None,
        include_state: bool = True,
        rationale: str = "",
    ) -> str:
        """Launch a SINDy search (sparse regression over a library of candidate terms) for the
        rate law d(target)/dt. Fast (seconds), non-blocking: results arrive as a search event and
        are read with search_results, like PySR searches. features: inputs from set_dynamics to
        include (the state is included unless include_state is false; at most 6 variables).
        degree 1-3: polynomial terms and products up to that order. extra_functions adds
        exp(x), log(x) or 1/x of each variable. Returns a sparsity front from the simplest law to
        the fullest, each re-scored on the derivative and the best ones simulated."""

        async def run():
            record = await session.start_sindy_search(
                features=features,
                degree=degree,
                extra_functions=list(extra_functions or []),
                include_state=include_state,
                rationale=rationale,
            )
            return {
                "search_id": record.search_id,
                "config": record.summary(session.models),
                "budget": session.budget_status(),
            }

        return await guarded("start_sindy_search", run)

    # -------------------------------------------------------------- notebook

    async def note(entries: list[NoteEntry]) -> str:
        """Record one or more findings in the shared lab notebook (the explanation agent and the
        report read it). Batch several entries in one call. kind: {kinds}. Note mechanisms and
        interactions you established ('insight'), why a promising direction failed
        ('rejected_form', with numbers), data problems ('data_issue'), models worth reporting
        ('candidate') and untested ideas ('hypothesis'). Cite the model_ids each entry rests on."""

        async def run():
            items = [e if isinstance(e, NoteEntry) else NoteEntry(**e) for e in entries][:10]
            for item in items:  # validate all ids before writing anything
                unknown = [m for m in item.model_ids if m not in session.models]
                if unknown:
                    raise ValueError(f"Unknown model_ids {unknown}; cite ids returned by fits")
            for item in items:
                entry = session.note(item.kind, item.text, model_ids=item.model_ids)
                await session.emit("note", f"[{item.kind}] {entry['text'][:160]}")
            return {"recorded": len(items), "notebook_size": len(session.notebook)}

        return await guarded("note", run)

    fit_formula.__doc__ = fit_formula.__doc__.format(functions=", ".join(ALLOWED_FUNCTIONS))
    note.__doc__ = note.__doc__.format(kinds=", ".join(NOTE_KINDS))

    tools = [
        describe_data,
        profile_shape,
        fit_formula,
        inspect_model,
        leaderboard,
        start_pysr_search,
        search_status,
        wait_for_searches,
        cancel_search,
        search_results,
        describe_time_structure,
        set_dynamics,
        fit_ode,
        start_sindy_search,
        note,
    ]

    return tools
