"""
Discovery session: shared state for one agentic equation-discovery run.

Owns the data contract (aliases, variable kinds, missingness, train/holdout split),
the model registry, the lab notebook, the budget, the searches (PySR for static
equations, SINDy for rate laws once the agent confirms a time structure) and the
agent's view of the world (state line, event inbox). Tools (``tools.py``) are thin wrappers
around these methods; the orchestrator, reconciler and selector read from here.
"""

import asyncio
import contextlib
import difflib
import functools
import logging
import re
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

import numpy as np
import pandas as pd
from scipy import stats

from backend.services.discovery.expression import (
    ExpressionError,
    alias_base,
    compose_template,
    make_alias,
    names_outside_call,
    operators_used,
    parameterize_constants,
    parse_expression,
    parse_template,
)
from backend.services.discovery.families import FAMILIES
from backend.services.discovery.features import (
    MAX_PADDED_SHARE,
    STATS,
    DerivedFeature,
    FeatureSpec,
    SeriesContext,
    TrainView,
    build_candidates,
    feature_evidence,
    selected_autocorrelation,
)
from backend.services.discovery.fitting import (
    TRANSFORMS,
    FitData,
    ModelResult,
    fit_model,
    predict,
    score_holdout,
    target_space,
    time_blocks,
)
from backend.services.discovery.profiling import (
    NEGLIGIBLE_SHARE,
    collinear_pairs,
    compute_profile,
    compute_profile_async,
    describe_features,
    profile_shape,
)
from backend.services.discovery.series import SeriesGrid, final_segment, is_series
from backend.services.discovery.temporal import (
    DynamicsData,
    TimeStructure,
    build_dynamics,
    detect_time_structure,
    simulate,
)

logger = logging.getLogger(__name__)

ALLOWED_UNARY = ("exp", "log", "sqrt", "abs", "sin", "cos", "tanh", "square", "cube", "inv", "neg")
ALLOWED_BINARY = ("+", "-", "*", "/", "^")
NOTE_KINDS = ("hypothesis", "rejected_form", "candidate", "data_issue", "insight")
TARGET_TRANSFORMS = ("none", "log", "log1p", "sqrt")
MAX_PYSR_ROWS = 10000
MAX_FRONT = 40  # equations ingested per search (30 most accurate + 10 simplest)
MIN_HOLDOUT_ROWS = 40  # below this, every metric is out-of-fold CV
EXTRAPOLATION_SHARE = 0.25  # held-out rows beyond a feature's training range worth flagging
# Literature events are not here: exploration is blind to known laws (see relate.py).
INBOX_KINDS = ("search_completed", "search_failed", "search_cancelled", "data_issue")
CATEGORICAL_WORDS = re.compile(
    r"\b(code|coded|class|classes|type|category|categorical|group|id)\b", re.I
)
MODEL_ID_PREFIXES = "CMSLD"  # classic, custom, symbolic, literature, rate law (dynamic)
MODEL_ID_RE = re.compile(rf"\b[{MODEL_ID_PREFIXES}]\d+\b")
SINDY_FUNCTIONS = ("exp", "log", "inv")
SINDY_TIMEOUT_S = 300
N_SIMULATED_PER_SEARCH = 5  # SINDy equations per front that are integrated at ingestion


def _family_parameter_names() -> set[str]:
    """Every parameter identifier used by the family templates (aliases must avoid them)."""
    names: set[str] = set()
    for fam in FAMILIES.values():
        dummy = ["zz_feat"] if fam.n_inputs == 1 else [f"zz_feat{i}" for i in range(fam.max_inputs)]
        with contextlib.suppress(ExpressionError):
            names |= set(parse_expression(fam.build(dummy), dummy).parameters)
    return names


RESERVED_ALIASES = _family_parameter_names()


@dataclass
class DiscoveryBudget:
    """Hard limits for one discovery run."""

    max_iters: int = 30
    max_pysr_runs: int = 3
    max_sindy_runs: int = 6
    max_concurrent_pysr: int = 2
    wall_clock_s: float = 45 * 60
    pysr_timeout_s: int = 1800
    max_tool_calls: int = 60  # safety net only; the agent is shown steps, not tool calls


class SearchLauncher(Protocol):
    """How a session runs PySR searches (Slurm in production, fakes in tests)."""

    async def submit(
        self, search_id: str, input_data: dict[str, Any], on_job_id: Callable[[str], None]
    ) -> str: ...

    async def wait(self, job_id: str) -> tuple[bool, dict[str, Any] | None, str | None]: ...

    async def cancel(self, job_id: str) -> None: ...


@dataclass
class SearchRecord:
    """One search (PySR or SINDy) launched by the agent or the orchestrator."""

    search_id: str
    features: list[str]
    config: dict[str, Any]
    target_transform: str | None
    guesses: list[str]
    rationale: str
    rejected_guesses: list[dict[str, str]] = field(default_factory=list)
    seeded_from_shap: bool = False  # the guesses come from the strongest SHAP interaction
    # submitting | queued | ingesting | completed | failed | cancelled
    status: str = "submitting"
    job_id: str | None = None
    submitted_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    read_at: float | None = None  # when the agent last read its results
    error: str | None = None
    model_ids: list[str] = field(default_factory=list)
    n_front: int = 0
    task: asyncio.Task | None = field(default=None, repr=False)
    engine: str = "pysr"  # pysr | sindy

    @property
    def done(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")

    @property
    def unread(self) -> bool:
        return self.status == "completed" and self.read_at is None

    def summary(self, models: dict[str, ModelResult]) -> dict[str, Any]:
        elapsed = (self.finished_at or time.monotonic()) - self.submitted_at
        timeout = int(self.config.get("timeout_in_seconds") or 0)
        out: dict[str, Any] = {
            "search_id": self.search_id,
            "engine": self.engine,
            "status": self.status,
            "features": self.features,
        }
        if self.engine == "pysr":
            out |= {
                "unary_operators": self.config.get("unary_operators"),
                "binary_operators": self.config.get("binary_operators"),
                "maxsize": self.config.get("maxsize"),
                "niterations": self.config.get("niterations"),
                **({"template": self.config["template"]} if self.config.get("template") else {}),
                "target_transform": self.target_transform,
                "guesses": self.guesses,
                "rejected_guesses": self.rejected_guesses,
                **({"seeded_from_shap": True} if self.seeded_from_shap else {}),
            }
        else:
            out |= {
                "problem": "dynamic",
                **{k: v for k, v in self.config.items() if k != "timeout_in_seconds"},
            }
        out |= {
            "rationale": self.rationale,
            "elapsed_s": round(elapsed),
            "timeout_s": timeout,
        }
        if not self.done:
            # Upper bound: PySR stops at its timeout (queue wait comes on top).
            out["expected_done_in_s"] = max(0, timeout - round(elapsed))
        if self.error:
            out["error"] = self.error
        evaluated = [models[m] for m in self.model_ids if m in models and not models[m].error]
        if self.status == "completed":
            out["n_front"] = self.n_front
            out["n_ingested"] = len(evaluated)
        if evaluated:
            best = max(evaluated, key=lambda m: m.cv_r2 if m.cv_r2 is not None else -np.inf)
            out["n_equations"] = len(evaluated)
            out["best_cv_r2"] = best.cv_r2 and round(best.cv_r2, 4)
            out["best_model_id"] = best.model_id
        return out


class BudgetExhausted(Exception):
    """Raised by tools once a hard limit is reached."""


class DiscoverySession:
    """State and operations of one discovery run."""

    def __init__(
        self,
        data: pd.DataFrame,
        target_column: str,
        predictor_columns: list[str],
        budget: DiscoveryBudget | None = None,
        launcher: SearchLauncher | None = None,
        on_event: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
        seed: int = 0,
        max_fit_rows: int = 5000,
        holdout_fraction: float = 0.2,
        descriptions: dict[str, str] | None = None,
        sparse_column_threshold: float = 0.2,
        max_categorical_levels: int = 10,
        launchers: dict[str, SearchLauncher] | None = None,
    ):
        self.budget = budget or DiscoveryBudget()
        # Engine -> launcher; ``launcher`` is shorthand for the PySR one.
        self.launchers: dict[str, SearchLauncher] = dict(launchers or {})
        if launcher is not None:
            self.launchers.setdefault("pysr", launcher)
        self._on_event = on_event
        self.seed = seed
        self.started_at = time.monotonic()
        self.tool_calls = 0
        self.steps_used = 0
        self.events: list[dict[str, Any]] = []
        self._inbox_cursor = 0
        self.notebook: list[dict[str, Any]] = []
        self.models: dict[str, ModelResult] = {}
        self.searches: dict[str, SearchRecord] = {}
        self._cancelled_jobs: set[str] = set()
        self.known_laws: dict[str, Any] | None = None
        # Published laws collected by the scout, fitted only after exploration (relate.py)
        self.literature_raw: list[dict[str, Any]] | None = None
        # Supplied literature: "web" or "supplied", what the scout read from it (raw), and
        # the constraints mapped onto the data at RELATE (literature_coherence.py)
        self.literature_source: str = "web"
        self.literature_constraints_raw: list[Any] | None = None
        self.literature_constraints: list[dict[str, Any]] | None = None
        # Relationships of the literature among the other variables (formula_space.py)
        self.literature_relations_raw: list[Any] | None = None
        self.literature_task: asyncio.Task | None = None
        self.agent_finished_at: float | None = None
        self.cancelled = False
        self._lock = threading.Lock()
        self._model_counter = 0
        self._profile: dict[str, Any] | None = None
        self._shap_sample: tuple[np.ndarray, np.ndarray] | None = None
        # SHAP summary/dependence PNGs: [{"name", "kind", "feature", "title", "b64"}]
        self.shap_plots: list[dict[str, Any]] = []
        descriptions = descriptions or {}

        # --- clean, account for missingness ---------------------------------
        frame = data[[target_column, *predictor_columns]].apply(pd.to_numeric, errors="coerce")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        self.n_uploaded = len(frame)
        self.missing_by_column = {
            str(c): int(v) for c, v in frame.isna().sum().items() if int(v) > 0
        }
        self.excluded_columns: list[dict[str, str]] = []
        kept = list(predictor_columns)
        frame = frame[frame[target_column].notna()]
        # Drop predictors whose missingness alone removes many rows, when dropping
        # them at least doubles the complete rows (always keep one predictor).
        while len(kept) > 1:
            complete = int(frame[kept].notna().all(axis=1).sum())
            worst = max(kept, key=lambda c: frame[c].isna().mean())
            miss = float(frame[worst].isna().mean())
            others = [c for c in kept if c != worst]
            without = int(frame[others].notna().all(axis=1).sum())
            if miss > sparse_column_threshold and without >= 2 * max(complete, 1):
                kept.remove(worst)
                self.excluded_columns.append(
                    {
                        "column": str(worst),
                        "reason": f"{miss:.0%} missing; keeping it would leave {complete} of "
                        f"{without} complete rows",
                    }
                )
            else:
                break
        frame = frame[[target_column, *kept]].dropna()
        if len(frame) < 10:
            raise ValueError(f"Only {len(frame)} complete rows — not enough data for discovery")

        # --- aliases (qualifiers kept only where needed to tell columns apart) ---
        bases = [alias_base(c) for c in kept]
        clashing = {b for b in bases if bases.count(b) > 1}
        taken: set[str] = set()
        self.alias_of: dict[str, str] = {}
        for col, base in zip(kept, bases, strict=True):
            alias = make_alias(col, taken, RESERVED_ALIASES, keep_qualifiers=base in clashing)
            taken.add(alias)
            self.alias_of[col] = alias
        self.target_alias = make_alias(target_column, taken, RESERVED_ALIASES)
        self.column_of = {a: c for c, a in self.alias_of.items()}
        self.column_of[self.target_alias] = target_column
        self.target_column = target_column
        self.features = [self.alias_of[c] for c in kept]
        frame.columns = [self.target_alias, *self.features]

        # --- variable kinds -------------------------------------------------
        self.kinds: dict[str, str] = {}
        self.levels: dict[str, list[float]] = {}
        for col in kept:
            alias = self.alias_of[col]
            values = frame[alias].to_numpy(dtype=float)
            uniq = np.unique(values)
            # Codes look like consecutive small integers (1, 2, 3, ...); designed dose
            # levels such as 0/40/80/120 stay continuous.
            integer = bool(np.all(np.equal(np.mod(uniq, 1), 0)))
            consecutive = integer and len(uniq) > 1 and bool(np.all(np.diff(uniq) == 1))
            worded = bool(CATEGORICAL_WORDS.search(f"{col} {descriptions.get(col, '')}"))
            if 3 <= len(uniq) <= max_categorical_levels and (consecutive or (integer and worded)):
                self.kinds[alias] = "categorical"
                self.levels[alias] = [float(u) for u in uniq]
            else:
                self.kinds[alias] = "continuous"

        # --- time structure (all uploaded columns: time is often not a predictor) ---
        self.raw_data = data
        self.dynamics: DynamicsData | None = None
        try:
            self.time_structure: TimeStructure | None = detect_time_structure(
                data, target_column, descriptions
            )
        except Exception as e:  # a proposal only; never block the static analysis
            logger.warning(f"Time-structure detection failed: {e}", exc_info=True)
            self.time_structure = None

        # --- a long series: rows in time order (features come from the feature stage) ---
        self.descriptions = dict(descriptions)
        self.series: dict[str, Any] | None = None
        self._series_ctx: SeriesContext | None = None
        self._max_fit_rows = max_fit_rows
        keys = held = None
        if is_series(self.time_structure) and data.index.is_unique:
            try:
                frame, keys, held = self._order_series(frame, data, holdout_fraction)
            except Exception as e:  # never block the row-wise analysis
                logger.warning(f"Series ordering failed: {e}", exc_info=True)
                self.series, self._series_ctx = None, None

        # --- split ------------------------------------------------------------
        self._apply_split(frame, keys, held, holdout_fraction)

        for col in self.excluded_columns:
            self.note("data_issue", f"Column '{col['column']}' excluded: {col['reason']}")

    def _order_series(
        self, frame: pd.DataFrame, data: pd.DataFrame, holdout_fraction: float
    ) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
        """
        Sort the rows by trajectory and time and mark the final part of each trajectory as
        the holdout. Time-dependent features are added later by the feature stage
        (``add_series_features``); padding keeps every row, so the split never changes.
        Returns the frame, each row's trajectory code and the holdout mask.
        """
        ts = self.time_structure
        grid = SeriesGrid.build(data, ts)
        pos = data.index.get_indexer(frame.index)
        keys, steps = grid.key[pos], grid.step[pos]
        ok = keys >= 0
        rows = np.flatnonzero(ok)[np.lexsort((steps[ok], keys[ok]))]
        frame, keys, pos = frame.iloc[rows], keys[rows], pos[rows]
        held = (
            final_segment(keys, holdout_fraction)
            if len(frame) >= MIN_HOLDOUT_ROWS
            else np.zeros(len(keys), dtype=bool)
        )
        self._series_ctx = SeriesContext(
            grid=grid,
            pos=pos,
            keys=keys,
            held=held,
            time_column=ts.time_column,
            group_column=ts.group_column,
        )
        self.series = {
            "time_column": ts.time_column,
            "group_column": ts.group_column,
            "n_series": len(np.unique(keys)),
            "time_step": grid.step_size,
            "lag_features": [],
            "padded_rows": 0,
            "feature_stage": {"status": "not_run"},
        }
        return frame, keys, held

    def _apply_split(
        self,
        frame: pd.DataFrame,
        keys: np.ndarray | None,
        held: np.ndarray | None,
        holdout_fraction: float,
    ) -> None:
        """Train/holdout split and the fitting data (re-run when series features are added)."""
        self._frame = frame
        max_fit_rows, seed = self._max_fit_rows, self.seed
        self.n_rows = len(frame)
        # Rows without a time value are missing values too
        self.dropped_incomplete = self.n_uploaded - self.n_rows
        rng = np.random.default_rng(seed)
        if keys is None:
            order = rng.permutation(len(frame))
            n_holdout = (
                round(holdout_fraction * len(frame)) if len(frame) >= MIN_HOLDOUT_ROWS else 0
            )
            held_rows, train_rows = order[:n_holdout], order[n_holdout:]
        else:  # the final part of each series: prediction forward in time
            held_rows, train_rows = np.flatnonzero(held), np.flatnonzero(~held)
        self.holdout = frame.iloc[held_rows].reset_index(drop=True)
        self.train = frame.iloc[train_rows].reset_index(drop=True)
        fit_frame, fit_keys = self.train, None if keys is None else keys[train_rows]
        if len(self.train) > max_fit_rows:
            if fit_keys is None:
                fit_frame = self.train.sample(n=max_fit_rows, random_state=seed)
            else:  # thinned, but kept in time order
                rows = np.sort(rng.choice(len(self.train), max_fit_rows, replace=False))
                fit_frame, fit_keys = self.train.iloc[rows], fit_keys[rows]
        y = fit_frame[self.target_alias].to_numpy(dtype=float)
        n_folds = 5 if len(y) >= 25 else 3
        folds = (
            time_blocks(fit_keys, n_folds)
            if fit_keys is not None
            else np.array_split(rng.permutation(len(y)), n_folds)
        )
        self.fit_data = FitData(
            X={f: fit_frame[f].to_numpy(dtype=float) for f in self.features},
            y=y,
            folds=folds,
            series=fit_keys,
        )

    # ------------------------------------------------------------------
    # Time-dependent features of a long series (the feature stage)
    # ------------------------------------------------------------------

    def _series_sources(self) -> list[str]:
        """Continuous uploaded features that may be lagged or aggregated."""
        ctx = self._series_ctx
        derived = set(self.lag_features)
        return [
            a
            for a in self.continuous_features
            if a not in derived and self.column_of[a] not in (ctx.time_column, ctx.group_column)
        ]

    def _raw_values(self, alias: str) -> np.ndarray:
        """A source's values on every uploaded row (the history beyond the complete rows)."""
        raw = pd.to_numeric(self.raw_data[self.column_of[alias]], errors="coerce")
        values = raw.to_numpy(dtype=float)
        values[~np.isfinite(values)] = np.nan  # like the cleaned frame: inf is missing
        return values

    def series_feature_context(self) -> dict[str, Any]:
        """What the feature proposer is told about the series."""
        ctx = self._series_ctx
        if ctx is None:
            raise ValueError("The data is not a long series")

        def item(alias: str) -> dict[str, Any]:
            column = self.column_of[alias]
            return {
                "alias": alias,
                "column": column,
                "description": self.descriptions.get(column, ""),
            }

        return {
            "target": item(self.target_alias),
            "sources": [item(a) for a in self._series_sources()],
            "time_column": ctx.time_column,
            "time_is_date": ctx.dates is not None,
            "time_step": ctx.grid.step_size,
            "time_step_unit": "days" if ctx.dates is not None else f"units of {ctx.time_column}",
            "group_column": ctx.group_column,
            "n_trajectories": ctx.n_trajectories,
            "training_rows_shortest_trajectory": ctx.train_rows_min,
            "max_padded_rows_per_trajectory": ctx.max_padded_rows,
            "allowed_periods": ctx.allowed_periods,
            "stats": list(STATS),
        }

    def evaluate_feature_specs(
        self, specs: list[FeatureSpec]
    ) -> tuple[list[DerivedFeature], list[dict[str, str]], dict[str, Any]]:
        """Check, compute and measure proposed specs: candidates, rejections, evidence."""
        ctx = self._series_ctx
        if ctx is None:
            raise ValueError("The data is not a long series")
        sources = self._series_sources()
        candidates, rejected = build_candidates(
            specs,
            ctx,
            functools.cache(self._raw_values),  # several specs share a source
            self.column_of,
            set(sources),
            self.target_alias,
            set(self.features) | {self.target_alias},
            set(RESERVED_ALIASES),
        )
        frame = self._frame
        current = {a: frame[a].to_numpy(dtype=float) for a in [*sources, self.target_alias]}
        evidence = feature_evidence(candidates, self._train_view(), current)
        return candidates, rejected, evidence

    def _train_view(self) -> TrainView:
        """The current continuous features and the target on the training rows."""
        ctx, frame = self._series_ctx, self._frame
        return TrainView.build(
            [frame[a].to_numpy(dtype=float) for a in self.continuous_features],
            frame[self.target_alias].to_numpy(dtype=float),
            ctx.keys,
            ~ctx.held,
        )

    def add_series_features(
        self,
        selected: list[DerivedFeature],
        reasons: dict[str, str],
        record: dict[str, Any],
    ) -> None:
        """
        Add the selected derived features and re-run the split (same rows, same holdout).
        Rows where a feature of the target's own past was back-filled carry their own target
        value, so they leave the data; every other filled cell keeps its row.
        """
        ctx = self._series_ctx
        if ctx is None:
            raise ValueError("The data is not a long series")
        autocorr = selected_autocorrelation(selected, self._train_view())
        leak = np.zeros(len(self._frame), dtype=bool)
        for c in selected:
            leak |= c.leaks_target
        keep = ~leak
        frame = self._frame.assign(**{c.alias: c.values for c in selected})[keep]
        padded = np.zeros(int(keep.sum()), dtype=bool)
        added = []
        for c in selected:
            source_text = self.descriptions.get(self.column_of[c.spec.source])
            description = c.description + (f" ({source_text})" if source_text else "")
            self.descriptions[c.column] = description
            self.alias_of[c.column] = c.alias
            self.column_of[c.alias] = c.column
            self.kinds[c.alias] = "continuous"
            self.features.append(c.alias)
            padded |= c.padded[keep]
            added.append(
                c.record()
                | {
                    "description": description,
                    "reason": reasons.get(c.alias, ""),
                    "padded_rows": int(c.padded[keep].sum()),
                }
            )
        self.series = (
            self.series
            | record
            | {
                "lag_features": added,
                "padded_rows": int(padded.sum()),
                "rows_without_history": int(leak.sum()),
                "padding": "edge: a cell without history takes its trajectory's nearest earlier "
                f"value, or its first available one (at most {MAX_PADDED_SHARE:.0%} of each "
                "trajectory's training rows); where a feature of the target's own past has no "
                "history at a trajectory's start, the row is left out instead",
                "residual_autocorrelation": autocorr,
            }
        )
        ctx = self._series_ctx = replace(
            ctx, pos=ctx.pos[keep], keys=ctx.keys[keep], held=ctx.held[keep]
        )
        self._apply_split(frame, ctx.keys, ctx.held, holdout_fraction=0.0)  # split is fixed
        self._profile = None
        self._shap_sample = None

    # ------------------------------------------------------------------
    # Data contract
    # ------------------------------------------------------------------

    @property
    def has_holdout(self) -> bool:
        return len(self.holdout) > 0

    @property
    def metric_basis(self) -> str:
        return "holdout" if self.has_holdout else "cv"

    @property
    def categorical_features(self) -> list[str]:
        return [f for f in self.features if self.kinds.get(f) == "categorical"]

    @property
    def continuous_features(self) -> list[str]:
        return [f for f in self.features if self.kinds.get(f) != "categorical"]

    @property
    def lag_features(self) -> list[str]:
        return [d["feature"] for d in self.series["lag_features"]] if self.series else []

    def split_info(self) -> dict[str, Any]:
        chronological = self.series is not None
        held = (
            f"the final {len(self.holdout)} rows in time (the last part of each series)"
            if chronological
            else f"{len(self.holdout)} held-out rows"
        )
        out = {
            "complete_rows": self.n_rows,
            "train": len(self.train),
            "holdout": len(self.holdout),
            "has_holdout": self.has_holdout,
            "regime": "holdout" if self.has_holdout else "cv_only",
            "metric_basis": self.metric_basis,
            "order": "chronological" if chronological else "random",
            "scored_on": (
                held
                if self.has_holdout
                else f"out-of-fold cross-validation ({len(self.fit_data.folds)} folds; "
                f"fewer than {MIN_HOLDOUT_ROWS} rows, no holdout)"
            ),
            "uploaded": self.n_uploaded,
            "dropped_incomplete": self.dropped_incomplete,
            "missing_by_column": self.missing_by_column,
            "excluded_columns": self.excluded_columns,
        }
        beyond = self.holdout_extrapolation()
        if beyond:
            out["holdout_extrapolates"] = beyond
        return out

    def holdout_extrapolation(self) -> dict[str, float]:
        """Share of held-out rows outside the training range, per continuous feature (only
        those with at least EXTRAPOLATION_SHARE): there the holdout tests extrapolation."""
        if not self.has_holdout:
            return {}
        out = {}
        for f in self.continuous_features:
            x, h = self.train[f].to_numpy(dtype=float), self.holdout[f].to_numpy(dtype=float)
            share = float(np.mean((h < x.min()) | (h > x.max())))
            if share >= EXTRAPOLATION_SHARE:
                out[f] = round(share, 2)
        return out

    def variables_for(self, aliases: list[str]) -> dict[str, str]:
        """alias -> original column for the given aliases plus the target."""
        out = {a: self.column_of[a] for a in aliases if a in self.column_of}
        out[self.target_alias] = self.target_column
        return out

    # ------------------------------------------------------------------
    # Budget, events and the agent's view of the world
    # ------------------------------------------------------------------

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def remaining_s(self) -> float:
        return max(0.0, self.budget.wall_clock_s - self.elapsed_s)

    def reset_clock(self) -> None:
        """Start the agent's time budget now (profiling is not charged to it)."""
        self.started_at = time.monotonic()

    def check_budget(self) -> None:
        self.tool_calls += 1
        if self.remaining_s <= 0:
            raise BudgetExhausted("Wall-clock budget exhausted")
        if self.tool_calls > self.budget.max_tool_calls:
            raise BudgetExhausted("Tool-call budget exhausted")

    def budget_status(self) -> dict[str, Any]:
        return {
            "elapsed_min": round(self.elapsed_s / 60, 1),
            "remaining_min": round(self.remaining_s / 60, 1),
            "steps_used": self.steps_used,
            "steps_max": self.budget.max_iters,
            "pysr_searches_used": self._n_searches("pysr"),
            "pysr_searches_max": self.budget.max_pysr_runs,
            "pysr_running": self._n_searches("pysr", running=True),
            "sindy_searches_used": self._n_searches("sindy"),
            "sindy_searches_max": self.budget.max_sindy_runs,
            "dynamics": self.dynamics is not None,
        }

    def _n_searches(self, engine: str, running: bool = False) -> int:
        return sum(
            1 for s in self.searches.values() if s.engine == engine and not (running and s.done)
        )

    async def emit(self, kind: str, text: str, **extra: Any) -> None:
        event = {"t": round(self.elapsed_s, 1), "kind": kind, "text": text, **extra}
        self.events.append(event)
        if self._on_event:
            try:
                res = self._on_event(event)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.debug(f"Discovery event callback failed: {e}")

    def take_inbox(self) -> list[dict[str, Any]]:
        """Events the agent has not seen yet (search results, data issues)."""
        new = [e for e in self.events[self._inbox_cursor :] if e["kind"] in INBOX_KINDS]
        self._inbox_cursor = len(self.events)
        return new

    def pending_or_unread(self) -> list[SearchRecord]:
        return [s for s in self.searches.values() if not s.done or s.unread]

    def state_line(self, step: int, max_iters: int) -> str:
        """Compact live status appended to every observation."""
        parts = [f"step {step}/{max_iters}", f"{self.remaining_s / 60:.0f} min left"]
        for s in self.searches.values():
            item = f"{s.search_id} {s.status}"
            if not s.done:
                expected = max(
                    0,
                    int(s.config.get("timeout_in_seconds") or 0)
                    - int(time.monotonic() - s.submitted_at),
                )
                item += f" (<= {expected // 60} min)"
            summary = s.summary(self.models)
            if summary.get("best_model_id"):
                item += f" best {summary['best_model_id']} cv_r2={summary['best_cv_r2']}"
            if s.unread:
                item += " UNREAD"
            parts.append(item)
        top = self.leaderboard(top=3)
        if top:
            parts.append(
                "top: " + ", ".join(f"{m['model_id']} {m['cv_r2']} {m['verdict']}" for m in top)
            )
        rates = self.leaderboard(top=2, problem="dynamic")
        if rates:
            parts.append(
                "top rate laws: "
                + ", ".join(
                    f"{m['model_id']} dydt_r2={m['cv_r2']} sim_r2={m.get('simulation_r2')}"
                    for m in rates
                )
            )
        line = "STATE | " + " | ".join(parts)
        events = self.take_inbox()
        if events:
            line += "\n" + "\n".join(f"[event] {e['text']}" for e in events)
        left = max_iters - step
        if left <= 3:
            line += f"\nWARNING: {left} steps left — record key notes, then finish."
        return line

    # ------------------------------------------------------------------
    # Data understanding
    # ------------------------------------------------------------------

    def _profile_inputs(
        self,
    ) -> tuple[np.ndarray, np.ndarray, list[str], list[bool], int, list[str], np.ndarray | None]:
        """compute_profile's arguments: X, y, names, categorical, seed, plot labels, series."""
        X = np.column_stack([self.fit_data.X[f] for f in self.features])
        cat = [self.kinds.get(f) == "categorical" for f in self.features]
        # 'P' or 'P (P_added mg/kg)': the agent's alias plus the column it stands for
        labels = [
            f if self.column_of.get(f, f) == f else f"{f} ({self.column_of[f]})"
            for f in self.features
        ]
        return X, self.fit_data.y, list(self.features), cat, self.seed, labels, self.fit_data.series

    async def ensure_profile(self, timeout_s: float = 240) -> dict[str, Any]:
        """Compute the profile in the profiling process (keeps the event loop free)."""
        if self._profile is not None:
            return self._profile
        args = self._profile_inputs()
        try:
            raw = await compute_profile_async(*args, timeout_s=timeout_s)
        except asyncio.TimeoutError:
            logger.warning("Profiling timed out; continuing with a light profile")
            raw = None
        except Exception as e:
            logger.warning(f"Profiling process failed ({e}); computing in a thread")
            raw = await asyncio.to_thread(compute_profile, *args)
        return self._assemble_profile(raw)

    def profile(self) -> dict[str, Any]:
        """Synchronous profile (in-process); used by scripts, tests and fallbacks."""
        if self._profile is not None:
            return self._profile
        return self._assemble_profile(compute_profile(*self._profile_inputs()))

    def _assemble_profile(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        X, y = self.fit_data.X, self.fit_data.y
        if raw is None:  # light profile: no forests, no SHAP
            raw = {
                "ceiling_r2": None,
                "ceiling_sd": None,
                "importance_mean": [],
                "importance_sd": [],
                "mutual_info": [],
                "shap": {"available": False, "reason": "profiling timed out"},
                "shap_sample": None,
            }
        self.fit_data.ceiling_r2 = raw["ceiling_r2"]
        self.fit_data.ceiling_sd = raw["ceiling_sd"]
        self._shap_sample = raw.get("shap_sample")
        self.shap_plots = raw.get("shap_plots") or []
        importance = {
            f: (raw["importance_mean"][i], raw["importance_sd"][i])
            for i, f in enumerate(self.features)
            if i < len(raw["importance_mean"])
        }
        mi = {
            f: raw["mutual_info"][i]
            for i, f in enumerate(self.features)
            if i < len(raw["mutual_info"])
        }
        features = describe_features(X, y, self.column_of, importance, mi, self.kinds)
        shap = raw["shap"]
        shap_share = {d["feature"]: d["share"] for d in shap.get("importance", [])}
        for d in features:
            d["shap_share"] = shap_share.get(d["alias"])
            if d["kind"] == "categorical":
                d["levels"] = self.levels.get(d["alias"])
        # Consensus ranking over permutation importance, mutual information and SHAP
        # (any single measure is noisy on small data).
        for key in ("permutation_importance", "mutual_info", "shap_share"):
            order = sorted(features, key=lambda d, k=key: -(d.get(k) or 0.0))
            for rank, d in enumerate(order):
                d.setdefault("_ranks", []).append(rank)
        features.sort(key=lambda d: np.mean(d.pop("_ranks")))

        ceiling = raw["ceiling_r2"]
        self._profile = {
            "rows": {
                "uploaded": self.n_uploaded,
                "complete": self.n_rows,
                "train": len(self.train),
                "holdout": len(self.holdout),
                "used_for_fitting": len(y),
                "metric_basis": self.metric_basis,
            },
            "excluded_columns": self.excluded_columns,
            "target": {
                "alias": self.target_alias,
                "column": self.target_column,
                "min": float(f"{y.min():.4g}"),
                "max": float(f"{y.max():.4g}"),
                "mean": float(f"{y.mean():.4g}"),
                "sd": float(f"{y.std():.4g}"),
                "all_positive": bool(np.all(y > 0)),
                "skewness": round(float(pd.Series(y).skew()), 2),
            },
            "noise_ceiling_r2": None if ceiling is None else round(ceiling, 4),
            "noise_ceiling_sd": None if raw["ceiling_sd"] is None else round(raw["ceiling_sd"], 4),
            "has_signal": self.fit_data.has_signal,
            "noise_ceiling_note": (
                "Out-of-fold R2 of flexible tree ensembles on the training data: a rough estimate "
                "of the achievable accuracy. A smooth law can beat it on small datasets. Below "
                "0.05 there is no detectable signal."
            ),
            "features": features,
            "collinear_pairs": collinear_pairs(X),
            "shap": shap,
        }
        return self._profile

    def overview(self, max_features: int = 12) -> dict[str, Any]:
        """Compact profile for the agent's prompt (about 2k characters)."""
        p = self.profile() if self._profile is None else self._profile
        max_features += len(self.lag_features)  # lags must not push current drivers out
        shap = p.get("shap") or {}
        partial = shap.get("partial_effects") or {}
        feats = []
        for d in p["features"][:max_features]:
            item = {
                "alias": d["alias"],
                "kind": d["kind"],
                "perm_imp": d["permutation_importance"],
                "mi": d["mutual_info"],
                "shap_share": d.get("shap_share"),
                "range": [d["min"], d["max"]],
                "positive": d["all_positive"],
            }
            if d["alias"] in partial:
                item["partial_shape"] = partial[d["alias"]]
            if d["kind"] == "categorical":
                item["levels"] = d.get("levels")
            feats.append(item)
        return {
            "target": p["target"],
            # metric_basis is how the final report scores; the agent only ever sees CV
            "rows": {k: v for k, v in p["rows"].items() if k != "metric_basis"},
            "scoring": self.scoring_note(),
            "noise_ceiling_r2": p["noise_ceiling_r2"],
            "noise_ceiling_sd": p["noise_ceiling_sd"],
            "has_signal": p["has_signal"],
            "features_ranked": feats,
            "more_features": max(0, len(p["features"]) - max_features),
            "shap_interactions": shap.get("interactions", []) if shap.get("reliable", True) else [],
            "shap_reliable": shap.get("reliable"),
            "collinear_pairs": p["collinear_pairs"][:6],
            "excluded_columns": p["excluded_columns"],
            "time_structure": self.time_structure_brief(),
        }

    def scoring_note(self) -> str:
        """How the agent's tools score models, for DATA_OVERVIEW."""
        folds = (
            "contiguous time blocks of the series (the end blocks extrapolate, so cv_se is "
            "larger than with random folds)"
            if self.series
            else "random folds"
        )
        held = (
            f"The {len(self.holdout)} held-out rows are scored once after you finish, for the "
            "report only; you never see them."
            if self.has_holdout
            else "There is no holdout (too few rows)."
        )
        return (
            f"Every tool reports cross-validated scores on the training rows (cv_r2, cv_rmse; "
            f"cv_se = standard error of the per-fold RMSE), with {len(self.fit_data.folds)} "
            f"folds of {folds}. {held} Models are tied when cv_rmse is within one cv_se of "
            "the best."
        )

    def time_structure_brief(self) -> dict[str, Any] | None:
        """Compact time-structure proposal for DATA_OVERVIEW (None without a plausible one)."""
        ts = self.time_structure
        if ts is None or ts.time_column is None or ts.confidence == "none":
            return None
        out = {
            "time_column": ts.time_column,
            "group_column": ts.group_column,
            "confidence": ts.confidence,
            "n_trajectories": ts.n_trajectories,
            "points_min": ts.points_min,
            "smoothness_along_time": ts.evidence.get("smoothness_along_time"),
            "regime": "series" if self.series else "trajectories",
            "confirmed": self.dynamics is not None,
        }
        if self.series:
            out["lag_features"] = self.lag_features
            out["residual_autocorrelation"] = self.series.get("residual_autocorrelation")
        return out

    @property
    def ceiling_r2(self) -> float | None:
        return self.fit_data.ceiling_r2

    def shape(self, feature: str) -> dict[str, Any]:
        """Marginal shape (binned target means) plus the SHAP partial-effect shape."""
        self._require_features([feature])
        if self.kinds.get(feature) == "categorical":
            x, y = self.fit_data.X[feature], self.fit_data.y
            return {
                "feature": feature,
                "kind": "categorical",
                "note": "Integer-coded categories: compare level means; use level(x, k) in formulas.",
                "level_means": {
                    str(lv): float(f"{y[x == lv].mean():.4g}") for lv in self.levels[feature]
                },
            }
        out = {"feature": feature} | profile_shape(self.fit_data.X[feature], self.fit_data.y)
        if self._shap_sample is not None and (self._profile or {}).get("shap", {}).get(
            "reliable", True
        ):
            Xs, values = self._shap_sample
            j = self.features.index(feature)
            partial = profile_shape(Xs[:, j], values[:, j], ref_sd=float(np.std(self.fit_data.y)))
            out["partial_effect"] = {
                "shape": partial["shape"],
                "note": "SHAP dependence: effect of this feature with the others accounted for",
                "bins": [{"x_mid": b["x_mid"], "effect": b["y_mean"]} for b in partial["bins"]],
            }
        return out

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------

    def _require_features(self, features: list[str]) -> None:
        unknown = [f for f in features if f not in self.fit_data.X]
        if unknown:
            hints = []
            for u in unknown:
                close = difflib.get_close_matches(u, self.features, n=1, cutoff=0.6)
                if close:
                    hints.append(f"'{u}' -> did you mean '{close[0]}'?")
            raise ValueError(
                f"Unknown feature(s) {unknown}. Aliases are case-sensitive: {self.features}"
                + (f" ({'; '.join(hints)})" if hints else "")
            )

    def _new_id(self, prefix: str) -> str:
        with self._lock:
            self._model_counter += 1
            return f"{prefix}{self._model_counter}"

    def _register(self, result: ModelResult) -> ModelResult:
        with self._lock:
            self.models[result.model_id] = result
        return result

    def snapshot(self) -> list[ModelResult]:
        with self._lock:
            return list(self.models.values())

    def _check_transform(self, transform: str | None) -> str | None:
        if transform in (None, "", "none", "None"):
            return None
        if transform not in TRANSFORMS:
            raise ValueError(
                f"target_transform must be one of none, log, log1p, sqrt (got {transform!r})"
            )
        return transform

    def _others(self, used: list[str], problem: str = "static") -> list[str]:
        variables = self._space(problem)[0]
        return [f for f in variables if f not in used and self.kinds.get(f) != "categorical"]

    def _space(self, problem: str) -> tuple[list[str], FitData]:
        """Variables and training data of a problem: static y = f(x), or the rate law."""
        if problem == "dynamic":
            dyn = self._require_dynamics()
            return dyn.variables, dyn.fit_data
        return self.features, self.fit_data

    def fit_family(
        self, family: str, features: list[str], target_transform: str | None = None
    ) -> ModelResult:
        fam = FAMILIES.get(family)
        if fam is None:
            raise ValueError(f"Unknown family {family!r}. Available: {sorted(FAMILIES)}")
        self._require_features(features)
        transform = self._check_transform(target_transform)
        if fam.n_inputs == 1 and len(features) != 1:
            raise ValueError(f"{family} takes exactly one feature")
        if fam.n_inputs == 0 and not (1 <= len(features) <= fam.max_inputs):
            raise ValueError(f"{family} takes 1-{fam.max_inputs} features")
        categorical = [f for f in features if self.kinds.get(f) == "categorical"]
        if categorical:
            raise ValueError(
                f"{categorical} are integer-coded categories, not magnitudes: compare levels with "
                f"fit_formula using level(x, k), e.g. 'a + b*level({categorical[0]}, "
                f"{self.levels[categorical[0]][1]:g})'"
            )

        result = ModelResult(
            model_id=self._new_id("C"),
            kind="classic",
            name=family,
            label=fam.label,
            expression=fam.build(features),
            features=list(features),
            target_transform=transform,
        )
        xs = [self.fit_data.X[f] for f in features]
        if fam.requires_positive_x and any(np.any(x <= 0) for x in xs):
            bad = [f for f, x in zip(features, xs, strict=True) if np.any(x <= 0)]
            result.error = f"{fam.label} requires positive inputs but {bad} contain values <= 0"
            result.reasons = [result.error]
            return self._register(result)

        expr = parse_expression(result.expression, list(features))
        clash = set(expr.parameters) & set(self.features)
        if clash:  # aliases avoid parameter names, so this is a bug guard
            result.error = f"feature alias collides with a family parameter: {sorted(clash)}"
            result.reasons = [result.error]
            return self._register(result)
        z = target_space(self.fit_data.y, transform)
        guess = fam.guess(xs, z) if np.all(np.isfinite(z)) else {}
        fit_model(
            result,
            expr,
            self.fit_data,
            guess,
            fam.lower_bounds,
            seed=self.seed,
            other_features=self._others(features),
        )
        return self._register(result)

    def _check_identifiers(
        self, expr, initial_params: dict[str, float], variables: list[str]
    ) -> None:
        """Unbound identifiers that look like variables are almost always typos."""
        lowered = {f.lower(): f for f in variables}
        columns = {str(c): a for a, c in self.column_of.items() if a in variables}
        for name in expr.parameters:
            if name in initial_params:
                continue
            if name in self.features:  # a feature that is not a variable of this problem
                raise ExpressionError(
                    f"'{name}' is not a variable here (time, trajectory, categorical and derived "
                    f"columns such as lags are not inputs of a rate law); variables: {variables}"
                )
            match = lowered.get(name.lower()) or columns.get(name)
            if match is None and len(name) > 2:
                close = difflib.get_close_matches(name, variables, n=1, cutoff=0.8)
                match = close[0] if close else None
            if match is not None:
                raise ExpressionError(
                    f"Unknown identifier '{name}' looks like feature '{match}'; use the exact "
                    "alias (case-sensitive) or declare it in initial_params if it is a parameter"
                )

    def fit_custom(
        self,
        expression: str,
        initial_params: dict[str, float] | None = None,
        target_transform: str | None = None,
        label: str = "",
        kind: str = "custom",
        problem: str = "static",
    ) -> ModelResult:
        """
        Fit a formula. problem="dynamic" fits a rate law: the expression is d(target)/dt
        over the state and the inputs, and the fitted law is simulated.
        """
        transform = self._check_transform(target_transform)
        variables, data = self._space(problem)
        initial_params = dict(initial_params or {})
        expr = parse_expression(expression, variables)
        self._check_identifiers(expr, initial_params, variables)
        if not expr.variables:
            raise ExpressionError(f"Expression must use at least one variable ({variables})")
        if len(expr.parameters) > 12:
            raise ExpressionError("At most 12 free parameters are allowed")
        self._check_categorical_use(expr)
        dynamic = problem == "dynamic"
        prefix = "D" if dynamic else {"custom": "M", "literature": "L", "classic": "C"}[kind]
        default_label = "Rate law" if dynamic else "Custom formula"
        result = ModelResult(
            model_id=self._new_id(prefix),
            kind=kind,
            name=label or kind,
            label=label or (default_label if kind == "custom" else "Published law"),
            expression=expr.source.replace("**", "^"),
            features=list(expr.variables),
            target_transform=transform,
            problem=problem,
        )
        p0 = dict.fromkeys(expr.parameters, 1.0) | {
            k: float(v) for k, v in initial_params.items() if k in expr.parameters
        }
        fit_model(
            result,
            expr,
            data,
            p0,
            seed=self.seed,
            other_features=self._others(list(expr.variables), problem),
        )
        if dynamic:
            self._attach_simulation(result)
        return self._register(result)

    def _check_categorical_use(self, expr) -> None:
        misused = names_outside_call(expr, self.categorical_features, "level")
        if misused:
            name = sorted(misused)[0]
            raise ExpressionError(
                f"{sorted(misused)} are integer-coded categories; use them only as "
                f"level({name}, k) indicators (levels: {self.levels[name]})"
            )

    def score_symbolic(
        self,
        equation: str,
        source: str,
        target_transform: str | None = None,
        problem: str = "static",
    ) -> ModelResult:
        """
        Score a PySR equation (or, for problem="dynamic", a SINDy rate law) like the
        other models: constants refit per CV fold. Not registered.
        """
        variables, data = self._space(problem)
        template, values = parameterize_constants(equation, taken=variables)
        expr = parse_expression(template, variables, parameters=list(values))
        # A category's integer code has no magnitude, so an equation using it as one is invalid.
        self._check_categorical_use(expr)
        dynamic = problem == "dynamic"
        result = ModelResult(
            model_id=self._new_id("D" if dynamic else "S"),
            kind="symbolic",
            name=source,
            label=f"{'SINDy' if dynamic else 'PySR'} ({source})",
            expression=equation.replace("**", "^"),
            features=list(expr.variables),
            target_transform=target_transform,
            source=source,
            problem=problem,
        )
        fit_model(
            result,
            expr,
            data,
            values,
            n_starts=1,
            seed=self.seed,
            other_features=self._others(list(expr.variables), problem),
        )
        return result

    def evaluate_symbolic(
        self, equation: str, source: str, target_transform: str | None = None
    ) -> ModelResult:
        return self._register(self.score_symbolic(equation, source, target_transform))

    def auto_screen(
        self, n_univariate: int = 3, n_multivariate: int = 4, priority: list[str] | None = None
    ) -> int:
        """
        Deterministic screen of the classic catalog (no LLM): every univariate family on
        the most important continuous features, multivariate families on the top ones.
        ``priority`` features (those the discovered equations use) come first. Runs after
        exploration, so the named laws are references the discoveries are compared with.
        """
        profiled = [f["alias"] for f in self.profile()["features"] if f["kind"] == "continuous"]
        ranked = list(dict.fromkeys([f for f in priority or [] if f in profiled] + profiled))
        fitted = 0
        for feature in ranked[:n_univariate]:
            for fam in (f for f in FAMILIES.values() if f.n_inputs == 1):
                try:
                    self.fit_family(fam.name, [feature])
                    fitted += 1
                except ValueError:
                    continue
        top = ranked[:n_multivariate]
        if len(top) >= 2:
            for fam in (f for f in FAMILIES.values() if f.n_inputs == 0):
                try:
                    self.fit_family(fam.name, top[: fam.max_inputs])
                    fitted += 1
                except ValueError:
                    continue
        # One step per category level: the classic baseline for an integer-coded category.
        # Kind "classic": it is a reference fitted after exploration, not an agent discovery.
        for feature in self.categorical_features[:n_univariate]:
            levels = self.levels[feature]
            prefix = next(
                (
                    p
                    for p in ("c", "k", "q", "w")
                    if not any(f.startswith(p) for f in self.features)
                ),
                None,
            )
            if prefix is None:
                break
            terms = [f"{prefix}0"] + [
                f"{prefix}{i}*level({feature}, {lv:g})" for i, lv in enumerate(levels[1:], 1)
            ]
            try:
                self.fit_custom(
                    " + ".join(terms), label=f"Level means of {feature}", kind="classic"
                )
                fitted += 1
            except ValueError:
                continue
        return fitted

    def leaderboard(
        self, top: int = 10, kind: str | None = None, problem: str = "static"
    ) -> list[dict[str, Any]]:
        """The agent's compact ranking; rate laws keep their equation (D ids say nothing)."""
        ranked = [m for m in self.ranked_models(problem) if kind is None or m.kind == kind]
        # cv_rmse stays: ties are judged on it (cv_se is its standard error)
        drop = {"aic", "reasons", "target_transform"}
        if problem == "static":
            drop.add("fitted")
        return [{k: v for k, v in m.brief().items() if k not in drop} for m in ranked[:top]]

    def note(
        self,
        kind: str,
        text: str,
        evidence: str = "",
        model_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if kind not in NOTE_KINDS:
            raise ValueError(f"kind must be one of {NOTE_KINDS}")
        ids = list(dict.fromkeys(model_ids or []))
        unknown = [m for m in ids if m not in self.models]
        if unknown:
            raise ValueError(f"Unknown model_ids {unknown}; cite ids returned by fits")
        entry = {
            "kind": kind,
            "text": str(text).strip()[:1000],
            "evidence": str(evidence or "").strip()[:300],
            "model_ids": ids,
            "t": round(self.elapsed_s, 1),
        }
        self.notebook.append(entry)
        return entry

    # ------------------------------------------------------------------
    # Dynamics (rate laws)
    # ------------------------------------------------------------------

    def _resolve_column(self, name: str | None) -> str | None:
        """An uploaded column by its name or by a feature alias."""
        if name in (None, "", "none", "None"):
            return None
        if name in self.raw_data.columns:
            return str(name)
        if name in self.column_of and self.column_of[name] in self.raw_data.columns:
            return self.column_of[name]  # not derived columns such as lags
        close = difflib.get_close_matches(str(name), [str(c) for c in self.raw_data.columns], n=1)
        hint = f" (did you mean '{close[0]}'?)" if close else ""
        raise ValueError(f"Unknown column {name!r}{hint}")

    def set_dynamics(self, time_column: str, group_column: str | None = None) -> DynamicsData:
        """Confirm a time structure and build the rate-of-change problem."""
        tcol = self._resolve_column(time_column)
        if tcol is None:
            raise ValueError("time_column is required")
        if tcol == self.target_column:
            raise ValueError("The target cannot be the time axis")
        gcol = self._resolve_column(group_column)
        if gcol in (tcol, self.target_column):
            raise ValueError("group_column must differ from the time column and the target")
        detected = self.time_structure
        if detected and detected.time_column == tcol and detected.group_column == gcol:
            structure = detected
        else:
            structure = TimeStructure(time_column=tcol, group_column=gcol, confidence="agent")
        # Uploaded columns only (not derived ones such as lags): a rate law's inputs are
        # interpolated along time from the raw data
        inputs = {
            a: self.column_of[a]
            for a in self.continuous_features
            if self.column_of[a] not in (tcol, gcol) and self.column_of[a] in self.raw_data
        }
        previous = self.dynamics
        self.dynamics = build_dynamics(
            self.raw_data, structure, self.target_column, self.target_alias, inputs, seed=self.seed
        )
        old_axes = previous and (previous.structure.time_column, previous.structure.group_column)
        if old_axes and old_axes != (tcol, gcol):
            # Laws fitted on the old derivative data are not comparable with the new ones.
            for m in self.snapshot():
                if m.problem == "dynamic" and not m.error:
                    m.error = (
                        f"superseded: fitted along {old_axes[0]} before set_dynamics changed "
                        "the time structure"
                    )
        return self.dynamics

    def _require_dynamics(self) -> DynamicsData:
        if self.dynamics is None:
            raise ValueError(
                "No time structure confirmed yet: call set_dynamics(time_column, group_column) first"
            )
        return self.dynamics

    def simulate_model(self, m: ModelResult, holdout: bool = False, traces: bool = False):
        """Integrate a rate law over the training (or held-out) trajectories."""
        dyn = self._require_dynamics()
        episodes = dyn.holdout_episodes if holdout else dyn.train_episodes
        return simulate(m.parsed, m.params, dyn.state, episodes, dyn.fill_value, traces=traces)

    def _attach_simulation(self, m: ModelResult) -> ModelResult:
        """Integrate a fitted rate law over the training trajectories (agent feedback)."""
        if m.error or m.parsed is None:
            return m
        sim = self.simulate_model(m)
        if sim is None:
            return m
        m.diagnostics["simulation"] = sim
        if sim["n_diverged"]:
            m.reasons.insert(
                0,
                f"simulation diverges or fails on {sim['n_diverged']} of {sim['n_episodes']} "
                "training trajectories",
            )
        elif sim["r2"] < 0.5:
            m.reasons.append(
                f"fits the derivative but the integrated law tracks the trajectories poorly "
                f"(simulation R2 {sim['r2']:.3f})"
            )
        else:
            m.reasons.append(
                f"simulated trajectories reproduce the data (simulation R2 {sim['r2']:.3f})"
            )
        return m

    # ------------------------------------------------------------------
    # PySR searches
    # ------------------------------------------------------------------

    def _check_guess(
        self, guess: str, features: list[str], unary: list[str], binary: list[str]
    ) -> str | None:
        """Why PySR could not use this guess, or None if it can."""
        try:
            expr = parse_expression(guess, features, parameters=())
        except ExpressionError as e:
            return f"not a closed formula over {features}: {e}"
        funcs, binops = operators_used(expr)
        for f in sorted(funcs):
            if f in ("square", "cube") and "^" in binary:
                continue
            if f not in unary:
                return f"uses {f}() which is not among the unary operators {unary}"
        missing = sorted(b for b in binops if b not in binary)
        if missing:
            return f"uses {missing} which are not among the binary operators {binary}"
        return None

    def shap_seed_guesses(
        self, features: list[str], transform: str | None, unary: list[str], binary: list[str]
    ) -> list[str]:
        """
        Warm-start seeds from the strongest reliable SHAP interaction among ``features``:
        ``c0 + c1*a*b`` and ``c0 + c1*a/b``, constants by least squares in the search's
        target space. Empty without a profile (the baseline search starts before it).
        """
        shap = (self._profile or {}).get("shap") or {}
        pair = next(
            (p for p in shap.get("interactions", []) if p["a"] in features and p["b"] in features),
            None,
        )
        if not shap.get("reliable") or pair is None:
            return []
        z = target_space(self.fit_data.y, transform)
        if not np.all(np.isfinite(z)):
            return []
        a, b = pair["a"], pair["b"]
        xa, xb = self.fit_data.X[a], self.fit_data.X[b]
        seeds = []
        with np.errstate(all="ignore"):
            terms = {f"{a}*{b}": xa * xb, f"{a}/{b}": xa / xb}
        for expr, t in terms.items():
            if not np.all(np.isfinite(t)):
                continue
            coef, *_ = np.linalg.lstsq(np.column_stack([np.ones_like(t), t]), z, rcond=None)
            c0, c1 = (float(c) for c in coef)
            if c1 < 0 and "-" in binary:
                seeds.append(f"{c0:.6g} - {-c1:.6g}*{expr}")
            else:
                seeds.append(f"{c0:.6g} + {c1:.6g}*{expr}")
        # Only seeds this search's operators can express.
        return [g for g in seeds if self._check_guess(g, features, unary, binary) is None]

    def weak_features(self, features: list[str]) -> list[str]:
        """Features with a negligible SHAP share and no permutation importance."""
        profile = self._profile or {}
        if not (profile.get("shap") or {}).get("reliable"):
            return []
        weak = []
        for d in profile.get("features", []):
            share, imp = d.get("shap_share"), d.get("permutation_importance")
            if d["alias"] not in features or share is None or imp is None:
                continue
            if share < NEGLIGIBLE_SHARE and imp <= (d.get("permutation_importance_sd") or 0.0):
                weak.append(d["alias"])
        return weak

    def _validate_search(
        self,
        features: list[str],
        unary_operators: list[str],
        binary_operators: list[str],
        maxsize: int | None,
        niterations: int | None,
    ) -> dict[str, Any]:
        self._require_features(features)
        categorical = [f for f in features if f in self.categorical_features]
        if categorical:
            raise ValueError(
                f"{categorical} are integer-coded categories; PySR would treat their codes as "
                "magnitudes. Search on continuous features and model category effects with "
                "fit_formula and level(name, k) indicators."
            )
        bad_u = [u for u in unary_operators if u not in ALLOWED_UNARY]
        bad_b = [b for b in binary_operators if b not in ALLOWED_BINARY]
        if bad_u or bad_b:
            raise ValueError(
                f"Unsupported operators {bad_u + bad_b}. Unary: {ALLOWED_UNARY}; binary: {ALLOWED_BINARY}"
            )
        if not binary_operators:
            raise ValueError("At least one binary operator is required")
        maxsize = int(np.clip(maxsize or 20, 7, 40))
        timeout = int(min(self.budget.pysr_timeout_s, max(120, self.remaining_s - 120)))
        return {
            "unary_operators": list(dict.fromkeys(unary_operators)),
            "binary_operators": list(dict.fromkeys(binary_operators)),
            "maxsize": maxsize,
            "maxdepth": min(maxsize, 12),
            "niterations": int(np.clip(niterations, 50, 5000)) if niterations else None,
            "timeout_in_seconds": timeout,
        }

    def pysr_input(
        self,
        features: list[str],
        target_transform: str | None,
        config: dict[str, Any],
        guesses: list[str],
    ) -> dict[str, Any]:
        """Worker input for one search: training split only, aliased columns."""
        frame = self.train
        if len(frame) > MAX_PYSR_ROWS:
            frame = frame.sample(n=MAX_PYSR_ROWS, random_state=self.seed)
        return {
            "data": frame[[self.target_alias, *features]].to_dict(orient="split"),
            "target_column": self.target_alias,
            "predictor_columns": features,
            "target_transform": target_transform,
            "guesses": [g.replace("**", "^") for g in guesses],
            "config": config,
            "return_full_front": True,
        }

    async def start_search(
        self,
        features: list[str],
        unary_operators: list[str],
        binary_operators: list[str],
        maxsize: int | None = None,
        niterations: int | None = None,
        target_transform: str | None = None,
        guesses: list[str] | None = None,
        guess_model_ids: list[str] | None = None,
        rationale: str = "",
        enforce_budget: bool = True,
        template: str | None = None,
    ) -> SearchRecord:
        if self.launchers.get("pysr") is None:
            raise RuntimeError("No PySR launcher configured")
        if self.cancelled:
            raise BudgetExhausted("The run was cancelled")
        if enforce_budget:
            if self._n_searches("pysr") >= self.budget.max_pysr_runs:
                raise BudgetExhausted(
                    f"PySR search budget used ({self.budget.max_pysr_runs}); refine with fit_formula or finish"
                )
            running = self._n_searches("pysr", running=True)
            if running >= self.budget.max_concurrent_pysr:
                raise ValueError(
                    f"{running} searches already running (max {self.budget.max_concurrent_pysr}); "
                    "wait for or cancel one first"
                )
        transform = self._check_transform(target_transform)
        config = self._validate_search(
            features, unary_operators, binary_operators, maxsize, niterations
        )
        candidates = [g for g in (guesses or []) if g and str(g).strip()]
        rejected: list[dict[str, str]] = []
        template = (template or "").strip()
        if template:
            calls = parse_template(template, list(features))
            config["template"] = template
            config["template_expressions"] = list(dict.fromkeys(name for name, _ in calls))
            # PySR warm-starts a template only from its parts, not from a closed formula
            rejected += [
                {"guess": g, "reason": "a templated search takes no closed-formula seeds"}
                for g in [*candidates, *(guess_model_ids or [])]
            ]
            candidates, guess_model_ids = [], []

        for mid in guess_model_ids or []:
            m = self.models.get(mid)
            if m is None or m.error:
                rejected.append({"guess": mid, "reason": "unknown or failed model"})
            elif m.target_transform != transform:
                rejected.append(
                    {
                        "guess": mid,
                        "reason": f"{mid} was fit with target_transform={m.target_transform}, "
                        f"this search uses {transform}",
                    }
                )
            else:
                candidates.append(m.fitted_core)
        shap_seeds: list[str] = []
        if not candidates and not rejected and "template" not in config:
            shap_seeds = self.shap_seed_guesses(
                features, transform, config["unary_operators"], config["binary_operators"]
            )
            candidates = list(shap_seeds)
        accepted = []
        for g in candidates:
            reason = self._check_guess(
                g, features, config["unary_operators"], config["binary_operators"]
            )
            if reason:
                rejected.append({"guess": g, "reason": reason})
            elif g not in accepted:
                accepted.append(g)
        accepted = accepted[:5]

        search_id = f"pysr_{self._n_searches('pysr') + 1}"
        record = SearchRecord(
            search_id=search_id,
            features=list(features),
            config=config,
            target_transform=transform,
            guesses=accepted,
            rejected_guesses=rejected,
            seeded_from_shap=bool(shap_seeds) and bool(accepted),
            rationale=str(rationale).strip()[:500],
        )
        return await self._launch(record, self.pysr_input(features, transform, config, accepted))

    async def start_sindy_search(
        self,
        features: list[str] | None = None,
        degree: int = 2,
        extra_functions: list[str] | None = None,
        include_state: bool = True,
        rationale: str = "",
    ) -> SearchRecord:
        """Launch a SINDy search for the rate law over the state and the given inputs."""
        if self.launchers.get("sindy") is None:
            raise RuntimeError("No SINDy launcher configured")
        if self.cancelled:
            raise BudgetExhausted("The run was cancelled")
        dyn = self._require_dynamics()
        if self._n_searches("sindy") >= self.budget.max_sindy_runs:
            raise BudgetExhausted(
                f"SINDy search budget used ({self.budget.max_sindy_runs}); refine with fit_ode or finish"
            )
        features = [f for f in dict.fromkeys(features or []) if f != dyn.state]
        unknown = [f for f in features if f not in dyn.inputs]
        if unknown:
            raise ValueError(f"{unknown} are not inputs of the rate law; inputs: {dyn.inputs}")
        variables = ([dyn.state] if include_state else []) + features
        if not variables:
            raise ValueError("Include the state or at least one input")
        if len(variables) > 6:
            raise ValueError("At most 6 variables (the library grows combinatorially)")
        extra = [f for f in dict.fromkeys(extra_functions or []) if f]
        bad = [f for f in extra if f not in SINDY_FUNCTIONS]
        if bad:
            raise ValueError(f"Unsupported extra functions {bad}; allowed: {SINDY_FUNCTIONS}")
        config = {
            "degree": int(np.clip(degree, 1, 3)),
            "extra_functions": extra,
            "include_state": bool(include_state),
            "timeout_in_seconds": SINDY_TIMEOUT_S,
        }
        record = SearchRecord(
            search_id=f"sindy_{self._n_searches('sindy') + 1}",
            features=variables,
            config=config,
            target_transform=None,
            guesses=[],
            rationale=str(rationale).strip()[:500],
            engine="sindy",
        )
        input_data = {
            "X": {v: dyn.fit_data.X[v] for v in variables},
            "dydt": dyn.fit_data.y,
            "variables": variables,
            "degree": config["degree"],
            "extra_functions": extra,
        }
        return await self._launch(record, input_data)

    async def _launch(self, record: SearchRecord, input_data: dict[str, Any]) -> SearchRecord:
        search_id = record.search_id
        self.searches[search_id] = record
        record.task = asyncio.create_task(self._run_search(record, input_data))
        await self.emit(
            "search_started",
            f"Started {search_id} on {', '.join(record.features)}"
            + (f" — {record.rationale}" if record.rationale else ""),
            search_id=search_id,
            features=record.features,
            rationale=record.rationale,
        )
        return record

    def _set_job_id(self, record: SearchRecord, job_id: str) -> None:
        record.job_id = job_id

    async def _run_search(self, record: SearchRecord, input_data: dict[str, Any]) -> None:
        launcher = self.launchers[record.engine]
        try:
            submit = asyncio.ensure_future(
                launcher.submit(
                    record.search_id, input_data, lambda jid: self._set_job_id(record, jid)
                )
            )
            try:
                # Shielded: a cancel during the submit round trip must not lose the job id.
                job_id = await asyncio.shield(submit)
            except asyncio.CancelledError:
                # Let the submit finish (one HTTP round trip) so its job can be cancelled.
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(submit, timeout=60)
                    await self._cancel_job(submit.result(), record.search_id)
                raise
            record.job_id = job_id
            if record.status == "cancelled":
                await self._cancel_job(job_id, record.search_id)
                return
            record.status = "queued"
            ok, result, error = await launcher.wait(job_id)
            if record.status == "cancelled":
                return
            if not ok or not result:
                record.status = "failed"
                record.error = error or "search failed without an error message"
                await self.emit(
                    "search_failed",
                    f"{record.search_id} failed: {record.error[:200]}",
                    search_id=record.search_id,
                )
                if "unrecognized arguments" in record.error or "--task-key" in record.error:
                    self.note(
                        "data_issue",
                        "The Slurm worker image is older than the backend (it rejects --task-key); "
                        "rebuild and redeploy syxplain-worker.sif.",
                    )
                return
            equations = result.get("equations") or []
            record.n_front = len(equations)
            record.status = "ingesting"
            scored = await asyncio.to_thread(self._score_front, record, equations)
            if record.status == "cancelled":
                return
            if (
                record.config.get("template")
                and equations
                and not any("=" in str(e.get("equation") or "") for e in equations)
            ):
                # A worker older than 3.1 ignores the template and returns plain formulas
                self.note(
                    "data_issue",
                    f"{record.search_id} ignored its template (the Slurm worker image predates "
                    "templated searches); rebuild and redeploy syxplain-worker.sif.",
                )
            for model in scored:  # single writer: registration happens on the loop
                self._register(model)
                record.model_ids.append(model.model_id)
            record.status = "completed"
            summary = record.summary(self.models)
            n = summary.get("n_equations", 0)
            await self.emit(
                "search_completed",
                f"{record.search_id} completed: {n} equations"
                + (
                    f", best {summary['best_model_id']} CV R2 {summary['best_cv_r2']}"
                    if n
                    else " (none could be scored)"
                ),
                search_id=record.search_id,
                n_equations=n,
                **(self.models[summary["best_model_id"]].event_fields() if n else {}),
            )
        except asyncio.CancelledError:
            # _cancel_job is idempotent, so a job cancel_search() already sent is not repeated.
            record.status = "cancelled"
            if record.job_id:
                await asyncio.shield(self._cancel_job(record.job_id, record.search_id))
            raise
        except Exception as e:
            logger.warning(f"Search {record.search_id} crashed: {e}", exc_info=True)
            record.status = "failed"
            record.error = str(e)
            await self.emit(
                "search_failed",
                f"{record.search_id} failed: {record.error[:200]}",
                search_id=record.search_id,
            )
        finally:
            record.finished_at = time.monotonic()

    def _score_front(
        self, record: SearchRecord, equations: list[dict[str, Any]]
    ) -> list[ModelResult]:
        """Score a PySR hall of fame or a SINDy front (pure: nothing is registered here)."""
        problem = "dynamic" if record.engine == "sindy" else "static"
        if len(equations) > MAX_FRONT:
            by_loss = sorted(equations, key=lambda e: e.get("loss", np.inf))[:30]
            by_size = sorted(equations, key=lambda e: e.get("complexity", 0))[:10]
            keep = {id(e) for e in by_loss + by_size}
            equations = [e for e in equations if id(e) in keep]
        scored = []
        template = record.config.get("template")
        for eq in equations:
            text = eq.get("equation") or ""
            try:
                if template:
                    text = compose_template(template, text)
                model = self.score_symbolic(
                    text, record.search_id, record.target_transform, problem=problem
                )
            except ExpressionError as e:
                logger.info(f"Could not parse {record.engine} equation {text!r}: {e}")
                continue
            model.diagnostics[f"{record.engine}_loss"] = eq.get("loss")
            model.diagnostics[f"{record.engine}_complexity"] = eq.get("complexity")
            if template:
                model.diagnostics["template_parts"] = eq.get("equation")
            model.diagnostics["structure_selected_in_sample"] = True
            scored.append(model)
        if problem == "dynamic":
            # Integrate the most accurate laws and the sparsest ones (the selection vetoes
            # unsimulated laws, and prefers the simplest law within one standard error).
            ok = [m for m in scored if not m.error and m.cv_r2 is not None]
            best = sorted(ok, key=lambda m: -m.cv_r2)[:N_SIMULATED_PER_SEARCH]
            simple = self.pareto(ok)[:N_SIMULATED_PER_SEARCH]
            for m in {m.model_id: m for m in [*best, *simple]}.values():
                self._attach_simulation(m)
        return scored

    def mark_read(self, search_id: str) -> None:
        record = self._get_search(search_id)
        if record.status == "completed":
            record.read_at = time.monotonic()

    async def wait_any(self, search_ids: list[str] | None, max_wait_s: float) -> list[SearchRecord]:
        """Wait until any of the searches finishes (or the wait cap). Returns finished ones."""
        records = (
            [self._get_search(s) for s in search_ids]
            if search_ids
            else list(self.searches.values())
        )
        pending = [r.task for r in records if r.task and not r.done]
        if pending:
            cap = max(1.0, min(max_wait_s, self.remaining_s - 180))
            await asyncio.wait(
                [asyncio.shield(t) for t in pending],
                timeout=cap,
                return_when=asyncio.FIRST_COMPLETED,
            )
        return [r for r in records if r.done]

    async def _cancel_job(self, job_id: str, search_id: str) -> None:
        record = self.searches.get(search_id)
        launcher = self.launchers.get(record.engine if record else "pysr")
        if not launcher or job_id in self._cancelled_jobs:
            return
        self._cancelled_jobs.add(job_id)
        try:
            await launcher.cancel(job_id)
        except Exception as e:
            logger.warning(f"Failed to cancel {search_id}: {e}")

    async def _stop_search(self, record: SearchRecord) -> None:
        if record.job_id:
            await self._cancel_job(record.job_id, record.search_id)
        if record.task and not record.task.done():
            record.task.cancel()
            # A search cancelled mid-submit cancels its own job once the id arrives.
            with contextlib.suppress(BaseException):
                await record.task

    async def cancel_search(self, search_id: str) -> SearchRecord:
        record = self._get_search(search_id)
        if record.done:
            return record
        if record.status == "ingesting" and record.task:
            # Results are already back; let scoring finish rather than lose them.
            with contextlib.suppress(Exception):
                await asyncio.shield(record.task)
            return record
        record.status = "cancelled"
        record.finished_at = time.monotonic()
        # Shielded: the Slurm cancel must go out even if our caller is cancelled now.
        await asyncio.shield(self._stop_search(record))
        await self.emit("search_cancelled", f"Cancelled {search_id}", search_id=search_id)
        return record

    async def cancel_all(self) -> None:
        for s in list(self.searches.values()):
            if not s.done:
                with contextlib.suppress(Exception):
                    await self.cancel_search(s.search_id)

    def _get_search(self, search_id: str) -> SearchRecord:
        if search_id not in self.searches:
            raise ValueError(f"Unknown search {search_id!r}. Known: {list(self.searches)}")
        return self.searches[search_id]

    async def ensure_result(self, grace_s: float, max_wait_s: float) -> None:
        """
        Settle all searches before scoring.

        Running searches get ``grace_s`` to finish. If none has completed by then,
        keep waiting (up to ``max_wait_s`` in total) for the first one to finish.
        Whatever is still running afterwards is cancelled.
        """
        start = time.monotonic()

        def pending() -> list[asyncio.Task]:
            return [s.task for s in self.searches.values() if s.task and not s.done]

        if pending():
            await asyncio.wait(pending(), timeout=max(0.0, grace_s))
        # The static analysis needs a PySR result: a (fast) SINDy search does not count.
        while pending() and not any(
            s.status == "completed" and s.engine == "pysr" for s in self.searches.values()
        ):
            left = max_wait_s - (time.monotonic() - start)
            if left <= 0:
                break
            await asyncio.wait(pending(), timeout=left, return_when=asyncio.FIRST_COMPLETED)
        await self.cancel_all()

    # ------------------------------------------------------------------
    # Final scoring
    # ------------------------------------------------------------------

    def final_scoring(self) -> None:
        """Score every model once on the holdout (display only; ranking uses CV)."""
        if not self.has_holdout:
            return  # never report in-sample numbers as held-out
        X = {f: self.holdout[f].to_numpy(dtype=float) for f in self.features}
        y = self.holdout[self.target_alias].to_numpy(dtype=float)
        fill = float(self.train[self.target_alias].mean())
        for m in self.snapshot():
            # Rate laws are scored by simulation, only for the ones reported (report.py).
            if m.error or m.parsed is None or m.problem != "static":
                continue
            m.holdout = score_holdout(m.parsed, m.params, X, y, m.target_transform, fill)

    def partial_dependence(
        self,
        model: ModelResult,
        feature: str,
        values: np.ndarray,
        background: dict[str, np.ndarray],
    ) -> np.ndarray:
        """
        The equation's mean prediction with ``feature`` set to each of ``values`` and
        the other features taken from every background row (NaN where undefined).
        """
        n, k = len(values), len(next(iter(background.values())))
        X = {g: np.tile(v, n) for g, v in background.items() if g != feature}
        X[feature] = np.repeat(values, k)
        pred = predict(model.parsed, model.params, X, model.target_transform).reshape(n, -1)
        with np.errstate(all="ignore"):
            return np.nanmean(np.where(np.isfinite(pred), pred, np.nan), axis=1)

    def shap_agreement(
        self, model: ModelResult | None, max_features: int = 6, background: int = 100
    ) -> list[dict[str, Any]]:
        """
        Does the equation move with each important feature the way the data does?
        Compares the equation's centred partial dependence on a feature (averaged over
        background rows) with the forest's SHAP effect, on the SHAP sample rows.
        Empty without reliable SHAP.
        """
        shap = (self._profile or {}).get("shap") or {}
        if model is None or model.parsed is None or self._shap_sample is None:
            return []
        if not shap.get("reliable"):
            return []
        Xs, values = self._shap_sample
        n = len(Xs)
        bg = np.random.default_rng(self.seed).choice(n, size=min(background, n), replace=False)
        others = {g: Xs[bg, self.features.index(g)] for g in model.features if g in self.features}
        out = []
        for d in shap.get("importance", [])[:max_features]:
            f = d["feature"]
            if d["share"] < NEGLIGIBLE_SHARE or self.kinds.get(f) == "categorical":
                continue
            j = self.features.index(f)
            item: dict[str, Any] = {"feature": f, "shap_share": d["share"]}
            out.append(item)
            if f not in model.features:
                item |= {
                    "verdict": "ignored",
                    "note": f"the equation does not use {f}, which carries "
                    f"{d['share']:.0%} of the SHAP attribution",
                }
                continue
            pdp = self.partial_dependence(model, f, Xs[:, j], others)
            effect = values[:, j]
            ok = np.isfinite(pdp)
            if ok.sum() < 5 or np.ptp(pdp[ok]) == 0 or np.ptp(effect[ok]) == 0:
                item |= {"verdict": "undetermined", "note": "no variation to compare"}
                continue
            rho = float(stats.spearmanr(pdp[ok], effect[ok]).statistic)
            ratio = float(np.std(pdp[ok]) / np.std(effect[ok]))
            item |= {
                # |rho| < 0.5 is no clear relation either way, not a reversed effect
                "verdict": "opposite" if rho <= -0.5 else "disagrees" if rho < 0.5 else "agrees",
                "spearman_rho": round(rho, 3),
                "effect_size_ratio": round(ratio, 2),
                "note": (
                    f"equation vs SHAP effect of {f}: rank correlation {rho:.2f}, "
                    f"effect size {ratio:.2f}x the forest's"
                ),
            }
        return out

    def scatter(self, model: ModelResult, max_points: int = 500) -> dict[str, Any] | None:
        """Measured vs predicted on the holdout, or out-of-fold CV predictions without one."""
        rng = np.random.default_rng(self.seed)
        if self.has_holdout:
            if model.parsed is None:
                return None
            X = {f: self.holdout[f].to_numpy(dtype=float) for f in self.features}
            y = self.holdout[self.target_alias].to_numpy(dtype=float)
            pred = predict(model.parsed, model.params, X, model.target_transform)
            basis = "holdout"
        else:
            if model.oof_pred is None:
                return None
            y, pred, basis = self.fit_data.y, model.oof_pred, "cv_oof"
        ok = np.isfinite(pred)
        idx = np.where(ok)[0]
        if len(idx) == 0:
            return None
        if len(idx) > max_points:
            idx = np.sort(rng.choice(idx, max_points, replace=False))
        out: dict[str, Any] = {
            "measured": y[idx].tolist(),
            "predicted": pred[idx].tolist(),
            "basis": basis,
        }
        if (~ok).any():
            out["note"] = f"model undefined on {int((~ok).sum())} rows (not plotted)"
        return out

    def ranked_models(self, problem: str = "static") -> list[ModelResult]:
        """
        All usable models of a problem by cross-validated R2 (the holdout never ranks).
        Rate laws are scored on the derivative, so problem="dynamic" ranks them apart.
        """
        return sorted(
            (m for m in self.snapshot() if not m.error and m.problem == problem),
            key=lambda m: -(m.cv_r2 if m.cv_r2 is not None else -np.inf),
        )

    @staticmethod
    def pareto(models: list[ModelResult]) -> list[ModelResult]:
        """Models not dominated in (complexity, CV RMSE)."""

        def err(m: ModelResult) -> float:
            return m.cv_rmse if m.cv_rmse is not None else np.inf

        front, best = [], np.inf
        for m in sorted(models, key=lambda m: (m.complexity, err(m))):
            if err(m) < best:
                front.append(m)
                best = err(m)
        return front
