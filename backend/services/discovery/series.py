"""
Long, regularly sampled series: the time grid and the chronological split.

When the rows are a long series along time (annual GPP, daily discharge), the target
often depends on earlier conditions as well as on the current ones, and a random split
lets every held-out step sit between training steps, which measures interpolation
instead of prediction forward in time.

``SeriesGrid`` places every uploaded row on its trajectory's regular time grid, so a
lag is the value K steps earlier on that grid (a gap gives a missing lag, never the
wrong step). Which time-dependent features (lags, period aggregates) the run uses is
decided by the feature stage (features.py, feature_stage.py).
Rate laws (temporal.py) are a different question: how a state changes, not which past
conditions a quantity depends on.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.services.discovery.temporal import TimeStructure, days_since_first, parse_dates

MIN_SERIES_POINTS = 20  # per trajectory: enough for lags and a chronological holdout


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
    dates: pd.Series | None = None  # the time column as datetimes (None: numeric time)

    @classmethod
    def build(cls, data: pd.DataFrame, ts: TimeStructure) -> "SeriesGrid":
        column = data[ts.time_column]
        dates = parse_dates(column)
        if dates is not None:
            t = days_since_first(dates)
        elif pd.api.types.is_numeric_dtype(column):
            t = column.to_numpy(dtype=float)
        else:
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
            dates=dates,
        )

    def dense(self, values: np.ndarray) -> np.ndarray:
        """One value per cell from one per uploaded row: replicates averaged, gaps NaN."""
        n_cells = len(self.cell_step)
        has = (self.cell >= 0) & np.isfinite(values)
        sums = np.bincount(self.cell[has], weights=values[has], minlength=n_cells)
        counts = np.bincount(self.cell[has], minlength=n_cells)
        dense = np.full(n_cells, np.nan)
        np.divide(sums, counts, out=dense, where=counts > 0)
        return dense

    def lagged(self, values: np.ndarray, steps: int) -> np.ndarray:
        """``values`` (one per uploaded row) ``steps`` earlier; NaN without that history."""
        n_cells = len(self.cell_step)
        dense = self.dense(values)
        at = np.arange(n_cells)
        valid = self.cell_step >= steps  # within the same trajectory
        start = np.where(valid, at - steps, 0)
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
