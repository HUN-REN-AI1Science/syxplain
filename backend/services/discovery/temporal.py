"""
Time structure: is the dataset ordered measurements, and what is its rate of change?

``detect_time_structure`` looks at every uploaded column (the time column is often
not a selected predictor) for a time axis and, optionally, a trajectory column
(sample, jar, plot, ...). It is a deterministic proposal; the agent confirms or
overrides it with ``set_dynamics``.

``DynamicsData`` turns the confirmed structure into a regression problem for rate
laws: the target's time derivative (smoothed, per trajectory) against the state and
the inputs, with trajectories kept whole across CV folds and the holdout, so
``fit_model`` scores a right-hand side like any other formula. ``simulate``
integrates a fitted right-hand side from each trajectory's start, which is the real
test of a rate law: one that fits the derivatives can still drift or blow up.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

from backend.services.discovery.expression import ParsedExpression
from backend.services.discovery.fitting import FitData, holdout_metrics, r2_score
from backend.services.discovery.profiling import _forests

logger = logging.getLogger(__name__)

TIME_WORDS = {
    "t", "time", "times", "day", "days", "date", "datetime", "timestamp", "hour", "hours",
    "hr", "h", "week", "weeks", "month", "months", "year", "years", "doy", "elapsed", "age",
    "min", "minute", "minutes", "sec", "second", "seconds", "dap", "das", "period",
}  # fmt: skip
GROUP_WORDS = {
    "id", "sample", "samples", "plot", "jar", "replicate", "rep", "block", "site", "subject",
    "unit", "pot", "column", "series", "trajectory", "run", "batch", "experiment",
    "treatment", "trt", "core", "profile", "field", "station", "well",
}  # fmt: skip
MIN_POINTS = 4  # per trajectory
MAX_CANDIDATES = 10
REGULAR_TOLERANCE = 0.12  # a gap within this share of a whole number of steps (28 vs 31 days)
REGULAR_SINGLE_STEPS = 0.8  # share of gaps that must be a single step
MAX_WINDOW = 31  # points per local derivative fit (bounds the cost on long series)
MAX_DYNAMIC_ROWS = 5000  # derivative rows used for fitting (like the static max_fit_rows)
DATE_SAMPLE = 200  # values parsed to decide whether a text column holds dates
MAX_SIM_EPISODES = 20
SIM_MAX_EVALS = 20000
SIM_MAX_S = 3.0


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if w}


def _as_time(series: pd.Series) -> np.ndarray | None:
    """Numeric time values (datetimes become days since the first), or None."""
    if pd.api.types.is_numeric_dtype(series):
        return series.to_numpy(dtype=float)
    if pd.api.types.is_datetime64_any_dtype(series):
        parsed = series
    else:
        sample = series.dropna()
        if sample.empty:
            return None
        try:
            # A sample first: parsing every value of a free-text column is slow.
            head = pd.to_datetime(sample.iloc[:DATE_SAMPLE], errors="coerce", format="mixed")
            if head.notna().mean() < 0.8:
                return None
            parsed = pd.to_datetime(series, errors="coerce", format="mixed")
        except (TypeError, ValueError):
            return None
        if parsed.notna().mean() < 0.8:
            return None
    days = (parsed - parsed.min()).dt.total_seconds() / 86400.0
    return days.to_numpy(dtype=float)


@dataclass
class TimeStructure:
    """Proposed (or confirmed) time axis and trajectory column."""

    time_column: str | None
    group_column: str | None = None
    confidence: str = "none"  # strong | weak | none
    n_trajectories: int = 0
    points_min: int = 0
    points_median: float = 0.0
    regular: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)
    alternatives: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_column": self.time_column,
            "group_column": self.group_column,
            "confidence": self.confidence,
            "n_trajectories": self.n_trajectories,
            "points_per_trajectory": {"min": self.points_min, "median": self.points_median},
            "regular_spacing": self.regular,
            "evidence": self.evidence,
            "alternatives": self.alternatives,
        }


def _ordered(codes: np.ndarray, t: np.ndarray, *values: np.ndarray) -> list[np.ndarray]:
    """Rows sorted by trajectory then time, keeping trajectories with MIN_POINTS or more."""
    order = np.lexsort((t, codes))
    c = codes[order]
    keep = np.bincount(c)[c] >= MIN_POINTS
    return [c[keep], t[order][keep], *(v[order][keep] for v in values)]


def _smoothness(y: np.ndarray, codes: np.ndarray, t: np.ndarray) -> tuple[float, float, int]:
    """
    Von Neumann smoothness of the target along time within trajectories:
    1 - (sum of squared successive differences) / (2 * within-trajectory variance).
    About 0 for unordered noise, near 1 for a smooth curve. Also returns the share of
    distinct times shared by at least two trajectories and the number of trajectories.
    ``codes`` are integer trajectory codes (``pd.factorize``).
    """
    c, tt, yy = _ordered(codes, t, y)
    if not len(c):
        return 0.0, 0.0, 0
    same = c[1:] == c[:-1]
    num = float(np.sum(np.diff(yy)[same] ** 2))
    with np.errstate(all="ignore"):
        means = np.bincount(c, weights=yy) / np.bincount(c)
    den = 2.0 * float(np.sum((yy - means[c]) ** 2))
    grid = pd.DataFrame({"c": c, "t": tt}).drop_duplicates().groupby("t").size()
    smooth = 1.0 - num / den if den > 0 else 0.0
    return smooth, float((grid >= 2).mean()), len(np.unique(c))


def _regular(times: np.ndarray) -> bool:
    """
    Sampled on a regular grid: the gaps are whole multiples of the usual step (a missing year
    or month is a gap, not irregular sampling; calendar months of 28-31 days count as one
    step) and most of them are a single step.
    """
    gaps = np.diff(np.sort(times))
    if len(gaps) == 0 or np.any(gaps <= 0):
        return False
    steps = gaps / np.median(gaps)
    whole = np.abs(steps - np.rint(steps)) <= REGULAR_TOLERANCE
    return bool(np.all(whole) and np.mean(np.rint(steps) == 1) >= REGULAR_SINGLE_STEPS)


def _chops_one_series(codes: np.ndarray, t: np.ndarray) -> bool:
    """
    True when a candidate trajectory column only cuts a single series into interleaved
    pieces: every time occurs once in the whole table (no parallel trajectories), yet the
    rows switch between its values far more often than consecutive episodes would (a
    measured quantity with a few repeated values, e.g. a regulated outflow).
    """
    if pd.Series(t).duplicated().mean() > 0.05:
        return False  # parallel trajectories share times
    switches = int(np.sum(np.diff(codes[np.argsort(t, kind="stable")]) != 0))
    return switches > 2 * len(np.unique(codes))


def detect_time_structure(
    data: pd.DataFrame,
    target_column: str,
    descriptions: dict[str, str] | None = None,
) -> TimeStructure:
    """Propose a time column and a trajectory column from the uploaded table."""
    descriptions = descriptions or {}
    y_all = pd.to_numeric(data[target_column], errors="coerce")
    mask = y_all.notna().to_numpy()
    y = y_all.to_numpy(dtype=float)[mask]
    n = len(y)
    if n < 2 * MIN_POINTS or np.ptp(y) == 0:
        return TimeStructure(None, evidence={"reason": "too few rows or a constant target"})
    columns = [c for c in data.columns if c != target_column]

    def named(col: str, words: set[str]) -> bool:
        return bool(_words(f"{col} {descriptions.get(col, '')}") & words)

    times: dict[str, np.ndarray] = {}
    for col in columns:
        values = _as_time(data[col][mask])
        if values is None or np.isnan(values).mean() > 0.2:
            continue
        if len(np.unique(values[np.isfinite(values)])) < MIN_POINTS:
            continue
        times[str(col)] = values
    ranked_times = sorted(times, key=lambda c: not named(c, TIME_WORDS))[:MAX_CANDIDATES]

    # Trajectory candidates as integer codes (-1 = missing); None = a single series.
    candidates: dict[str, np.ndarray] = {}
    for col in columns:
        values = data[col][mask]
        k = values.nunique(dropna=True)
        if 2 <= k <= n // MIN_POINTS and values.notna().mean() > 0.8:
            numeric = pd.api.types.is_numeric_dtype(values)
            integer = numeric and bool(
                np.all(np.mod(values.dropna().to_numpy(dtype=float), 1) == 0)
            )
            # A non-integer number is a measurement unless its own name says it is a unit
            # (its description naming a "station" or "site" is where it was measured)
            if not numeric or integer or bool(_words(str(col)) & GROUP_WORDS):
                candidates[str(col)] = pd.factorize(values)[0]
    groups: list[str | None] = [
        None,
        *sorted(candidates, key=lambda c: not named(c, GROUP_WORDS))[:MAX_CANDIDATES],
    ]

    def codes_of(gcol: str | None) -> np.ndarray:
        return candidates[gcol] if gcol else np.zeros(n, dtype=int)

    scored: list[dict[str, Any]] = []
    for tcol in ranked_times:
        t = times[tcol]
        for gcol in groups:
            if gcol == tcol:
                continue
            codes = codes_of(gcol)
            ok = np.isfinite(t) & (codes >= 0)
            if ok.sum() < 2 * MIN_POINTS:
                continue
            dup = float(pd.DataFrame({"c": codes[ok], "t": t[ok]}).duplicated().mean())
            if dup > 0.05:  # a time axis is (almost) unique within each trajectory
                continue
            if gcol and _chops_one_series(codes[ok], t[ok]):
                continue
            smooth, shared, n_traj = _smoothness(y[ok], codes[ok], t[ok])
            if n_traj == 0:
                continue
            t_named, g_named = named(tcol, TIME_WORDS), bool(gcol) and named(gcol, GROUP_WORDS)
            score = smooth + (0.3 if t_named else 0.0) + (0.15 if g_named else 0.0)
            if gcol:
                score += 0.1 * shared
            scored.append(
                {
                    "time_column": tcol,
                    "group_column": gcol,
                    "score": round(score, 3),
                    "smoothness": round(smooth, 3),
                    "shared_time_grid": round(shared, 2),
                    "n_trajectories": n_traj,
                    "time_named": t_named,
                    "group_named": bool(g_named),
                }
            )
    if not scored:
        return TimeStructure(None, evidence={"reason": "no column orders the rows in time"})
    scored.sort(key=lambda d: -d["score"])
    best = scored[0]
    smooth = best["smoothness"]
    # A smooth curve along an unnamed column is usually just a static dependence on a
    # predictor, so without a time-like name confidence needs a shared sampling grid.
    if best["time_named"] and smooth >= 0.5:
        confidence = "strong"
    elif (best["time_named"] and smooth >= 0.15) or (
        smooth >= 0.5 and best["group_column"] and best["shared_time_grid"] >= 0.5
    ):
        confidence = "weak"
    else:
        confidence = "none"

    tcol, gcol = best["time_column"], best["group_column"]
    t, codes = times[tcol], codes_of(gcol)
    ok = np.isfinite(t) & (codes >= 0)
    c, tt = _ordered(codes[ok], t[ok])
    segments = np.split(tt, np.flatnonzero(np.diff(c)) + 1) if len(c) else []
    counts = [len(seg) for seg in segments]
    regular = [_regular(seg) for seg in segments]
    return TimeStructure(
        time_column=tcol,
        group_column=gcol,
        confidence=confidence,
        n_trajectories=len(counts),
        points_min=int(min(counts)) if counts else 0,
        points_median=float(np.median(counts)) if counts else 0.0,
        regular=bool(regular) and all(regular),
        evidence={
            "smoothness_along_time": smooth,
            "smoothness_note": "1 - successive-difference variance ratio of the target along time "
            "within trajectories: ~0 for unordered rows, near 1 for a smooth curve",
            "shared_time_grid": best["shared_time_grid"],
            "time_column_named_like_time": best["time_named"],
            "group_column_named_like_a_unit": best["group_named"],
        },
        alternatives=[
            {k: d[k] for k in ("time_column", "group_column", "smoothness", "n_trajectories")}
            for d in scored[1:4]
        ],
    )


# ---------------------------------------------------------------------------
# Dynamics dataset
# ---------------------------------------------------------------------------


def local_derivative(t: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Smoothed value and first derivative by local quadratic regression (Savitzky-Golay
    generalised to irregular spacing): a window of neighbouring points around each
    observation, the fit's intercept and slope at that time. All windows are solved
    in one batched least-squares call.
    """
    n = len(t)
    window = min(n, MAX_WINDOW, max(5, 2 * (n // 8) + 3))
    lo = np.clip(np.arange(n) - window // 2, 0, n - window)
    idx = lo[:, None] + np.arange(window)
    dt = t[idx] - t[:, None]
    design = np.stack([np.ones_like(dt), dt, dt**2], axis=-1)
    coef = (np.linalg.pinv(design) @ y[idx][..., None])[..., 0]
    return coef[:, 0], coef[:, 1]


@dataclass
class Episode:
    """One stretch to simulate: start value, observation times, observed values, inputs."""

    key: str
    t0: float
    y0: float
    t: np.ndarray
    y: np.ndarray
    input_t: np.ndarray
    inputs: dict[str, np.ndarray]


@dataclass
class DynamicsData:
    """The rate-of-change problem for a confirmed time structure."""

    structure: TimeStructure
    state: str  # the target alias, the ODE's state variable
    inputs: list[str]  # aliases of the exogenous variables
    fit_data: FitData
    train_episodes: list[Episode]
    holdout_episodes: list[Episode]
    regime: str  # trajectories | final_segment
    n_trajectories: int
    fill_value: float  # mean training target: the prediction where a simulation diverges
    derivative_snr: float | None = None
    keys: np.ndarray | None = field(default=None, repr=False)  # trajectory of each fit row

    @property
    def variables(self) -> list[str]:
        return [self.state, *self.inputs]

    @property
    def rate(self) -> str:
        return f"d{self.state}/dt"

    def split_info(self) -> dict[str, Any]:
        holdout_points = sum(len(e.t) for e in self.holdout_episodes)
        return {
            "time_column": self.structure.time_column,
            "group_column": self.structure.group_column,
            "regime": self.regime,
            "trajectories": self.n_trajectories,
            "train_rows": self.fit_data.n,
            "holdout_trajectories": len(self.holdout_episodes),
            "holdout_points": holdout_points,
            "scored_on": (
                f"{len(self.holdout_episodes)} held-out whole trajectories"
                if self.regime == "trajectories"
                else f"the final 20% of each series ({holdout_points} points)"
            )
            if self.holdout_episodes
            else "no holdout (too few points)",
            "cv": "folds keep trajectories whole"
            if self.regime == "trajectories"
            else "contiguous blocks in time",
        }

    def summary(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "rate": self.rate,
            "inputs": self.inputs,
            "split": self.split_info(),
            "dydt_noise_ceiling_r2": self.fit_data.ceiling_r2
            and round(self.fit_data.ceiling_r2, 4),
            "derivative_snr": self.derivative_snr,
            "note": "Scores of rate laws are on the derivative and are not comparable with "
            "static R2 on the target; simulation R2 (integrating the law from each trajectory's "
            "start) is the real test.",
        }


def build_dynamics(
    data: pd.DataFrame,
    structure: TimeStructure,
    target_column: str,
    state_alias: str,
    input_columns: dict[str, str],
    seed: int = 0,
    holdout_fraction: float = 0.2,
) -> DynamicsData:
    """
    Build the derivative regression problem. ``input_columns`` maps input aliases to
    their original columns (continuous predictors other than time and trajectory).
    """
    tcol, gcol = structure.time_column, structure.group_column
    if tcol is None or tcol not in data.columns:
        raise ValueError(f"Unknown time column {tcol!r}")
    if gcol is not None and gcol not in data.columns:
        raise ValueError(f"Unknown trajectory column {gcol!r}")
    t_all = _as_time(data[tcol])
    if t_all is None:
        raise ValueError(f"Column {tcol!r} is neither numeric nor a date")
    frame = pd.DataFrame({"__t": t_all, "__y": pd.to_numeric(data[target_column], errors="coerce")})
    # Rows without a trajectory id are dropped, not pooled into one "nan" trajectory.
    frame["__g"] = data[gcol].astype(str).where(data[gcol].notna()).to_numpy() if gcol else "all"
    for alias, col in input_columns.items():
        frame[alias] = pd.to_numeric(data[col], errors="coerce").to_numpy()
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    # Repeated times within a trajectory are averaged (replicate measurements).
    frame = frame.groupby(["__g", "__t"], as_index=False, sort=True).mean(numeric_only=True)
    trajectories = {
        k: g.sort_values("__t").reset_index(drop=True)
        for k, g in frame.groupby("__g", sort=True)
        if len(g) >= MIN_POINTS
    }
    if not trajectories:
        raise ValueError(
            f"No trajectory has {MIN_POINTS} or more time points with complete values "
            f"(time={tcol!r}, trajectory={gcol!r})"
        )

    rng = np.random.default_rng(seed)
    keys = sorted(trajectories)
    inputs = list(input_columns)
    train_parts: list[pd.DataFrame] = []
    train_eps: list[Episode] = []
    hold_eps: list[Episode] = []

    def episode(key: str, g: pd.DataFrame, start: pd.DataFrame, row: int, obs) -> Episode:
        """Simulate from ``start``'s smoothed value at ``row``; inputs come from ``g``."""
        return Episode(
            key=key,
            t0=float(start["__t"].iloc[row]),
            y0=float(start["__ys"].iloc[row]),
            t=obs["__t"].to_numpy(dtype=float),
            y=obs["__y"].to_numpy(dtype=float),
            input_t=g["__t"].to_numpy(dtype=float),
            inputs={a: g[a].to_numpy(dtype=float) for a in inputs},
        )

    def with_derivative(g: pd.DataFrame) -> pd.DataFrame:
        ys, dy = local_derivative(g["__t"].to_numpy(dtype=float), g["__y"].to_numpy(dtype=float))
        return g.assign(__ys=ys, __dy=dy)

    if len(keys) >= 3:
        regime = "trajectories"
        order = list(rng.permutation(keys))
        n_hold = min(max(1, round(holdout_fraction * len(keys))), len(keys) - 2)
        held, kept = order[:n_hold], order[n_hold:]
        for k in kept:
            g = with_derivative(trajectories[k])
            train_parts.append(g.assign(__k=k))
            train_eps.append(episode(k, g, g, 0, g))
        for k in held:
            g = with_derivative(trajectories[k])
            hold_eps.append(episode(k, g, g, 0, g.iloc[1:]))
    else:
        regime = "final_segment"
        for k in keys:
            g = trajectories[k]
            n_hold = round(holdout_fraction * len(g))
            if len(g) - n_hold < MIN_POINTS or n_hold < 2:
                n_hold = 0
            train = with_derivative(g.iloc[: len(g) - n_hold].reset_index(drop=True))
            train_parts.append(train.assign(__k=k))
            train_eps.append(episode(k, train, train, 0, train))
            if n_hold:
                hold_eps.append(episode(k, g, train, -1, g.iloc[len(g) - n_hold :]))

    train = pd.concat(train_parts, ignore_index=True)
    fill_value = float(train["__y"].mean())
    if len(train) > MAX_DYNAMIC_ROWS:  # thin the rows; derivatives already used whole series
        rows = np.sort(rng.choice(len(train), MAX_DYNAMIC_ROWS, replace=False))
        train = train.iloc[rows].reset_index(drop=True)
    n = len(train)
    if n < 2 * MIN_POINTS:
        raise ValueError(f"Only {n} training points along time — not enough for a rate law")
    row_keys = train["__k"].to_numpy()
    if regime == "trajectories":
        groups = list(rng.permutation(sorted(set(row_keys))))
        n_folds = min(5, len(groups))
        folds = [np.where(np.isin(row_keys, chunk))[0] for chunk in np.array_split(groups, n_folds)]
    else:
        n_folds = int(np.clip(n // MIN_POINTS, 2, 5))
        folds = list(np.array_split(np.arange(n), n_folds))
    X = {state_alias: train["__ys"].to_numpy(dtype=float)}
    X |= {a: train[a].to_numpy(dtype=float) for a in inputs}
    dydt = train["__dy"].to_numpy(dtype=float)
    fit_data = FitData(X=X, y=dydt, folds=[f for f in folds if len(f)])
    fit_data.ceiling_r2 = _ceiling(X, dydt, fit_data.folds, seed)

    resid = train["__y"].to_numpy(dtype=float) - train["__ys"].to_numpy(dtype=float)
    noise = float(np.std(resid))
    snr = float(np.std(train["__ys"]) / noise) if noise > 0 else None
    return DynamicsData(
        structure=structure,
        state=state_alias,
        inputs=inputs,
        fit_data=fit_data,
        train_episodes=train_eps,
        holdout_episodes=hold_eps,
        regime=regime,
        n_trajectories=len(keys),
        fill_value=fill_value,
        derivative_snr=None if snr is None else round(snr, 1),
        keys=row_keys,
    )


def _ceiling(
    X: dict[str, np.ndarray], y: np.ndarray, folds: list[np.ndarray], seed: int
) -> float | None:
    """Out-of-fold R2 of a tree ensemble on the derivative (same folds as the fits)."""
    if len(y) < 20 or len(folds) < 2:
        return None
    M = np.column_stack(list(X.values()))
    oof = np.full(len(y), np.nan)
    model = _forests(seed)[1]  # the profile's extra-trees benchmark (refit per fold)
    for test in folds:
        mask = np.ones(len(y), dtype=bool)
        mask[test] = False
        model.fit(M[mask], y[mask])
        oof[test] = model.predict(M[test])
    return r2_score(y, oof)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


class _Diverged(Exception):
    pass


def _simulate_episode(
    expr: ParsedExpression, params: dict[str, float], state: str, ep: Episode, bound: float
) -> np.ndarray | None:
    calls = [0]
    started = time.monotonic()

    def rhs(t: float, s: np.ndarray) -> list[float]:
        calls[0] += 1
        if calls[0] > SIM_MAX_EVALS or time.monotonic() - started > SIM_MAX_S:
            raise _Diverged("too stiff or too slow")
        if not np.isfinite(s[0]) or abs(s[0]) > bound:
            raise _Diverged("blew up")
        X = {state: np.array([s[0]])}
        X |= {a: np.array([np.interp(t, ep.input_t, v)]) for a, v in ep.inputs.items()}
        out = float(expr.evaluate(X, params)[0])
        if not np.isfinite(out):
            raise _Diverged("undefined")
        return [out]

    t_end = float(ep.t.max())
    if t_end <= ep.t0:
        return None
    try:
        sol = solve_ivp(
            rhs,
            (ep.t0, t_end),
            [ep.y0],
            t_eval=np.clip(ep.t, ep.t0, t_end),
            method="LSODA",
            rtol=1e-4,
            atol=1e-8 * max(1.0, abs(ep.y0)),
        )
    except _Diverged:
        return None
    except Exception as e:  # numerical failures are a property of the law
        logger.debug(f"Simulation failed for {expr.source}: {e}")
        return None
    if not sol.success or sol.y.shape[1] != len(ep.t) or not np.all(np.isfinite(sol.y[0])):
        return None
    return sol.y[0]


def simulate(
    expr: ParsedExpression,
    params: dict[str, float],
    state: str,
    episodes: list[Episode],
    fill_value: float,
    traces: bool = False,
) -> dict[str, Any] | None:
    """
    Integrate the rate law over each episode and score it on the observed target.
    A diverged episode is predicted by ``fill_value`` so it counts as error.
    """
    if not episodes:
        return None
    used = episodes[:MAX_SIM_EPISODES]
    y = np.concatenate([e.y for e in used])
    bound = 1e3 * ((float(np.ptp(y)) or 1.0) + float(np.max(np.abs(y))))
    preds, bad, out_traces = [], [], []
    n_diverged = 0
    for ep in used:
        sim = _simulate_episode(expr, params, state, ep, bound)
        n_diverged += sim is None
        bad.append(np.full(len(ep.t), sim is None))
        preds.append(np.full(len(ep.t), fill_value) if sim is None else sim)
        if traces:
            out_traces.append(
                {
                    "trajectory": ep.key,
                    "t": ep.t.tolist(),
                    "measured": ep.y.tolist(),
                    "simulated": None if sim is None else sim.tolist(),
                }
            )
    out = holdout_metrics(y, np.concatenate(preds), np.concatenate(bad))
    out |= {"n_episodes": len(used), "n_diverged": n_diverged}
    if traces:
        out["traces"] = out_traces
    return out
