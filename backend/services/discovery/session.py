"""
Discovery session: shared state for one agentic equation-discovery run.

Owns the data contract (aliases, variable kinds, missingness, train/holdout split),
the model registry, the lab notebook, the budget, the PySR searches and the agent's
view of the world (state line, event inbox). Tools (``tools.py``) are thin wrappers
around these methods; the orchestrator, reconciler and selector read from here.
"""

import asyncio
import contextlib
import difflib
import logging
import re
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import pandas as pd

from backend.services.discovery.expression import (
    ExpressionError,
    alias_base,
    make_alias,
    names_outside_call,
    operators_used,
    parameterize_constants,
    parse_expression,
)
from backend.services.discovery.families import FAMILIES
from backend.services.discovery.fitting import (
    TRANSFORMS,
    FitData,
    ModelResult,
    fit_model,
    predict,
    score_holdout,
)
from backend.services.discovery.profiling import (
    collinear_pairs,
    compute_profile,
    compute_profile_async,
    describe_features,
    profile_shape,
)

logger = logging.getLogger(__name__)

ALLOWED_UNARY = ("exp", "log", "sqrt", "abs", "sin", "cos", "tanh", "square", "cube", "inv", "neg")
ALLOWED_BINARY = ("+", "-", "*", "/", "^")
NOTE_KINDS = ("hypothesis", "rejected_form", "candidate", "data_issue", "insight")
TARGET_TRANSFORMS = ("none", "log", "log1p", "sqrt")
MAX_PYSR_ROWS = 10000
MAX_FRONT = 40  # equations ingested per search (30 most accurate + 10 simplest)
MIN_HOLDOUT_ROWS = 40  # below this, every metric is out-of-fold CV
INBOX_KINDS = ("search_completed", "search_failed", "search_cancelled", "literature", "data_issue")
CATEGORICAL_WORDS = re.compile(
    r"\b(code|coded|class|classes|type|category|categorical|group|id)\b", re.I
)
MODEL_ID_RE = re.compile(r"\b[CMSL]\d+\b")


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
    """One PySR search launched by the agent or the orchestrator."""

    search_id: str
    features: list[str]
    config: dict[str, Any]
    target_transform: str | None
    guesses: list[str]
    rationale: str
    rejected_guesses: list[dict[str, str]] = field(default_factory=list)
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
            "status": self.status,
            "features": self.features,
            "unary_operators": self.config.get("unary_operators"),
            "binary_operators": self.config.get("binary_operators"),
            "maxsize": self.config.get("maxsize"),
            "niterations": self.config.get("niterations"),
            "target_transform": self.target_transform,
            "guesses": self.guesses,
            "rejected_guesses": self.rejected_guesses,
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
    ):
        self.budget = budget or DiscoveryBudget()
        self.launcher = launcher
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
        self.known_laws: dict[str, Any] | None = None
        self.literature_task: asyncio.Task | None = None
        self.agent_finished_at: float | None = None
        self.cancelled = False
        self._lock = threading.Lock()
        self._model_counter = 0
        self._profile: dict[str, Any] | None = None
        self._shap_sample: tuple[np.ndarray, np.ndarray] | None = None
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
        self.dropped_incomplete = self.n_uploaded - len(frame)
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

        # --- split ------------------------------------------------------------
        self.n_rows = len(frame)
        rng = np.random.default_rng(seed)
        order = rng.permutation(len(frame))
        n_holdout = round(holdout_fraction * len(frame)) if len(frame) >= MIN_HOLDOUT_ROWS else 0
        self.holdout = frame.iloc[order[:n_holdout]].reset_index(drop=True)
        self.train = frame.iloc[order[n_holdout:]].reset_index(drop=True)
        fit_frame = (
            self.train.sample(n=max_fit_rows, random_state=seed)
            if len(self.train) > max_fit_rows
            else self.train
        )
        y = fit_frame[self.target_alias].to_numpy(dtype=float)
        n_folds = 5 if len(y) >= 25 else 3
        folds = np.array_split(rng.permutation(len(y)), n_folds)
        self.fit_data = FitData(
            X={f: fit_frame[f].to_numpy(dtype=float) for f in self.features},
            y=y,
            folds=folds,
        )

        for col in self.excluded_columns:
            self.note("data_issue", f"Column '{col['column']}' excluded: {col['reason']}")

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

    def split_info(self) -> dict[str, Any]:
        return {
            "complete_rows": self.n_rows,
            "train": len(self.train),
            "holdout": len(self.holdout),
            "has_holdout": self.has_holdout,
            "regime": "holdout" if self.has_holdout else "cv_only",
            "metric_basis": self.metric_basis,
            "scored_on": (
                f"{len(self.holdout)} held-out rows"
                if self.has_holdout
                else f"out-of-fold cross-validation ({len(self.fit_data.folds)} folds; "
                f"fewer than {MIN_HOLDOUT_ROWS} rows, no holdout)"
            ),
            "uploaded": self.n_uploaded,
            "dropped_incomplete": self.dropped_incomplete,
            "missing_by_column": self.missing_by_column,
            "excluded_columns": self.excluded_columns,
        }

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
            "pysr_searches_used": len(self.searches),
            "pysr_searches_max": self.budget.max_pysr_runs,
            "pysr_running": sum(1 for s in self.searches.values() if not s.done),
        }

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
        """Events the agent has not seen yet (search results, literature, data issues)."""
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

    def _profile_inputs(self) -> tuple[np.ndarray, np.ndarray, list[str], list[bool]]:
        X = np.column_stack([self.fit_data.X[f] for f in self.features])
        cat = [self.kinds.get(f) == "categorical" for f in self.features]
        return X, self.fit_data.y, list(self.features), cat

    async def ensure_profile(self, timeout_s: float = 240) -> dict[str, Any]:
        """Compute the profile in the profiling process (keeps the event loop free)."""
        if self._profile is not None:
            return self._profile
        X, y, names, cat = self._profile_inputs()
        try:
            raw = await compute_profile_async(X, y, names, cat, seed=self.seed, timeout_s=timeout_s)
        except asyncio.TimeoutError:
            logger.warning("Profiling timed out; continuing with a light profile")
            raw = None
        except Exception as e:
            logger.warning(f"Profiling process failed ({e}); computing in a thread")
            raw = await asyncio.to_thread(compute_profile, X, y, names, cat, self.seed)
        return self._assemble_profile(raw)

    def profile(self) -> dict[str, Any]:
        """Synchronous profile (in-process); used by scripts, tests and fallbacks."""
        if self._profile is not None:
            return self._profile
        X, y, names, cat = self._profile_inputs()
        return self._assemble_profile(compute_profile(X, y, names, cat, self.seed))

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
            "rows": p["rows"],
            "noise_ceiling_r2": p["noise_ceiling_r2"],
            "noise_ceiling_sd": p["noise_ceiling_sd"],
            "has_signal": p["has_signal"],
            "features_ranked": feats,
            "more_features": max(0, len(p["features"]) - max_features),
            "shap_interactions": shap.get("interactions", []) if shap.get("reliable", True) else [],
            "shap_reliable": shap.get("reliable"),
            "collinear_pairs": p["collinear_pairs"][:6],
            "excluded_columns": p["excluded_columns"],
        }

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

    def _others(self, used: list[str]) -> list[str]:
        return [f for f in self.continuous_features if f not in used]

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
        y = self.fit_data.y
        fwd, _ = TRANSFORMS[transform]
        with np.errstate(all="ignore"):
            z = fwd(y) if transform else y
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

    def _check_identifiers(self, expr, initial_params: dict[str, float]) -> None:
        """Unbound identifiers that look like features are almost always typos."""
        lowered = {f.lower(): f for f in self.features}
        columns = {str(c): a for c, a in self.alias_of.items()}
        for name in expr.parameters:
            if name in initial_params:
                continue
            match = lowered.get(name.lower()) or columns.get(name)
            if match is None and len(name) > 2:
                close = difflib.get_close_matches(name, self.features, n=1, cutoff=0.8)
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
    ) -> ModelResult:
        transform = self._check_transform(target_transform)
        initial_params = dict(initial_params or {})
        expr = parse_expression(expression, self.features)
        self._check_identifiers(expr, initial_params)
        if not expr.variables:
            raise ExpressionError(
                f"Expression must use at least one feature (aliases: {self.features})"
            )
        if len(expr.parameters) > 12:
            raise ExpressionError("At most 12 free parameters are allowed")
        misused = names_outside_call(expr, self.categorical_features, "level")
        if misused:
            name = sorted(misused)[0]
            raise ExpressionError(
                f"{sorted(misused)} are integer-coded categories; use them only as "
                f"level({name}, k) indicators (levels: {self.levels[name]})"
            )
        prefix = {"custom": "M", "literature": "L"}[kind]
        result = ModelResult(
            model_id=self._new_id(prefix),
            kind=kind,
            name=label or kind,
            label=label or ("Custom formula" if kind == "custom" else "Published law"),
            expression=expr.source.replace("**", "^"),
            features=list(expr.variables),
            target_transform=transform,
        )
        p0 = dict.fromkeys(expr.parameters, 1.0) | {
            k: float(v) for k, v in initial_params.items() if k in expr.parameters
        }
        fit_model(
            result,
            expr,
            self.fit_data,
            p0,
            seed=self.seed,
            other_features=self._others(list(expr.variables)),
        )
        return self._register(result)

    def score_symbolic(
        self, equation: str, source: str, target_transform: str | None = None
    ) -> ModelResult:
        """Score a PySR equation like the classic models (constants refit per CV fold). Not registered."""
        template, values = parameterize_constants(equation, taken=self.features)
        expr = parse_expression(template, self.features, parameters=list(values))
        result = ModelResult(
            model_id=self._new_id("S"),
            kind="symbolic",
            name=source,
            label=f"PySR ({source})",
            expression=equation.replace("**", "^"),
            features=list(expr.variables),
            target_transform=target_transform,
            source=source,
        )
        fit_model(
            result,
            expr,
            self.fit_data,
            values,
            n_starts=1,
            seed=self.seed,
            other_features=self._others(list(expr.variables)),
        )
        return result

    def evaluate_symbolic(
        self, equation: str, source: str, target_transform: str | None = None
    ) -> ModelResult:
        return self._register(self.score_symbolic(equation, source, target_transform))

    def auto_screen(self, n_univariate: int = 3, n_multivariate: int = 4) -> int:
        """
        Deterministic screen of the classic catalog (no LLM): every univariate family on
        the most important continuous features, multivariate families on the top ones.
        Used when the agent is disabled or failed, so classic baselines always exist.
        """
        ranked = [f["alias"] for f in self.profile()["features"] if f["kind"] == "continuous"]
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
        return fitted

    def leaderboard(self, top: int = 10, kind: str | None = None) -> list[dict[str, Any]]:
        ranked = [m for m in self.ranked_models() if kind is None or m.kind == kind]
        return [
            {
                "model_id": m.model_id,
                "name": m.name,
                "features": m.features,
                "cv_r2": m.cv_r2 and round(m.cv_r2, 4),
                "cv_se": m.cv_se and round(m.cv_se, 5),
                "n_params": m.n_params,
                "complexity": m.complexity,
                "verdict": m.verdict,
            }
            for m in ranked[:top]
        ]

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

    def _validate_search(
        self,
        features: list[str],
        unary_operators: list[str],
        binary_operators: list[str],
        maxsize: int | None,
        niterations: int | None,
    ) -> dict[str, Any]:
        self._require_features(features)
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
    ) -> SearchRecord:
        if self.launcher is None:
            raise RuntimeError("No PySR launcher configured")
        if self.cancelled:
            raise BudgetExhausted("The run was cancelled")
        if enforce_budget:
            if len(self.searches) >= self.budget.max_pysr_runs:
                raise BudgetExhausted(
                    f"PySR search budget used ({self.budget.max_pysr_runs}); refine with classic fits or finish"
                )
            running = sum(1 for s in self.searches.values() if not s.done)
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

        search_id = f"pysr_{len(self.searches) + 1}"
        record = SearchRecord(
            search_id=search_id,
            features=list(features),
            config=config,
            target_transform=transform,
            guesses=accepted,
            rejected_guesses=rejected,
            rationale=str(rationale).strip()[:500],
        )
        self.searches[search_id] = record
        input_data = self.pysr_input(features, transform, config, accepted)
        record.task = asyncio.create_task(self._run_search(record, input_data))
        await self.emit(
            "search_started",
            f"Started {search_id} on {', '.join(features)}"
            + (f" — {record.rationale}" if record.rationale else ""),
            search_id=search_id,
        )
        return record

    def _set_job_id(self, record: SearchRecord, job_id: str) -> None:
        record.job_id = job_id

    async def _run_search(self, record: SearchRecord, input_data: dict[str, Any]) -> None:
        try:
            job_id = await self.launcher.submit(
                record.search_id, input_data, lambda jid: self._set_job_id(record, jid)
            )
            record.job_id = job_id
            if record.status == "cancelled":
                return
            record.status = "queued"
            ok, result, error = await self.launcher.wait(job_id)
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
            )
        except asyncio.CancelledError:
            # cancel_search() already told Slurm; only an outside cancellation (run teardown)
            # still has to.
            outside = record.status != "cancelled"
            record.status = "cancelled"
            if outside and record.job_id and self.launcher:
                with contextlib.suppress(Exception):
                    await asyncio.shield(self.launcher.cancel(record.job_id))
            raise
        except Exception as e:
            logger.warning(f"Search {record.search_id} crashed: {e}", exc_info=True)
            record.status = "failed"
            record.error = str(e)
        finally:
            record.finished_at = time.monotonic()

    def _score_front(
        self, record: SearchRecord, equations: list[dict[str, Any]]
    ) -> list[ModelResult]:
        """Score a PySR hall of fame (pure: nothing is registered here)."""
        if len(equations) > MAX_FRONT:
            by_loss = sorted(equations, key=lambda e: e.get("loss", np.inf))[:30]
            by_size = sorted(equations, key=lambda e: e.get("complexity", 0))[:10]
            keep = {id(e) for e in by_loss + by_size}
            equations = [e for e in equations if id(e) in keep]
        scored = []
        for eq in equations:
            text = eq.get("equation") or ""
            try:
                model = self.score_symbolic(text, record.search_id, record.target_transform)
            except ExpressionError as e:
                logger.info(f"Could not parse PySR equation {text!r}: {e}")
                continue
            model.diagnostics["pysr_loss"] = eq.get("loss")
            model.diagnostics["pysr_complexity"] = eq.get("complexity")
            model.diagnostics["structure_selected_in_sample"] = True
            scored.append(model)
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
        if record.job_id and self.launcher:
            try:
                await self.launcher.cancel(record.job_id)
            except Exception as e:
                logger.warning(f"Failed to cancel {search_id}: {e}")
        if record.task:
            record.task.cancel()
        record.finished_at = time.monotonic()
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
        while pending() and not any(s.status == "completed" for s in self.searches.values()):
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
            if m.error or m.parsed is None:
                continue
            m.holdout = score_holdout(m.parsed, m.params, X, y, m.target_transform, fill)

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

    def ranked_models(self) -> list[ModelResult]:
        """All usable models by cross-validated R2 (the holdout never ranks)."""
        return sorted(
            (m for m in self.snapshot() if not m.error),
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
