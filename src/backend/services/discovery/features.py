"""
Time-dependent features of a long series: computed here, proposed and chosen by the LLM.

The feature stage (feature_stage.py) asks an LLM which earlier conditions could matter
and gets back ``FeatureSpec`` objects. This module checks every spec, computes it on the
series grid (series.py) and measures what it adds, so the LLM's selection rests on numbers.
LLMs propose; the code decides what is legal and how it is computed.

Three kinds of feature:
- ``lag``: the source K grid steps earlier.
- ``error``: the error of the automatic ARIMA fit of the target K steps earlier (orders.py:
  measured minus predicted one step ahead). Only the orders of that fit add these.
- ``period``: an aggregate (mean, sum, min, max, std) of the source over a period (a
  calendar year/quarter/month/week, a block of K steps, or a whole trajectory), repeated
  on every row of that period (``offset=0``) or taken from the previous period
  (``offset=1``).

Every feature keeps the row count. Where there is no history (the first steps of a
trajectory, a gap, an incomplete period), the trajectory's nearest earlier value fills
the cell, or its first available value at the start (edge padding). Filled cells are
recorded, kept out of the evidence and limited to a share of each trajectory.

A same-period aggregate of the target contains the current target value, so the target
may only be used as a lag or a previous-period aggregate.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Literal, get_args

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from backend.services.discovery.expression import make_alias
from backend.services.discovery.fitting import _r, lag1_autocorrelation, time_blocks
from backend.services.discovery.series import SeriesGrid

MAX_PROPOSED = 40  # specs evaluated per proposal
MAX_SELECTED = 8  # derived features that may enter the data
# Filled (padded) cells allowed per trajectory, as a share of its training rows: a safety
# limit so that padding never stands in for a large part of a series
MAX_PADDED_SHARE = 0.10
# The same limit for the features named by the orders of the automatic ARIMA fit: a value
# one season earlier (12 months) must stay possible on a series of a few years
MAX_ORDERS_SHARE = 0.20
N_EVIDENCE_FOLDS = 5

Stat = Literal["mean", "sum", "min", "max", "std"]
Period = Literal["year", "quarter", "month", "week", "block", "trajectory"]
STATS = get_args(Stat)
# pandas period frequency of each calendar period
CALENDAR = {"year": "Y", "quarter": "Q", "month": "M", "week": "W"}
CALENDAR_DAYS = {"year": 365.25, "quarter": 91.3, "month": 30.4, "week": 7.0}


class FeatureSpec(BaseModel):
    """One proposed time-dependent feature."""

    source: str = Field(description="alias of a continuous feature, or of the target")
    kind: Literal["lag", "period", "error"]
    steps: int | None = Field(default=None, description="lag: how many time steps earlier")
    period: Period | None = None
    block_steps: int | None = Field(default=None, description="period 'block': steps per block")
    stat: Stat = "mean"
    offset: Literal[0, 1] = Field(default=0, description="0: same period, 1: previous period")
    rationale: str = ""
    # "orders": named by the orders of the automatic ARIMA fit, added without a selection
    origin: Literal["proposed", "orders"] = "proposed"

    def label(self) -> str:
        """Compact text of the spec, for rejections."""
        if self.kind == "lag":
            return f"lag {self.steps} of {self.source}"
        if self.kind == "error":
            return f"error of the automatic ARIMA fit of {self.source}, {self.steps} steps earlier"
        block = f" of {self.block_steps} steps" if self.period == "block" else ""
        when = "previous" if self.offset else "same"
        return f"{self.stat} of {self.source} over the {when} {self.period}{block}"


@dataclass
class SeriesContext:
    """The analysed rows of a long series: their grid cells, trajectories and split."""

    grid: SeriesGrid
    pos: np.ndarray  # uploaded row of each analysed row (rows sorted by trajectory, time)
    keys: np.ndarray  # trajectory code of each analysed row
    held: np.ndarray  # holdout mask of each analysed row
    time_column: str
    group_column: str | None

    @property
    def dates(self) -> pd.Series | None:
        """The time column as dates (uploaded rows); None for numeric time."""
        return self.grid.dates

    @cached_property
    def n_trajectories(self) -> int:
        return len(np.unique(self.keys))

    def per_trajectory(self, mask: np.ndarray) -> np.ndarray:
        """Count of ``mask`` rows in each trajectory that has rows."""
        counts = np.bincount(self.keys, weights=mask.astype(float))
        return counts[np.bincount(self.keys) > 0]

    @cached_property
    def train_rows_min(self) -> int:
        """Training rows of the shortest trajectory."""
        return int(self.per_trajectory(~self.held).min())

    @cached_property
    def max_padded_rows(self) -> int:
        return math.floor(MAX_PADDED_SHARE * self.train_rows_min)

    def history_limit(self, spec: "FeatureSpec") -> int:
        """Rows of a trajectory that may be filled or left out for this spec."""
        if spec.origin == "orders":
            return math.floor(MAX_ORDERS_SHARE * self.train_rows_min)
        return self.max_padded_rows

    @cached_property
    def allowed_periods(self) -> list[str]:
        out = []
        if self.dates is not None:
            out += [p for p in CALENDAR if CALENDAR_DAYS[p] >= 2 * self.grid.step_size]
        out.append("block")
        if self.n_trajectories > 1:
            out.append("trajectory")
        return out


@dataclass
class DerivedFeature:
    """A computed, padded feature (one value per analysed row)."""

    spec: FeatureSpec
    alias: str
    column: str  # display name, used as the column name
    description: str
    values: np.ndarray
    padded: np.ndarray  # cells filled by edge padding
    backfilled: np.ndarray  # start cells filled from a later row
    of_target: bool

    @property
    def leaks_target(self) -> np.ndarray:
        """
        Rows whose value comes from a later row of the target's own past: at a trajectory's
        start, a lag of the target back-filled from the next row equals the row's own target.
        """
        return self.backfilled if self.of_target else np.zeros(len(self.values), dtype=bool)

    def record(self) -> dict[str, Any]:
        s = self.spec
        out: dict[str, Any] = {
            "feature": self.alias,
            "column": self.column,
            "source": s.source,
            "kind": s.kind,
        }
        if s.origin == "orders":
            out["origin"] = "orders"
        if s.kind in ("lag", "error"):
            out["steps"] = s.steps
        else:
            out |= {"period": s.period, "stat": s.stat, "offset": s.offset}
            if s.period == "block":
                out["block_steps"] = s.block_steps
        return out


# ----------------------------------------------------------------------------- checks


def validate_spec(
    spec: FeatureSpec, ctx: SeriesContext, sources: set[str], target: str
) -> str | None:
    """Why the spec cannot be computed (None: it can)."""
    if spec.source != target and spec.source not in sources:
        return (
            f"unknown source {spec.source!r}: use a continuous feature alias or the target "
            "(the time and group columns are not sources)"
        )
    if spec.kind == "error" and (spec.origin != "orders" or spec.source != target):
        return (
            "errors come from the automatic ARIMA fit of the target only; propose lags or periods"
        )
    if spec.kind in ("lag", "error"):
        if spec.steps is None or spec.steps < 1:
            return "a lag needs steps >= 1"
        if spec.steps > ctx.history_limit(spec):
            return (
                f"lag {spec.steps} needs more padded rows than allowed "
                f"({ctx.history_limit(spec)} per trajectory)"
            )
        return None
    if spec.period is None:
        return "a period aggregate needs a period"
    allowed = ctx.allowed_periods
    if spec.period not in allowed:
        return f"period {spec.period!r} is not available for this series (allowed: {allowed})"
    if spec.period == "block" and (spec.block_steps is None or spec.block_steps < 2):
        return "period 'block' needs block_steps >= 2"
    if spec.period == "trajectory" and spec.source == target:
        return "a trajectory aggregate of the target contains the current target value"
    if spec.period == "trajectory" and spec.offset != 0:
        return "a trajectory has no previous trajectory: use offset 0"
    if spec.source == target and spec.offset != 1:
        return (
            "a same-period aggregate of the target contains the current target value; use "
            "offset 1 (the previous period)"
        )
    return None


# ------------------------------------------------------------------------- computation


def _period_codes(
    spec: FeatureSpec, ctx: SeriesContext
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Each uploaded row's period code, whether it has one, and the steps a full period has."""
    grid = ctx.grid
    on = grid.step >= 0
    if spec.period == "trajectory":
        return np.zeros(len(grid.step), dtype=np.int64), on, None
    if spec.period == "block":
        b = int(spec.block_steps)
        return np.where(on, grid.step // b, 0).astype(np.int64), on, np.full(len(on), float(b))
    dates = ctx.dates
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    index = pd.PeriodIndex(dates, freq=CALENDAR[spec.period])
    codes = index.asi8.astype(np.int64)
    known = on & ~np.asarray(index.isna())
    days = np.asarray((index.end_time - index.start_time).days + 1, dtype=float)
    return np.where(known, codes, 0), known, days / grid.step_size


def _aggregate(
    spec: FeatureSpec, ctx: SeriesContext, raw: np.ndarray
) -> np.ndarray:  # one value per uploaded row
    grid = ctx.grid
    codes, known, expected = _period_codes(spec, ctx)
    dense = grid.dense(raw)
    cells = grid.cell[known]
    table = pd.DataFrame(
        {
            "cell": cells,
            "key": grid.key[known],
            "period": codes[known],
            "expected": expected[known] if expected is not None else np.nan,
        }
    ).drop_duplicates("cell")
    table["value"] = dense[table["cell"].to_numpy()]
    groups = table.groupby(["key", "period"])
    values = table[np.isfinite(table["value"])].groupby(["key", "period"])["value"]
    agg = values.agg(spec.stat)
    count = values.count()
    # A period needs half of its steps (a sum needs all of them: missing steps bias it)
    full = groups["expected"].max().reindex(agg.index)
    # (rounded: a calendar period's length in steps is not a whole number, e.g. 366 / 30.4)
    need = np.where(full.isna(), 1, np.round(full if spec.stat == "sum" else full / 2))
    need = np.maximum(need, 1)
    if spec.stat == "std":
        need = np.maximum(need, 2)
    agg = agg[count.to_numpy() >= need]
    lookup = pd.MultiIndex.from_arrays([grid.key, codes - spec.offset])
    out = agg.reindex(lookup).to_numpy(dtype=float)
    out[~known] = np.nan
    return out


def compute_spec(spec: FeatureSpec, ctx: SeriesContext, raw: np.ndarray) -> np.ndarray:
    """The spec's values on the analysed rows (NaN without history), before padding."""
    if spec.kind in ("lag", "error"):
        return ctx.grid.lagged(raw, int(spec.steps))[ctx.pos]
    return _aggregate(spec, ctx, raw)[ctx.pos]


def pad_edge(values: np.ndarray, keys: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Fill missing cells within each trajectory (rows sorted by trajectory, then time): from
    the nearest earlier value, and at the start from the first available one.
    Returns the filled values, the mask of filled cells and the mask of the start cells
    filled from a later row (back-filled).
    """
    forward = pd.Series(values).groupby(keys).ffill()
    backfilled = forward.isna().to_numpy()
    filled = forward.groupby(keys).bfill().to_numpy(dtype=float)
    padded = ~np.isfinite(values) & np.isfinite(filled)
    return filled, padded, backfilled & np.isfinite(filled)


# ------------------------------------------------------------------------ descriptions


def _period_text(spec: FeatureSpec, ctx: SeriesContext) -> str:
    if spec.period == "block":
        return f"block of {spec.block_steps} steps"
    if spec.period == "trajectory":
        return f"whole series of its {ctx.group_column or 'trajectory'}"
    return "calendar year" if spec.period == "year" else str(spec.period)


def alias_base(spec: FeatureSpec) -> str:
    if spec.kind == "lag":
        return f"{spec.source}_l{spec.steps}"
    if spec.kind == "error":
        return f"{spec.source}_err_l{spec.steps}"
    period = f"b{spec.block_steps}" if spec.period == "block" else spec.period
    prev = "_prev" if spec.offset else ""
    return f"{spec.source}_{spec.stat}{prev}_{period}"


def describe_spec(
    spec: FeatureSpec, column: str, ctx: SeriesContext, of_target: bool
) -> tuple[str, str]:
    """Display name and description of the derived column."""
    step = ctx.grid.step_size
    along = f"along {ctx.time_column}" + (f" (step {step:g})" if step != 1 else "")
    if spec.kind == "lag":
        k = spec.steps
        name = f"{column} at t-{k}"
        text = f"{column} {k} step{'s' if k != 1 else ''} earlier {along}"
    elif spec.kind == "error":
        k = spec.steps
        name = f"{column} error at t-{k}"
        text = (
            f"error of an automatic ARIMA fit of {column} (measured minus predicted one step "
            f"ahead from earlier measurements) {k} step{'s' if k != 1 else ''} earlier {along}"
        )
    else:
        period = _period_text(spec, ctx)
        if spec.offset:
            name = f"{column} {spec.stat} of previous {period}"
            text = f"{spec.stat} of {column} over the previous {period} {along}"
        else:
            name = f"{column} {spec.stat} of {period}"
            text = (
                f"{spec.stat} of {column} over the same {period} {along}, repeated on every "
                "row of it"
            )
    if of_target:
        text += "; the target's own past: persistence, not an external driver"
    return name, text


# -------------------------------------------------------------------------- candidates


def build_candidates(
    specs: list[FeatureSpec],
    ctx: SeriesContext,
    raw_of: Callable[[str], np.ndarray],
    column_of: dict[str, str],
    sources: set[str],
    target: str,
    taken: set[str],
    reserved: set[str],
    errors: np.ndarray | None = None,
) -> tuple[list[DerivedFeature], list[dict[str, str]]]:
    """
    Check and compute the specs. ``raw_of(alias)`` gives the uploaded rows' values of a
    source, ``errors`` the one-step errors of the automatic ARIMA fit (orders.py). Returns the computed candidates and the rejected specs with their reasons.
    """
    candidates: list[DerivedFeature] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()
    taken = set(taken)
    train = ~ctx.held
    for spec in specs[:MAX_PROPOSED]:
        limit = ctx.history_limit(spec)
        reason = validate_spec(spec, ctx, sources, target)
        if reason is None and alias_base(spec) in seen:
            reason = "duplicate of an earlier spec"
        if reason is None and spec.kind == "error" and errors is None:
            reason = "no automatic ARIMA fit of the target"
        if reason is None:
            raw = errors if spec.kind == "error" else raw_of(spec.source)
            values = compute_spec(spec, ctx, raw)
            values, padded, backfilled = pad_edge(values, ctx.keys)
            worst = int(ctx.per_trajectory(padded & train).max())
            if not np.all(np.isfinite(values)):
                reason = "no value at all in some trajectory"
            elif worst > limit:
                reason = f"needs {worst} padded rows in a trajectory, more than the {limit} allowed"
            elif np.nanstd(values[train & ~padded]) == 0:
                reason = "constant on the training rows"
        if reason is not None:
            rejected.append({"spec": spec.label(), "reason": reason})
            continue
        seen.add(alias_base(spec))
        alias = make_alias(alias_base(spec), taken, reserved)
        taken.add(alias)
        of_target = spec.source == target
        column, text = describe_spec(spec, column_of[spec.source], ctx, of_target)
        candidates.append(
            DerivedFeature(spec, alias, column, text, values, padded, backfilled, of_target)
        )
    for spec in specs[MAX_PROPOSED:]:
        rejected.append({"spec": spec.label(), "reason": f"beyond the first {MAX_PROPOSED}"})
    return candidates, rejected


# ---------------------------------------------------------------------------- evidence


def _design(columns: list[np.ndarray], rows: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(rows))] + [c[rows] for c in columns])


def _complete(rows: np.ndarray, columns: list[np.ndarray]) -> np.ndarray:
    """The rows where every column has a value."""
    for c in columns:
        rows = rows[np.isfinite(c[rows])]
    return rows


def _cv_mse(y: np.ndarray, keys: np.ndarray, columns: list[np.ndarray], rows: np.ndarray) -> float:
    """CV error of a linear model over contiguous time blocks of ``rows``."""
    X = _design(columns, rows)
    sd = X[:, 1:].std(axis=0)
    X[:, 1:] = (X[:, 1:] - X[:, 1:].mean(axis=0)) / np.where(sd > 0, sd, 1.0)
    ridge = 1e-6 * len(rows) * np.eye(X.shape[1])
    ridge[0, 0] = 0.0
    err = np.empty(len(rows))
    for test in time_blocks(keys[rows], N_EVIDENCE_FOLDS):
        train = np.ones(len(rows), dtype=bool)
        train[test] = False
        A = X[train]
        beta = np.linalg.solve(A.T @ A + ridge, A.T @ y[rows][train])
        err[test] = y[rows][test] - X[test] @ beta
    return float(np.mean(err**2))


def residual_autocorrelation(
    y: np.ndarray, keys: np.ndarray, columns: list[np.ndarray], rows: np.ndarray
) -> float | None:
    """Lag-1 autocorrelation of a linear model's residuals within the trajectories."""
    X = _design(columns, rows)
    beta, *_ = np.linalg.lstsq(X, y[rows], rcond=None)
    return _r(lag1_autocorrelation(y[rows] - X @ beta, keys[rows])[0], 3)


def _corr(a: np.ndarray, b: np.ndarray) -> float | None:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3 or np.std(a[ok]) == 0 or np.std(b[ok]) == 0:
        return None
    return float(np.corrcoef(a[ok], b[ok])[0, 1])


@dataclass
class TrainView:
    """The training rows of the analysed series: current features, target, trajectories."""

    rows: np.ndarray  # analysed-row index of each training row
    drivers: list[np.ndarray]
    y: np.ndarray
    keys: np.ndarray
    complete: np.ndarray  # training rows (positions in ``rows``) where every driver has a value

    @classmethod
    def build(
        cls, drivers: list[np.ndarray], y: np.ndarray, keys: np.ndarray, train: np.ndarray
    ) -> "TrainView":
        rows = np.flatnonzero(train)
        drivers_t = [d[rows] for d in drivers]
        return cls(rows, drivers_t, y[rows], keys[rows], _complete(np.arange(len(rows)), drivers_t))


def feature_evidence(
    candidates: list[DerivedFeature], view: TrainView, current: dict[str, np.ndarray]
) -> dict[str, Any]:
    """
    What each candidate adds, on the training rows without padded cells; ``current`` maps
    each source alias (and the target) to its current values on the analysed rows.

    Per candidate: gain = the share of a linear model's time-block CV error that adding it
    to the current features removes; r_target; for lags, step_change_r = how closely its
    step-to-step changes follow the source's current changes (near 1: a shifted copy of a
    smooth series, no memory beyond it); the most correlated other candidate; the padded share.
    """
    y, keys, drivers, base = view.y, view.keys, view.drivers, view.complete
    same = keys[1:] == keys[:-1]
    before_by_mask: dict[bytes, float] = {}  # the drivers-only model, per padding pattern
    table = []
    for c in candidates:
        v, pad = c.values[view.rows], c.padded[view.rows]
        rows = base[~pad[base]]
        gain = None
        if len(rows) >= 3 * (len(drivers) + 3):
            mask = pad[base].tobytes()
            if mask not in before_by_mask:
                before_by_mask[mask] = _cv_mse(y, keys, drivers, rows)
            before = before_by_mask[mask]
            after = _cv_mse(y, keys, [*drivers, v], rows)
            gain = 1 - after / before if before > 0 else 0.0
        item: dict[str, Any] = {
            "feature": c.alias,
            "spec": c.spec.label(),
            "of_target": c.of_target,
            "already_included": c.spec.origin == "orders",
            "gain": _r(gain, 3),
            "r_target": _r(_corr(v[rows], y[rows]), 3),
            "padded_share": _r(float(pad.mean()), 3),
        }
        if c.spec.kind == "lag":
            ok = same & ~pad[1:] & ~pad[:-1]
            src = current[c.spec.source][view.rows]
            item["step_change_r"] = _r(_corr(np.diff(v)[ok], np.diff(src)[ok]), 3)
        table.append(item)
    # Redundancy: the most correlated other candidate (pairwise, padded cells left out)
    for item in table:
        item["most_correlated"] = None
    if len(candidates) > 1:
        values = pd.DataFrame(
            {
                c.alias: np.where(c.padded[view.rows], np.nan, c.values[view.rows])
                for c in candidates
            }
        )
        corr = values.corr(min_periods=3).to_numpy()
        np.fill_diagonal(corr, np.nan)
        for i, item in enumerate(table):
            if np.all(np.isnan(corr[i])):
                continue
            j = int(np.nanargmax(np.abs(corr[i])))
            item["most_correlated"] = {"feature": candidates[j].alias, "r": _r(corr[i, j], 3)}
    return {
        "method": "single-feature addition to a linear model of the current features, "
        "CV over contiguous time blocks of the training rows, padded cells excluded",
        "candidates": table,
        "residual_autocorrelation_current": residual_autocorrelation(y, keys, drivers, base),
    }


def selected_autocorrelation(
    selected: list[DerivedFeature], view: TrainView
) -> dict[str, float | None]:
    """Residual autocorrelation with the current features only and with the selection."""
    rows = view.complete
    for c in selected:
        rows = rows[~c.padded[view.rows][rows]]
    ac = {"current_drivers_only": residual_autocorrelation(view.y, view.keys, view.drivers, rows)}
    with_selected = [*view.drivers, *(c.values[view.rows] for c in selected)]
    ac["with_selected"] = (
        residual_autocorrelation(view.y, view.keys, with_selected, rows) if selected else None
    )
    return ac
