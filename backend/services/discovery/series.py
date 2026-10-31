"""
Long, regularly sampled series: lagged features and a chronological split.

When the rows are a long series along time (annual GPP, daily discharge), the target
often depends on earlier conditions as well as on the current ones: last year's drought,
the mean of the previous seasons, the target's own persistence. The row-wise analysis
cannot see these, and a random split lets every held-out year sit between training
years, which measures interpolation instead of prediction forward in time.

``SeriesGrid`` places every uploaded row on its trajectory's regular time grid, so a
lag is the value K steps earlier on that grid (a gap gives a missing lag, never the
wrong year). ``screen_lags`` picks the few lagged columns that carry information beyond
the current values: forward selection by the drop of a linear model's cross-validated
error over contiguous time blocks of the training rows. Only the selected columns become
features, so every model, search and benchmark of the run sees the same rows.
Rate laws (temporal.py) are a different question: how a state changes, not which past
conditions a quantity depends on.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from backend.services.discovery.fitting import _r, lag1_autocorrelation, time_blocks
from backend.services.discovery.temporal import TimeStructure, _as_time

MIN_SERIES_POINTS = 20  # per trajectory: enough for lags and a chronological holdout
LONG_SERIES_POINTS = 50  # from here on the 5-step mean is a candidate too
LAG_STEPS = (1, 2)
MEAN_WINDOWS = (3, 5)
MAX_DRIVER_LAGS = 4
# The target's previous value (persistence) and, next to it, its last change (momentum: a
# water table that keeps falling through the summer). The change is y_l1 - y_l2, the same
# linear span as y_l2 but far less collinear with y_l1 and readable as a trend that carries on
MAX_TARGET_LAGS = 2
# A lag is kept when it lowers the cross-validated error by this share of what is left
LAG_MIN_GAIN = 0.03
# A lag whose step-to-step changes track the current value's this closely is a shifted copy
# of a smooth series: no memory, only a proxy for curvature (a trend alone is no reason)
SAME_AS_CURRENT_R = 0.98
N_SCREEN_FOLDS = 5


def is_series(ts: TimeStructure | None) -> bool:
    """A long, regularly sampled series along a time-named column."""
    return bool(
        ts
        and ts.time_column
        and ts.confidence == "strong"
        and ts.regular
        and ts.points_min >= MIN_SERIES_POINTS
    )


@dataclass
class SeriesGrid:
    """Every uploaded row's place on its trajectory's regular time grid."""

    step: np.ndarray  # integer step within the trajectory (-1: no time or trajectory)
    cell: np.ndarray  # (trajectory, step) cell of each row, -1: none
    cell_step: np.ndarray  # step of each cell within its trajectory
    key: np.ndarray  # trajectory code (-1: none)
    step_size: float  # time step (days for dates)

    @classmethod
    def build(cls, data: pd.DataFrame, ts: TimeStructure) -> "SeriesGrid":
        t = _as_time(data[ts.time_column])
        if t is None:
            raise ValueError(f"Column {ts.time_column!r} is neither numeric nor a date")
        codes = (
            pd.factorize(data[ts.group_column])[0]
            if ts.group_column
            else np.zeros(len(data), dtype=int)
        )
        ok = np.isfinite(t) & (codes >= 0)
        step = np.full(len(data), -1)
        cell = np.full(len(data), -1)
        cell_steps, sizes = [], []
        n_cells = 0
        for k in np.unique(codes[ok]):
            idx = np.flatnonzero(ok & (codes == k))
            times = np.unique(t[idx])
            gaps = np.diff(times)
            size = float(np.median(gaps)) if len(gaps) else 1.0
            # The mean of the single-step gaps: a median of 28-31 day months is 31, which
            # drifts by a step every ~30 months; gaps of several steps would bias the mean
            single = gaps[np.rint(gaps / size) == 1]
            if len(single):
                size = float(single.mean())
            step[idx] = np.rint((t[idx] - times[0]) / size).astype(int)
            cell[idx] = n_cells + step[idx]
            n_steps = int(step[idx].max()) + 1
            cell_steps.append(np.arange(n_steps))
            n_cells += n_steps
            sizes.append(size)
        return cls(
            step=step,
            cell=cell,
            cell_step=np.concatenate(cell_steps) if cell_steps else np.zeros(0, dtype=int),
            key=np.where(ok, codes, -1),
            step_size=float(np.median(sizes)) if sizes else 1.0,
        )

    def lagged(self, values: np.ndarray, steps: int, mean: bool = False) -> np.ndarray:
        """
        ``values`` (one per uploaded row) ``steps`` earlier, or with ``mean`` their mean
        over the previous ``steps`` (the current step excluded); NaN without that history.
        """
        n_cells = len(self.cell_step)
        # One value per step (replicates averaged); missing steps stay NaN
        has = (self.cell >= 0) & np.isfinite(values)
        sums = np.bincount(self.cell[has], weights=values[has], minlength=n_cells)
        counts = np.bincount(self.cell[has], minlength=n_cells)
        dense = np.full(n_cells, np.nan)
        np.divide(sums, counts, out=dense, where=counts > 0)
        at = np.arange(n_cells)
        valid = self.cell_step >= steps  # within the same trajectory
        start = np.where(valid, at - steps, 0)
        if mean:
            missing = np.isnan(dense)
            total = np.concatenate([[0.0], np.cumsum(np.where(missing, 0.0, dense))])
            gaps = np.concatenate([[0], np.cumsum(missing)])
            complete = valid & (gaps[at] - gaps[start] == 0)
            earlier = np.where(complete, (total[at] - total[start]) / steps, np.nan)
        else:
            earlier = np.where(valid, dense[start], np.nan)
        out = np.full(len(values), np.nan)
        on = self.cell >= 0
        out[on] = earlier[self.cell[on]]
        return out


def final_segment(keys: np.ndarray, fraction: float) -> np.ndarray:
    """Mask of the last ``fraction`` of each trajectory (rows sorted by trajectory, then time)."""
    mask = np.zeros(len(keys), dtype=bool)
    for k in np.unique(keys):
        rows = np.flatnonzero(keys == k)
        n_hold = round(fraction * len(rows))
        if n_hold:
            mask[rows[-n_hold:]] = True
    return mask


@dataclass
class LagCandidate:
    """A lagged copy of a predictor or of the target."""

    alias: str
    source: str  # alias of the column it is taken from
    kind: str  # lag | mean | change
    steps: int  # the lag, the window of the mean, or the step of the change (t-steps vs t-steps-1)
    values: np.ndarray  # one per analysed row
    of_target: bool = False

    def describe(self, column: str, time_column: str, step_size: float) -> tuple[str, str]:
        """Display name and description of the derived column."""
        along = f"along {time_column}" + (f" (step {step_size:g})" if step_size != 1 else "")
        if self.kind == "lag":
            name = f"{column} at t-{self.steps}"
            text = f"{column} {self.steps} step{'s' if self.steps > 1 else ''} earlier {along}"
        elif self.kind == "change":
            name = f"{column} change t-{self.steps + 1}..t-{self.steps}"
            text = (
                f"change of {column} over the step before the previous value {along} "
                f"(value at t-{self.steps} minus value at t-{self.steps + 1}): a recent trend "
                "that carries on"
            )
        else:
            name = f"{column} mean t-{self.steps}..t-1"
            text = (
                f"mean of {column} over the previous {self.steps} steps {along} "
                "(antecedent conditions)"
            )
        if self.of_target:
            text += "; the target's own past: persistence, not an external driver"
        return name, text


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
    for test in time_blocks(keys[rows], N_SCREEN_FOLDS):
        train = np.ones(len(rows), dtype=bool)
        train[test] = False
        A = X[train]
        beta = np.linalg.solve(A.T @ A + ridge, A.T @ y[rows][train])
        err[test] = y[rows][test] - X[test] @ beta
    return float(np.mean(err**2))


def _residual_autocorrelation(
    y: np.ndarray, keys: np.ndarray, columns: list[np.ndarray], rows: np.ndarray
) -> float | None:
    X = _design(columns, rows)
    beta, *_ = np.linalg.lstsq(X, y[rows], rcond=None)
    return _r(lag1_autocorrelation(y[rows] - X @ beta, keys[rows])[0], 3)


def screen_lags(
    drivers: list[np.ndarray],
    y: np.ndarray,
    keys: np.ndarray,
    candidates: list[LagCandidate],
    current: dict[str, np.ndarray],
) -> tuple[list[LagCandidate], dict[str, Any]]:
    """
    Forward selection of lagged columns on the training rows (sorted by trajectory, then
    time). Lags of the predictors go first; the target's own lags only after them, so
    persistence counts only where the drivers and their history leave memory unexplained;
    a last round of predictor lags then completes a persistent anomaly. A change term
    (momentum) is a candidate only next to its source's previous value.
    ``current`` maps each source alias to its current values (the collinearity check).

    Returns the selected candidates and the screening record for the agent and the report.
    """
    base_rows = _complete(np.arange(len(y)), drivers)
    table: list[dict[str, Any]] = []
    usable = []
    same = keys[1:] == keys[:-1]
    for c in candidates:
        steps_lag, steps_now = np.diff(c.values)[same], np.diff(current[c.source])[same]
        ok = np.isfinite(steps_lag) & np.isfinite(steps_now)
        r = np.nan
        if ok.sum() > 2 and np.std(steps_lag[ok]) > 0 and np.std(steps_now[ok]) > 0:
            r = np.corrcoef(steps_lag[ok], steps_now[ok])[0, 1]
        if np.isfinite(r) and abs(r) > SAME_AS_CURRENT_R:
            table.append(
                {"feature": c.alias, "selected": False, "gain": None,
                 "note": f"its changes track the current value's (r={r:.3f}): a shifted copy "
                 "of a smooth series, no memory beyond it"}
            )  # fmt: skip
        else:
            usable.append(c)

    # A predictor's lag must also beat the curvature of its current value: the gap
    # between a trending input and its recent mean is a curvature proxy
    curvature = {
        c.source: (
            (current[c.source] - np.nanmean(current[c.source]))
            / (np.nanstd(current[c.source]) or 1.0)
        )
        ** 2
        for c in usable
        if not c.of_target
    }
    selected: list[LagCandidate] = []
    gains: dict[str, float] = {}
    # Predictor lags, then the target's, then predictor lags again: an anomaly that
    # persists (y_l1 - b*x_l1) needs a predictor lag that only helps next to the target's
    for of_target, cap in (
        (False, MAX_DRIVER_LAGS),
        (True, MAX_TARGET_LAGS),
        (False, MAX_DRIVER_LAGS),
    ):
        while sum(c.of_target == of_target for c in selected) < cap:
            cols = drivers + [s.values for s in selected]
            rows_now = _complete(base_rows, [s.values for s in selected])
            taken = {s.alias for s in selected}
            best, best_gain = None, LAG_MIN_GAIN
            for c in usable:
                if c.of_target != of_target or c.alias in taken:
                    continue
                if c.kind == "change" and not any(
                    s.source == c.source and s.kind == "lag" and s.steps == c.steps
                    for s in selected
                ):
                    continue  # momentum only refines persistence, never replaces it
                if (
                    c.of_target
                    and c.kind != "change"
                    and any(s.of_target and s.source == c.source for s in selected)
                ):
                    # Next to persistence, a mean or a second lag of the target only encodes
                    # the same momentum less readably than its last change
                    continue
                rows = _complete(rows_now, [c.values])
                if len(rows) < 3 * (len(cols) + 2):
                    continue
                # Both models on the same rows (a lag has no value at a series' start)
                ref = cols if c.of_target else [*cols, curvature[c.source]]
                before = _cv_mse(y, keys, ref, rows)
                after = _cv_mse(y, keys, [*ref, c.values], rows)
                # What it adds to the current selection (the last round it was tried in)
                gains[c.alias] = 1 - after / before if before > 0 else 0.0
                if gains[c.alias] > best_gain:
                    best, best_gain = c, gains[c.alias]
            if best is None:
                break
            selected.append(best)

    chosen = {c.alias for c in selected}
    for c in usable:
        table.append(
            {
                "feature": c.alias,
                "selected": c.alias in chosen,
                "gain": _r(gains.get(c.alias), 3),
            }
        )
    table.sort(key=lambda d: (not d["selected"], -(d["gain"] if d["gain"] is not None else -9)))
    rows = _complete(base_rows, [c.values for c in selected])
    record = {
        "method": "forward selection by the drop of a linear model's CV error over contiguous "
        f"time blocks (kept when >= {LAG_MIN_GAIN:.0%} of the remaining error, for a predictor's "
        "lag beyond the curvature of its current value); predictor lags first, the target's "
        "own lags (persistence, then its last change) only after them",
        "candidates": table,
        "residual_autocorrelation": {
            "current_drivers_only": _residual_autocorrelation(y, keys, drivers, rows),
            "with_selected_lags": _residual_autocorrelation(
                y, keys, drivers + [c.values for c in selected], rows
            ),
        },
    }
    return selected, record
