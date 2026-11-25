"""
Long series along time: the time grid and the chronological split.

When the rows are a long series along time (annual GPP, daily discharge), the target
often depends on earlier conditions as well as on the current ones, and a random split
lets every held-out step sit between training steps, which measures interpolation
instead of prediction forward in time.

``SeriesGrid`` gives every trajectory a time grid whose step is the typical distance
between its measurements. The measurements need not be evenly spaced: a lag is the value
K steps of time earlier, read between the two measurements around that moment, and only
when those two are close together (``MAX_BRACKET_STEPS``). A longer gap gives a missing
lag, never a value from the wrong time. Which time-dependent features (lags, period aggregates) the run uses is
decided by the feature stage (features.py, feature_stage.py).
Rate laws (temporal.py) are a different question: how a state changes, not which past
conditions a quantity depends on.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.services.discovery.temporal import TimeStructure, days_since_first, parse_dates

MIN_SERIES_POINTS = 20  # per trajectory: enough for lags and a chronological holdout
# A value between two measurements is read only when they are at most this many typical
# steps apart (1.5: one missing step of an evenly spaced series stays missing)
MAX_BRACKET_STEPS = 1.5
# A moment this close to a measurement (in steps) is that measurement: months of 28 to 31
# days stay exact on a grid whose step is their mean length
ON_GRID = 0.1


def is_series(ts: TimeStructure | None) -> bool:
    """A long series along a time-named column; the spacing need not be even."""
    return bool(
        ts and ts.time_column and ts.confidence == "strong" and ts.points_min >= MIN_SERIES_POINTS
    )


@dataclass
class SeriesGrid:
    """Every uploaded row's place on its trajectory's time grid."""

    step: np.ndarray  # integer step within the trajectory (-1: no time or trajectory)
    cell: np.ndarray  # (trajectory, step) cell of each row, -1: none
    cell_step: np.ndarray  # step of each cell within its trajectory
    key: np.ndarray  # trajectory code (-1: none)
    step_size: float  # time step (days for dates)
    dates: pd.Series | None = None  # the time column as datetimes (None: numeric time)
    time: np.ndarray | None = None  # each row's time (days for dates)
    origin: np.ndarray | None = None  # each row's trajectory start time
    size: np.ndarray | None = None  # each row's trajectory step
    cell_key: np.ndarray | None = None  # trajectory code of each cell
    cell_time: np.ndarray | None = None  # time of each cell

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
        cell_steps, cell_keys, cell_times, sizes = [], [], [], []
        origin = np.full(len(data), np.nan)
        row_size = np.full(len(data), np.nan)
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
            cell_keys.append(np.full(n_steps, k))
            cell_times.append(times[0] + np.arange(n_steps) * size)
            origin[idx], row_size[idx] = times[0], size
            n_cells += n_steps
            sizes.append(size)
        return cls(
            step=step,
            cell=cell,
            cell_step=np.concatenate(cell_steps) if cell_steps else np.zeros(0, dtype=int),
            key=np.where(ok, codes, -1),
            step_size=float(np.median(sizes)) if sizes else 1.0,
            dates=dates,
            time=np.where(ok, t, np.nan),
            origin=origin,
            size=row_size,
            cell_key=np.concatenate(cell_keys) if cell_keys else np.zeros(0, dtype=int),
            cell_time=np.concatenate(cell_times) if cell_times else np.zeros(0),
        )

    def _at(self, values: np.ndarray, keys: np.ndarray, moments: np.ndarray) -> np.ndarray:
        """
        ``values`` (one per uploaded row) at ``moments`` of the trajectories ``keys``: the
        measurement itself when there is one at that moment, otherwise the value on the
        line between the two measurements around it, when they are close together.
        """
        out = np.full(len(moments), np.nan)
        has = (self.key >= 0) & np.isfinite(values) & np.isfinite(self.time)
        for k in np.unique(keys[keys >= 0]):
            rows = np.flatnonzero(has & (self.key == k))
            want = np.flatnonzero((keys == k) & np.isfinite(moments))
            if not len(rows) or not len(want):
                continue
            size = float(self.size[rows[0]])
            # Replicates at the same time are averaged
            times, inverse = np.unique(self.time[rows], return_inverse=True)
            means = np.bincount(inverse, weights=values[rows]) / np.bincount(inverse)
            at = moments[want]
            right = np.clip(np.searchsorted(times, at, side="left"), 0, len(times) - 1)
            left = np.clip(right - 1, 0, len(times) - 1)
            near = np.where(np.abs(times[right] - at) <= np.abs(times[left] - at), right, left)
            exact = np.abs(times[near] - at) <= ON_GRID * size
            inside = (at >= times[0]) & (at <= times[-1])
            close = (times[right] - times[left]) <= MAX_BRACKET_STEPS * size
            got = np.where(exact, means[near], np.interp(at, times, means))
            out[want] = np.where(exact | (inside & close), got, np.nan)
        return out

    def dense(self, values: np.ndarray) -> np.ndarray:
        """One value per cell of the time grid from one per uploaded row (long gaps NaN)."""
        return self._at(values, self.cell_key, self.cell_time)

    def lagged(self, values: np.ndarray, steps: int) -> np.ndarray:
        """``values`` (one per uploaded row) ``steps`` of time earlier; NaN without that history."""
        return self._at(values, self.key, self.time - steps * self.size)


def final_segment(keys: np.ndarray, fraction: float) -> np.ndarray:
    """Mask of the last ``fraction`` of each trajectory (rows sorted by trajectory, then time)."""
    mask = np.zeros(len(keys), dtype=bool)
    for k in np.unique(keys):
        rows = np.flatnonzero(keys == k)
        n_hold = round(fraction * len(rows))
        if n_hold:
            mask[rows[-n_hold:]] = True
    return mask
