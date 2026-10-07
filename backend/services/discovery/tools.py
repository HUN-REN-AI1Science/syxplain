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
from backend.services.discovery.families import FAMILIES
from backend.services.discovery.session import (
    ALLOWED_BINARY,
    ALLOWED_UNARY,
    NOTE_KINDS,
    BudgetExhausted,
    DiscoverySession,
)

logger = logging.getLogger(__name__)

MAX_OBSERVATION_CHARS = 4000

TargetTransform = Literal["none", "log", "log1p", "sqrt"]
UnaryOp = Literal[ALLOWED_UNARY]
BinaryOp = Literal[ALLOWED_BINARY]
NoteKind = Literal[NOTE_KINDS]
FamilyName = Literal[tuple(FAMILIES)]


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
    literature_enabled: bool = False,
) -> list[Callable[..., Awaitable[str]]]:
    """Create the tool functions bound to ``session``."""

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
        'peaked', 'sigmoidal' or 'roughly linear' come with suggested families. For categorical
        codes it returns the mean of the target per level."""

        async def run():
            out = await asyncio.to_thread(session.shape, feature)
            label = out.get("shape") or out.get("note", "")
            await session.emit("tool", f"Shape of target vs {feature}: {label}")
            return out

        return await guarded("profile_shape", run)

    # --------------------------------------------------------------- fitting

    async def list_families() -> str:
        """Catalog of classic named function families (formula, typical scientific use, requirements)."""

        async def run():
            return [f.summary() for f in FAMILIES.values()]

        return await guarded("list_families", run)

    async def fit_families(
        families: list[FamilyName],
        features: list[str],
        target_transform: TargetTransform = "none",
    ) -> str:
        """Fit several classic families to the same feature(s) and rank them by cross-validated R2.
        Univariate families need exactly one feature; multivariate ones (multiple_linear, cobb_douglas,
        mitscherlich_baule, linear_interactions, additive_saturating) take several. Categorical codes
        are not allowed here (use fit_formula with level(x, k)). target_transform fits the model to the
        transformed target and scores it on the original scale. Each result has a verdict (good /
        adequate / poor / no_signal / failed) and the diagnosed reasons it falls short."""

        async def run():
            transform = _transform(target_transform)
            results = []
            for fam in families[:12]:
                try:
                    m = await asyncio.to_thread(session.fit_family, fam, features, transform)
                    results.append(m)
                except ValueError as e:
                    results.append({"name": fam, "error": str(e)})
            fitted = [r for r in results if not isinstance(r, dict)]
            fitted.sort(key=lambda m: -(m.cv_r2 if m.cv_r2 is not None else -1e9))
            if fitted and not fitted[0].error and fitted[0].cv_r2 is not None:
                best = fitted[0]
                await session.emit(
                    "fit",
                    f"Fitted {len(fitted)} families on {', '.join(features)}; best {best.label} "
                    f"({best.model_id}, CV R2 {best.cv_r2:.3f})",
                    model_id=best.model_id,
                )
            briefs = []
            for m in fitted:
                b = m.brief()
                if "reasons" in b:
                    b["reasons"] = b["reasons"][:3]
                briefs.append(b)
            return {
                "noise_ceiling_r2": session.ceiling_r2 and round(session.ceiling_r2, 4),
                "results": briefs + [r for r in results if isinstance(r, dict)],
            }

        return await guarded("fit_families", run)

    async def fit_formula(
        expression: str,
        label: str = "",
        initial_params: dict[str, float] | None = None,
        target_transform: TargetTransform = "none",
    ) -> str:
        """Fit your own formula. Use feature aliases exactly (case-sensitive) as variables; every
        other identifier is a free parameter (max 12) fitted by least squares — an identifier that
        looks like a misspelled alias is rejected. Allowed: + - * / ^, numbers, pi, and functions
        {functions}. Categorical codes may only appear as level(x, k) indicators.
        Example: 'a*P/(b + P) * exp(c*pH)'. Give initial_params for nonlinear parameters when you
        can (default 1.0). Returns the same metrics and diagnosed reasons as fit_families."""

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
                    model_id=m.model_id,
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
            return d

        return await guarded("inspect_model", run)

    async def leaderboard(top: int = 10) -> str:
        """All fitted models (classic, custom, literature and PySR) ranked by cross-validated R2,
        with the standard error used to decide ties."""

        async def run():
            return {
                "noise_ceiling_r2": session.ceiling_r2 and round(session.ceiling_r2, 4),
                "models": session.leaderboard(top=min(max(top, 1), 30)),
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
    ) -> str:
        """Launch a PySR symbolic-regression search on the HPC cluster (non-blocking; queue + run
        take minutes). Returns a search_id. Keep fitting classic models meanwhile.
        maxsize 7-40 (complexity cap). niterations 50-5000 or null for auto.
        Seeds: guess_model_ids takes ids of your best fits (resolved in the right target space);
        guesses takes up to 5 closed formulas with numeric constants. A seed using an operator you
        did not enable is rejected (the reply lists rejected seeds and why). Restrict features to
        the ones your diagnostics say matter, pick operators matching the shapes you found, and
        explain the purpose in rationale."""

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
            )
            return {
                "search_id": record.search_id,
                "config": record.config,
                "accepted_guesses": record.guesses,
                "rejected_guesses": record.rejected_guesses,
                "budget": session.budget_status(),
            }

        return await guarded("start_pysr_search", run)

    async def search_status() -> str:
        """Status of all PySR searches (queued / ingesting / completed / failed / cancelled; an upper
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
        """Block until ANY of the given PySR searches (default: all running) finishes, or
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
        """Cancel a running PySR search (frees a slot for a better-targeted one)."""

        async def run():
            record = await session.cancel_search(search_id)
            return record.summary(session.models)

        return await guarded("cancel_search", run)

    async def search_results(search_id: str, top: int = 8) -> str:
        """Equations found by a completed PySR search, re-scored like the classic models (constants
        refit in cross-validation): Pareto front of complexity vs error with CV R2, verdicts and
        reasons. Reading a search marks it as reviewed."""

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
        list_families,
        fit_families,
        fit_formula,
        inspect_model,
        leaderboard,
        start_pysr_search,
        search_status,
        wait_for_searches,
        cancel_search,
        search_results,
        note,
    ]

    if literature_enabled:

        async def literature_status() -> str:
            """Published laws found by the literature scout (runs in the background from the start
            of the run). Laws whose variables map onto the data were already fitted (model ids
            L<n>); compare them with your models. Returns status 'pending' while still searching."""

            async def run():
                from backend.services.discovery.literature import literature_summary

                return literature_summary(session)

            return await guarded("literature_status", run)

        async def await_literature(max_minutes: float = 10.0) -> str:
            """Wait (up to max_minutes) for the background literature search to finish, then
            return its laws. Only use when you have nothing else to do."""

            async def run():
                from backend.services.discovery.literature import literature_summary

                task = session.literature_task
                if task is not None and not task.done():
                    cap = max(1.0, min(max_minutes * 60, session.remaining_s - 180))
                    await asyncio.wait([asyncio.shield(task)], timeout=cap)
                return literature_summary(session)

            return await guarded("await_literature", run)

        tools += [literature_status, await_literature]

    return tools
