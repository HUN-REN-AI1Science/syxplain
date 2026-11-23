"""
Orders of an automatic ARIMA fit of the target: which earlier values and which earlier
errors a long series offers as features.

An automatic seasonal ARIMA search with the current features as regressors (pmdarima's
``auto_arima``) is run on the training part of the longest trajectory. Its orders say how
far back the series remembers:
- p and d (and the seasonal P and D): the target this many steps earlier;
- q (and the seasonal Q): the error of the fit this many steps earlier. An error is the
  measured value minus the value the fit predicted one step ahead from earlier
  measurements only, so it is known before the row it is used on.

The fitted ARIMA model is never a candidate equation. It only names the features; the
symbolic regression decides which of them an equation uses. The parameters come from the
training rows; the errors of the holdout rows are computed with those parameters from the
measurements before each row, exactly like a lag of the target.
"""

import logging
import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from backend.services.discovery.series import SeriesGrid

logger = logging.getLogger(__name__)

MAX_ORDER = 5  # largest p and q searched
MAX_SEASON = 24  # longest season (in steps) a seasonal fit is tried for
MIN_SEASONS = 3  # training seasons a seasonal fit needs
MAX_REGRESSORS = 6  # current features passed to the fit
MAX_FROM_ORDERS = 8  # features the orders may add
CALENDAR_YEAR_DAYS = 365.25


@dataclass
class SeriesOrders:
    """The orders, the lags they name and the one-step errors of every uploaded row."""

    order: tuple[int, int, int]
    seasonal: tuple[int, int, int, int]  # P, D, Q and the season length in steps
    target_lags: list[int]
    error_lags: list[int]
    errors: np.ndarray  # measured minus predicted one step ahead (NaN: none)
    regressors: list[str]
    diagnostics: dict[str, Any] | None = None  # what the fit leaves open (training rows)
    plot_b64: str | None = None  # the same as a picture (PNG, base64)

    def record(self) -> dict[str, Any]:
        p, d, q = self.order
        P, D, Q, m = self.seasonal
        out: dict[str, Any] = {
            "method": "automatic ARIMA search (auto_arima) on the training rows of the "
            "longest series, with the current features as regressors",
            "p": p,
            "d": d,
            "q": q,
            "target_lags": self.target_lags,
            "error_lags": self.error_lags,
            "regressors": self.regressors,
        }
        if m > 1:
            out |= {"season_steps": m, "seasonal_p": P, "seasonal_d": D, "seasonal_q": Q}
        if self.diagnostics:
            out["diagnostics"] = self.diagnostics
        return out


def season_steps(grid: SeriesGrid, n_train: int) -> int:
    """Steps in a calendar year for a date series (1: no seasonal fit)."""
    if grid.dates is None or grid.step_size <= 0:
        return 1
    m = round(CALENDAR_YEAR_DAYS / grid.step_size)
    if abs(m * grid.step_size - CALENDAR_YEAR_DAYS) > 0.1 * CALENDAR_YEAR_DAYS:
        return 1
    return m if 2 <= m <= MAX_SEASON and n_train >= MIN_SEASONS * m else 1


def lags_of(order: tuple[int, int, int], seasonal: tuple[int, int, int, int]) -> tuple[list, list]:
    """The target lags (from p, d, P, D) and the error lags (from q, Q), nearest first."""
    (p, d, q), (P, D, Q, m) = order, seasonal
    near = p + d  # with d differences, p values of the differenced series reach back p + d
    target = list(range(1, near + 1))
    target += [m * k + j for k in range(1, P + D + 1) for j in range(near + 1)]
    errors = list(range(1, q + 1)) + [m * k for k in range(1, Q + 1)]
    return sorted(set(target)), sorted(set(errors))


def _filled(values: np.ndarray) -> np.ndarray:
    """Gaps filled along the series (for the order search only, which takes no gaps)."""
    return pd.Series(values).interpolate(limit_direction="both").to_numpy(dtype=float)


def fit_orders(
    grid: SeriesGrid,
    target: np.ndarray,
    regressors: dict[str, np.ndarray],
    train_end: dict[int, float],
) -> SeriesOrders:
    """
    ``target`` and ``regressors`` hold one value per uploaded row; ``train_end`` gives the
    time of the last training row of each trajectory. Raises when no fit is possible.
    """
    import pmdarima as pm
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    y = grid.dense(target)
    cells = {k: np.flatnonzero(grid.cell_key == k) for k in train_end}
    n_train = {k: int(np.sum(grid.cell_time[c] <= train_end[k] + 1e-9)) for k, c in cells.items()}
    longest = max(n_train, key=lambda k: int(np.isfinite(y[cells[k]][: n_train[k]]).sum()))
    m = season_steps(grid, n_train[longest])

    # Regressors: current features with a value in every cell after filling short gaps
    X, names = {}, []
    for name, values in list(regressors.items())[:MAX_REGRESSORS]:
        dense = grid.dense(values)
        filled = np.full(len(dense), np.nan)
        for c in cells.values():
            filled[c] = _filled(dense[c])
        used = np.concatenate(list(cells.values()))
        if np.all(np.isfinite(filled[used])) and np.std(filled[cells[longest]]) > 0:
            X[name] = filled
            names.append(name)

    def design(c: np.ndarray, use: list[str]) -> np.ndarray | None:
        return np.column_stack([X[n][c] for n in use]) if use else None

    def search(use: list[str]) -> tuple[Any, list[str]]:
        c = cells[longest][: n_train[longest]]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = pm.auto_arima(
                _filled(y[c]),
                X=design(c, use),
                seasonal=m > 1,
                m=m,
                max_p=MAX_ORDER,
                max_q=MAX_ORDER,
                stepwise=True,
                suppress_warnings=True,
                error_action="ignore",
            )
        return fit, use

    try:
        fit, names = search(names)
    except Exception as e:  # collinear or ill-scaled regressors: the series alone
        logger.info(f"Order search with regressors failed ({e}); retrying without them")
        fit, names = search([])
    order, seasonal = tuple(fit.order), tuple(fit.seasonal_order)
    result = fit.arima_res_
    spec = result.model
    burn = order[1] + seasonal[1] * seasonal[3]  # the first errors only start the differences

    cell_errors = np.full(len(y), np.nan)
    for c in cells.values():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = SARIMAX(
                y[c],
                exog=design(c, names),
                order=order,
                seasonal_order=seasonal,
                trend=spec.trend,
                enforce_stationarity=spec.enforce_stationarity,
                enforce_invertibility=spec.enforce_invertibility,
            )
            resid = np.asarray(model.filter(result.params).resid, dtype=float)
        resid[:burn] = np.nan
        cell_errors[c] = resid
    errors = np.full(len(target), np.nan)
    on = grid.cell >= 0
    errors[on] = cell_errors[grid.cell[on]]
    errors[~np.isfinite(target)] = np.nan  # a row without a measurement has no error

    target_lags, error_lags = lags_of(order, seasonal)
    found = SeriesOrders(order, seasonal, target_lags, error_lags, errors, names)
    try:  # a reading aid for the feature step: never a reason to lose the orders
        c = cells[longest][: n_train[longest]]
        found.diagnostics = diagnose(y[c], cell_errors[c])
        found.plot_b64 = plot(y[c], cell_errors[c])
    except Exception as e:
        logger.warning(f"Diagnostics of the automatic ARIMA fit failed: {e}", exc_info=True)
    return found


# ------------------------------------------------------------------------- diagnostics

MAX_MEMORY_LAG = 40
FOREST_LAGS = 3


def _memory(values: np.ndarray, max_lag: int) -> np.ndarray:
    """Correlation of a series with itself k steps earlier, k = 1..max_lag (gaps left out)."""
    out = np.full(max_lag, np.nan)
    for k in range(1, max_lag + 1):
        a, b = values[k:], values[:-k]
        ok = np.isfinite(a) & np.isfinite(b)
        if ok.sum() >= 8 and np.std(a[ok]) > 0 and np.std(b[ok]) > 0:
            out[k - 1] = np.corrcoef(a[ok], b[ok])[0, 1]
    return out


def _line_and_forest(y: np.ndarray) -> dict[str, float] | None:
    """CV R2 (contiguous blocks) of a line and of a tree ensemble on the last values."""
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression

    rows = np.arange(FOREST_LAGS, len(y))
    X = np.column_stack([y[rows - k] for k in range(1, FOREST_LAGS + 1)])
    t = y[rows]
    ok = np.isfinite(t) & np.all(np.isfinite(X), axis=1)
    X, t = X[ok], t[ok]
    if len(t) < 40:
        return None
    pred = {"line": np.empty(len(t)), "forest": np.empty(len(t))}
    for test in np.array_split(np.arange(len(t)), 5):
        train = np.setdiff1d(np.arange(len(t)), test)
        pred["line"][test] = LinearRegression().fit(X[train], t[train]).predict(X[test])
        forest = RandomForestRegressor(200, min_samples_leaf=3, random_state=0)
        pred["forest"][test] = forest.fit(X[train], t[train]).predict(X[test])
    total = float(np.sum((t - t.mean()) ** 2))
    return {k: round(1 - float(np.sum((t - v) ** 2)) / total, 3) for k, v in pred.items()}


def diagnose(y: np.ndarray, errors: np.ndarray) -> dict[str, Any]:
    """
    What the automatic ARIMA fit leaves open, on the training rows of the longest series:
    memory at longer distances, memory left in its errors, and signs that the series does
    not follow a line of its own past.
    """
    n = int(np.isfinite(y).sum())
    max_lag = max(3, min(MAX_MEMORY_LAG, n // 4))
    noise = 2 / np.sqrt(n)
    of_target, of_errors = _memory(y, max_lag), _memory(errors, max_lag)
    peaks = [
        k
        for k in range(2, max_lag)
        if np.isfinite(of_target[k - 2 : k + 1]).all()
        and of_target[k - 1] > max(of_target[k - 2], of_target[k], noise)
    ]
    peaks = sorted(peaks, key=lambda k: -of_target[k - 1])[:4]
    left = [k for k in range(1, max_lag + 1) if abs(np.nan_to_num(of_errors[k - 1])) > noise]
    left = sorted(left, key=lambda k: -abs(of_errors[k - 1]))[:8]
    out: dict[str, Any] = {
        "rows": n,
        "noise_level_of_a_correlation": round(float(noise), 3),
        "memory_of_target": {
            "first_steps": [round(float(v), 3) for v in of_target[:5]],
            "peaks": [{"steps": k, "r": round(float(of_target[k - 1]), 3)} for k in sorted(peaks)],
        },
        "memory_left_in_errors": [
            {"steps": k, "r": round(float(of_errors[k - 1]), 3)} for k in sorted(left)
        ],
    }
    # Errors by the level of the previous value: a line of the past leaves none of this
    prev, e = y[:-1], errors[1:]
    ok = np.isfinite(prev) & np.isfinite(e)
    if ok.sum() >= 30:
        prev, e = prev[ok], e[ok]
        cuts = np.quantile(prev, [1 / 3, 2 / 3])
        part = np.digitize(prev, cuts)
        out["errors_by_previous_level"] = [
            {
                "third": name,
                "mean_error": round(float(e[part == i].mean()), 4),
                "spread": round(float(e[part == i].std()), 4),
            }
            for i, name in enumerate(("low", "middle", "high"))
            if np.any(part == i)
        ]
    steps = np.diff(y)
    steps = steps[np.isfinite(steps)]
    up, down = steps[steps > 0], steps[steps < 0]
    if len(up) and len(down):
        out["rises_and_falls"] = {
            "share_of_rising_steps": round(len(up) / len(steps), 3),
            "mean_rise": round(float(up.mean()), 4),
            "mean_fall": round(float(-down.mean()), 4),
        }
    scores = _line_and_forest(y)
    if scores:
        out["line_against_forest"] = scores | {
            "features": f"the target 1 to {FOREST_LAGS} steps earlier",
            "note": "CV R2 over contiguous blocks; a forest clearly above the line means the "
            "series depends on its past in a nonlinear way",
        }
    return out


def plot(y: np.ndarray, errors: np.ndarray) -> str:
    """The series, its memory, the memory left in the errors and the errors by level (PNG)."""
    import base64
    import io

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = int(np.isfinite(y).sum())
    max_lag = max(3, min(MAX_MEMORY_LAG, n // 4))
    noise = 2 / np.sqrt(n)
    lags = np.arange(1, max_lag + 1)
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    axes[0, 0].plot(y, lw=0.9)
    axes[0, 0].set(title="Target along time (training rows)", xlabel="step")
    for ax, values, title in (
        (
            axes[0, 1],
            _memory(y, max_lag),
            "Memory of the target: correlation with itself k steps earlier",
        ),
        (axes[1, 0], _memory(errors, max_lag), "Memory left in the errors of the ARIMA fit"),
    ):
        ax.bar(lags, np.nan_to_num(values), width=0.7)
        ax.axhline(noise, color="grey", ls="--", lw=0.8)
        ax.axhline(-noise, color="grey", ls="--", lw=0.8)
        ax.set(title=title, xlabel="k (steps)")
    axes[1, 1].scatter(y[:-1], errors[1:], s=8, alpha=0.6)
    axes[1, 1].axhline(0, color="grey", lw=0.8)
    axes[1, 1].set(
        title="Error of the ARIMA fit against the previous value",
        xlabel="target one step earlier",
        ylabel="error",
    )
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=90)
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode()
