"""
Generic least-squares fitting, cross-validation and residual diagnostics.

Every candidate — classic family, agent formula or PySR equation — goes
through ``fit_model`` so they are scored identically. The diagnostics turn
residual structure into plain-language reasons ("residuals still depend on
pH"), which is what the agent and the explanation step use to understand
*why* a form does not fit.
"""

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
from scipy import optimize, stats

from backend.services.discovery.expression import ParsedExpression, substitute_parameters

logger = logging.getLogger(__name__)

TRANSFORMS = {
    None: (lambda y: y, lambda z: z),
    "log": (np.log, np.exp),
    "log1p": (np.log1p, np.expm1),
    "sqrt": (np.sqrt, np.square),
}


def target_space(y: np.ndarray, transform: str | None) -> np.ndarray:
    """The target as a model with this transform sees it (may hold NaN/inf)."""
    with np.errstate(all="ignore"):
        return TRANSFORMS[transform][0](y)


# Residuals this autocorrelated along time (and significant) mean a missing memory effect
AUTOCORR_FLAG = 0.3


def lag1_autocorrelation(resid: np.ndarray, keys: np.ndarray) -> tuple[float | None, int]:
    """
    Pooled lag-1 autocorrelation of residuals over consecutive rows of the same
    trajectory (rows sorted by trajectory, then time), and the number of pairs.
    """
    same = keys[1:] == keys[:-1]
    a, b = resid[1:][same], resid[:-1][same]
    if len(a) < 10:
        return None, len(a)
    mean = float(np.mean(resid))
    den = float(np.sum((resid - mean) ** 2)) / len(resid)
    if den == 0:
        return None, len(a)
    return float(np.mean((a - mean) * (b - mean)) / den), len(a)


def time_blocks(keys: np.ndarray, n_folds: int) -> list[np.ndarray]:
    """CV folds of contiguous time blocks: fold j is the j-th block of every trajectory
    (rows sorted by trajectory, then time; ``keys`` gives each row's trajectory)."""
    chunks: list[list[np.ndarray]] = [[] for _ in range(n_folds)]
    for rows in np.split(np.arange(len(keys)), np.flatnonzero(np.diff(keys)) + 1):
        for j, block in enumerate(np.array_split(rows, n_folds)):
            chunks[j].append(block)
    folds = [np.concatenate(c) for c in chunks if c]
    return [f for f in folds if len(f)]


# A model whose CV R2 is within this distance of the noise ceiling "matches" it
# (widened by twice the ceiling's own uncertainty when that is known).
CEILING_TOL = 0.02
# Below this ceiling even a flexible model cannot predict the target.
SIGNAL_MIN_R2 = 0.05


@dataclass
class FitData:
    """Training data as seen by the fitting engine (feature arrays keyed by alias)."""

    X: dict[str, np.ndarray]
    y: np.ndarray
    folds: list[np.ndarray]  # test indices of each CV fold
    ceiling_r2: float | None = None  # raw (unclipped) nonparametric benchmark
    ceiling_sd: float | None = None
    # Rows of a series: the trajectory of each row, rows in time order within each
    series: np.ndarray | None = None

    @property
    def n(self) -> int:
        return len(self.y)

    @property
    def has_signal(self) -> bool | None:
        if self.ceiling_r2 is None:
            return None
        return self.ceiling_r2 > SIGNAL_MIN_R2

    @property
    def ceiling_tol(self) -> float:
        return max(CEILING_TOL, 2 * (self.ceiling_sd or 0.0))


@dataclass
class ModelResult:
    """Outcome of fitting one candidate model."""

    model_id: str
    kind: str  # classic | custom | symbolic
    name: str
    label: str
    expression: str
    features: list[str]
    target_transform: str | None = None
    fitted_expression: str = ""  # original target scale (wrapped in the inverse transform)
    fitted_core: str = ""  # same model in the transformed-target space (what PySR would see)
    params: dict[str, float] = field(default_factory=dict)
    param_se: dict[str, float | None] = field(default_factory=dict)
    complexity: int = 0
    n_params: int = 0
    cv_r2: float | None = None
    cv_rmse: float | None = None
    cv_se: float | None = None  # standard error of the per-fold RMSE
    n_undefined: int = 0  # CV rows where the model was undefined (counted as errors)
    train_r2: float | None = None
    aic: float | None = None
    bic: float | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    verdict: str = "failed"  # good | adequate | poor | failed | no_signal
    error: str | None = None
    source: str | None = None  # e.g. PySR search id
    holdout: dict[str, float] | None = None
    ill_conditioned: bool = False
    # static: target = f(features); dynamic: d(target)/dt = f(target, inputs), scored on the
    # derivative, so the two never share a ranking
    problem: str = "static"
    parsed: ParsedExpression | None = field(default=None, repr=False, compare=False)
    oof_pred: np.ndarray | None = field(default=None, repr=False, compare=False)

    @property
    def simulation(self) -> dict[str, Any]:
        """Rate laws: the law integrated over the training trajectories ({} if not run)."""
        return self.diagnostics.get("simulation") or {}

    @property
    def n_undefined_total(self) -> int:
        """Rows where the model is undefined, in CV and on the holdout."""
        return self.n_undefined + ((self.holdout or {}).get("n_undefined") or 0)

    def event_fields(self) -> dict[str, Any]:
        """Fields of an activity event about this model, so the UI can rank models live."""
        return {
            "model_id": self.model_id,
            "label": self.label,
            "expression": self.fitted_expression,
            "cv_r2": _r(self.cv_r2),
            "problem": self.problem,
        }

    def brief(self) -> dict[str, Any]:
        """Compact view for the agent's context window."""
        out: dict[str, Any] = {
            "model_id": self.model_id,
            "name": self.name,
            "features": self.features,
            "verdict": self.verdict,
        }
        if self.error:
            out["error"] = self.error
            return out
        out |= {
            "fitted": self.fitted_expression,
            "cv_r2": _r(self.cv_r2),
            "cv_rmse": _r(self.cv_rmse, 5),
            "cv_se": _r(self.cv_se, 5),
            "aic": _r(self.aic, 1),
            "n_params": self.n_params,
            "complexity": self.complexity,
        }
        if self.target_transform:
            out["target_transform"] = self.target_transform
        if self.simulation:
            out["simulation_r2"] = self.simulation.get("r2")
            out["simulation_diverged"] = self.simulation.get("n_diverged")
        if self.reasons:
            out["reasons"] = self.reasons
        return out

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("parsed", None)
        d.pop("oof_pred", None)
        return d


def _r(v: float | None, nd: int = 4) -> float | None:
    if v is None or not np.isfinite(v):
        return None
    return round(float(v), nd)


def r2_score(y: np.ndarray, pred: np.ndarray) -> float:
    sst = float(np.sum((y - y.mean()) ** 2))
    if sst == 0:
        return 0.0
    return 1.0 - float(np.sum((y - pred) ** 2)) / sst


# ---------------------------------------------------------------------------
# Core fitting
# ---------------------------------------------------------------------------


def _subset(X: dict[str, np.ndarray], idx: np.ndarray) -> dict[str, np.ndarray]:
    return {k: v[idx] for k, v in X.items()}


def _least_squares(
    expr: ParsedExpression,
    X: dict[str, np.ndarray],
    z: np.ndarray,
    p0: np.ndarray,
    lower: np.ndarray,
    max_nfev: int,
) -> tuple[np.ndarray, float, Any] | None:
    names = expr.parameters
    penalty = 1e3 * (np.nanstd(z) + 1.0) if np.isfinite(z).any() else 1e3

    def residuals(p: np.ndarray) -> np.ndarray:
        pred = expr.evaluate(X, dict(zip(names, p, strict=True)))
        r = pred - z
        bad = ~np.isfinite(r)
        if bad.any():
            r[bad] = penalty
        return r

    try:
        if not names:
            r = residuals(np.array([]))
            return np.array([]), 0.5 * float(r @ r), None
        start = np.clip(p0, lower + 1e-12, None)
        bounds = (lower, np.full_like(lower, np.inf))
        res = optimize.least_squares(
            residuals, start, bounds=bounds, method="trf", x_scale="jac", max_nfev=max_nfev
        )
        return res.x, float(res.cost), res
    except Exception as e:  # numerical failures are expected for bad forms
        logger.debug(f"least_squares failed for {expr.source}: {e}")
        return None


def fit_model(
    result: ModelResult,
    expr: ParsedExpression,
    data: FitData,
    p0: dict[str, float],
    lower_bounds: dict[str, float] | None = None,
    n_starts: int = 6,
    seed: int = 0,
    other_features: list[str] | None = None,
    time_limit_s: float = 20.0,
) -> ModelResult:
    """
    Fit ``expr`` to the training data, cross-validate and diagnose it.

    The model is fit in the transformed target space (``result.target_transform``)
    but all metrics are reported on the original target scale.
    """
    t0 = time.monotonic()
    result.parsed = expr
    result.complexity = expr.complexity
    result.n_params = len(expr.parameters)
    names = expr.parameters
    fwd, inv = TRANSFORMS[result.target_transform]

    y = data.y
    domain = {
        "log": (y <= 0, "a positive target"),
        "sqrt": (y < 0, "a non-negative target"),
        "log1p": (y <= -1, "a target above -1"),
    }.get(result.target_transform)
    if domain is not None and np.any(domain[0]):
        return _fail(result, f"target_transform='{result.target_transform}' needs {domain[1]}")
    with np.errstate(all="ignore"):
        z = fwd(y)

    lower = np.array([(lower_bounds or {}).get(n, -np.inf) for n in names], dtype=float)
    base = np.array([float(p0.get(n, 1.0)) for n in names], dtype=float)
    base = np.where(np.isfinite(base), base, 1.0)
    rng = np.random.default_rng(seed)
    max_nfev = 100 * (len(names) + 1)

    starts = [base]
    for _ in range(max(0, n_starts - 1)):
        scale = np.exp(rng.normal(0, 0.8, size=len(names)))
        jitter = np.where(base == 0, rng.normal(0, 1.0, size=len(names)), base * scale)
        starts.append(jitter)

    best: tuple[np.ndarray, float, Any] | None = None
    for start in starts:
        if time.monotonic() - t0 > time_limit_s:
            break
        out = _least_squares(expr, data.X, z, start, lower, max_nfev)
        if out is not None and np.isfinite(out[1]) and (best is None or out[1] < best[1]):
            best = out

    if best is None:
        return _fail(result, "optimizer failed to converge from any starting point")

    p_hat, _, ls = best
    params = {n: float(v) for n, v in zip(names, p_hat, strict=True)}
    with np.errstate(all="ignore"):
        pred = inv(expr.evaluate(data.X, params))
    if not np.all(np.isfinite(pred)):
        frac = float(np.mean(~np.isfinite(pred)))
        return _fail(
            result,
            f"model is undefined on {frac:.0%} of the data (domain error, e.g. log or power of a negative value)",
        )

    result.params = params
    result.fitted_expression = substitute_parameters(expr.source, params)
    result.fitted_core = result.fitted_expression
    if result.target_transform:
        outer = {"log": "exp", "log1p": "expm1", "sqrt": "square"}[result.target_transform]
        result.fitted_expression = f"{outer}({result.fitted_expression})"

    n, k = data.n, len(names)
    rss = float(np.sum((y - pred) ** 2))
    result.train_r2 = r2_score(y, pred)
    result.aic = n * np.log(max(rss, 1e-300) / n) + 2 * (k + 1)
    result.bic = n * np.log(max(rss, 1e-300) / n) + (k + 1) * np.log(n)

    # Standard errors from the Jacobian at the optimum (transformed space).
    result.param_se, ill_conditioned, max_corr = _standard_errors(ls, n, names)
    result.ill_conditioned = ill_conditioned

    # Cross-validation: refit on each fold starting from the full-data optimum.
    # Rows where a fold model is undefined count as errors (predicted by the fold's
    # training mean) instead of being silently dropped.
    oof = np.full(n, np.nan)
    fold_rmse = []
    n_undefined = 0
    for test_idx in data.folds:
        train_mask = np.ones(n, dtype=bool)
        train_mask[test_idx] = False
        X_tr = _subset(data.X, np.where(train_mask)[0])
        fold_params = params
        if names:
            out = _least_squares(expr, X_tr, z[train_mask], p_hat, lower, max_nfev)
            if out is not None and np.isfinite(out[1]):
                fold_params = dict(zip(names, out[0], strict=True))
            else:
                # The full-data fit has seen this fold, so it must not score it.
                fold_params = None
        if fold_params is None:
            fold_pred = np.full(len(test_idx), np.nan)
        else:
            with np.errstate(all="ignore"):
                fold_pred = inv(expr.evaluate(_subset(data.X, test_idx), fold_params))
        bad = ~np.isfinite(fold_pred)
        if bad.any():
            n_undefined += int(bad.sum())
            fold_pred = np.where(bad, float(np.mean(y[train_mask])), fold_pred)
        oof[test_idx] = fold_pred
        fold_rmse.append(float(np.sqrt(np.mean((y[test_idx] - fold_pred) ** 2))))

    result.n_undefined = n_undefined
    if n_undefined > 0.5 * n:
        result.cv_r2 = None
        result.reasons.append(
            f"cross-validation predictions were undefined on {n_undefined} of {n} rows"
        )
    else:
        result.cv_r2 = r2_score(y, oof)
        result.cv_rmse = float(np.sqrt(np.mean((y - oof) ** 2)))
        result.cv_se = (
            float(np.std(fold_rmse, ddof=1) / np.sqrt(len(fold_rmse)))
            if len(fold_rmse) > 1
            else None
        )
        result.oof_pred = oof
        if n_undefined:
            result.reasons.append(
                f"undefined on {n_undefined} of {n} rows in cross-validation (counted as errors)"
            )

    _diagnose(result, data, y - pred, pred, other_features or [], ill_conditioned, max_corr)
    return result


def _fail(result: ModelResult, msg: str) -> ModelResult:
    result.error = msg
    result.verdict = "failed"
    result.reasons = [msg]
    return result


def _standard_errors(
    ls: Any, n: int, names: tuple[str, ...]
) -> tuple[dict[str, float | None], bool, dict[str, float]]:
    """Parameter SEs, an ill-conditioning flag and each parameter's max |correlation|."""
    k = len(names)
    if ls is None or k == 0 or n <= k:
        return {}, False, {}
    J = ls.jac
    s2 = 2 * ls.cost / (n - k)
    try:
        JTJ = J.T @ J
        cond = np.linalg.cond(JTJ)
        cov = np.linalg.pinv(JTJ) * s2
        var = np.clip(np.diag(cov), 0, None)
        se = np.sqrt(var)
        with np.errstate(all="ignore"):
            corr = cov / np.sqrt(np.outer(var, var))
        np.fill_diagonal(corr, 0.0)
        corr = np.nan_to_num(np.abs(corr))
        max_corr = {name: float(corr[i].max()) if k > 1 else 0.0 for i, name in enumerate(names)}
        return (
            {name: float(v) for name, v in zip(names, se, strict=True)},
            bool(cond > 1e12),
            max_corr,
        )
    except Exception:
        return {}, True, {}


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def binned_dependence(
    resid: np.ndarray, x: np.ndarray, max_bins: int = 10
) -> tuple[float, np.ndarray, np.ndarray] | None:
    """
    Share of residual variance explained by quantile bins of ``x``
    (bias-adjusted eta squared), plus per-bin mean residuals and bin edges.
    """
    n = len(resid)
    bins = min(max_bins, n // 15)
    if bins < 3 or np.ptp(x) == 0:
        return None
    edges = np.unique(np.quantile(x, np.linspace(0, 1, bins + 1)))
    if len(edges) < 4:
        return None
    labels = np.clip(np.searchsorted(edges, x, side="right") - 1, 0, len(edges) - 2)
    B = len(edges) - 1
    total = float(np.sum((resid - resid.mean()) ** 2))
    if total == 0:
        return None
    means = np.array([resid[labels == b].mean() if np.any(labels == b) else 0.0 for b in range(B)])
    counts = np.array([np.sum(labels == b) for b in range(B)])
    between = float(np.sum(counts * (means - resid.mean()) ** 2))
    eta2 = between / total
    adj = (B - 1) / max(n - 1, 1)
    eta2_adj = max(0.0, (eta2 - adj) / (1 - adj)) if adj < 1 else 0.0
    return eta2_adj, means, edges


def _describe_pattern(means: np.ndarray, resid_sd: float) -> str:
    """Translate per-bin mean residuals into 'under/over-predicts at low/mid/high x'."""
    thirds = np.array_split(means, 3)
    words = []
    for region, chunk in zip(("low", "mid", "high"), thirds, strict=True):
        m = float(np.mean(chunk)) if len(chunk) else 0.0
        if abs(m) > 0.15 * resid_sd:
            words.append(f"{'under' if m > 0 else 'over'}predicts at {region} values")
    return ", ".join(words)


def _diagnose(
    result: ModelResult,
    data: FitData,
    resid: np.ndarray,
    pred: np.ndarray,
    other_features: list[str],
    ill_conditioned: bool,
    max_corr: dict[str, float] | None = None,
) -> None:
    diag: dict[str, Any] = {}
    reasons = result.reasons
    resid_sd = float(np.std(resid)) or 1.0

    # 1. Shape misfit along the features the model uses.
    shape_flags = []
    for f in result.features:
        dep = binned_dependence(resid, data.X[f])
        if dep and dep[0] >= 0.05:
            pattern = _describe_pattern(dep[1], resid_sd)
            shape_flags.append((f, dep[0]))
            reasons.append(
                f"wrong curve shape along {f}: a residual pattern explains {dep[0]:.0%} of the "
                f"remaining error" + (f" ({pattern})" if pattern else "")
            )
    diag["shape_misfit"] = {f: round(v, 3) for f, v in shape_flags}

    # 2. Missing variables: residuals that depend on features not in the model.
    # Require both an effect size and Holm-corrected significance, otherwise with
    # many candidate features some noise column is always "missing".
    candidates = []
    y_var = float(np.var(data.y)) or 1.0
    if float(np.var(resid)) / y_var >= 1e-3:
        for f in other_features:
            x = data.X.get(f)
            if x is None or np.ptp(x) == 0:
                continue
            dep = binned_dependence(resid, x)
            sp = stats.spearmanr(resid, x)
            rho = float(sp.statistic) if np.isfinite(sp.statistic) else 0.0
            p_rho = float(sp.pvalue) if np.isfinite(sp.pvalue) else 1.0
            p_bin = 1.0
            if dep:
                labels = np.clip(np.searchsorted(dep[2], x, side="right") - 1, 0, len(dep[2]) - 2)
                groups = [resid[labels == b] for b in np.unique(labels)]
                if len(groups) > 1:
                    p_bin = float(stats.kruskal(*groups).pvalue)
            strength = max(dep[0] if dep else 0.0, rho**2)
            candidates.append((f, strength, rho, min(p_rho, p_bin)))
    # Holm step-down correction over the candidate features
    m = len(candidates)
    missing = []
    for rank, (f, strength, rho, p) in enumerate(sorted(candidates, key=lambda t: t[3])):
        if p * (m - rank) > 0.05:
            break
        if strength >= 0.05:
            missing.append((f, strength, rho))
    missing.sort(key=lambda t: -t[1])
    diag["missing_variables"] = {f: round(s, 3) for f, s, _ in missing}
    for f, s, rho in missing[:3]:
        reasons.append(
            f"missing variable {f}: it explains ~{s:.0%} of the residual variance "
            f"(Spearman rho={rho:+.2f} with residuals)"
        )

    # 3. Heteroscedasticity.
    if len(resid) >= 20 and np.ptp(pred) > 0:
        rho_h = stats.spearmanr(np.abs(resid), pred).statistic
        diag["heteroscedasticity_rho"] = _r(rho_h, 3)
        if np.isfinite(rho_h) and abs(rho_h) >= 0.3:
            trend = "grows" if rho_h > 0 else "shrinks"
            hint = " (multiplicative noise; consider target_transform='log')" if rho_h > 0 else ""
            reasons.append(
                f"residual spread {trend} with the predicted value (rho={rho_h:+.2f}){hint}"
            )

    # 3b. Memory: residuals that follow each other in time (rows of a series).
    autocorr = None
    if data.series is not None:
        autocorr, n_pairs = lag1_autocorrelation(resid, data.series)
        diag["residual_autocorrelation"] = _r(autocorr, 3)
        # z = r * sqrt(pairs) > 2.58: significant at the 1% level
        if (
            autocorr is not None
            and autocorr >= AUTOCORR_FLAG
            and autocorr * np.sqrt(n_pairs) > 2.58
        ):
            reasons.append(
                f"residuals are correlated in time (lag-1 autocorrelation {autocorr:.2f}): a memory "
                "effect is missing, e.g. earlier conditions (lagged features) or the target's "
                "persistence"
            )

    # 4. Parameter identifiability: a parameter whose SE exceeds its value is either
    # simply not different from zero (term can be dropped) or unidentified (traded off
    # against another parameter).
    weak = [
        (n, se / abs(result.params[n]))
        for n, se in result.param_se.items()
        if se is not None
        and result.params.get(n) not in (None, 0.0)
        and se / abs(result.params[n]) > 1.0
    ]
    corr = max_corr or {}
    unidentified = [(n, rel) for n, rel in weak if ill_conditioned or corr.get(n, 0.0) >= 0.9]
    nonsignificant = [(n, rel) for n, rel in weak if (n, rel) not in unidentified]
    if unidentified:
        names = ", ".join(f"{n} (±{rel:.0%})" for n, rel in unidentified)
        reasons.append(
            f"poorly constrained parameters: {names} — the data does not pin down this form "
            "(e.g. the plateau/asymptote is never reached, or terms are redundant)"
        )
    if nonsignificant:
        names = ", ".join(f"{n} (±{rel:.0%})" for n, rel in nonsignificant)
        reasons.append(f"parameters not distinguishable from zero: {names} — try dropping the term")
    if ill_conditioned:
        reasons.append("parameters are strongly correlated with each other (near-singular fit)")
    diag["weak_parameters"] = [n for n, _ in unidentified]
    diag["nonsignificant_parameters"] = [n for n, _ in nonsignificant]

    # 5. Outliers.
    z = (resid - resid.mean()) / resid_sd
    n_out = int(np.sum(np.abs(z) > 3))
    diag["outliers_3sd"] = n_out
    if n_out > max(2, 0.02 * len(resid)):
        reasons.append(f"{n_out} points lie beyond 3 SD of the residuals (heavy tails or outliers)")

    # 6. Gap to the nonparametric noise ceiling (raw, can be negative = no signal).
    cv = result.cv_r2
    ceiling = data.ceiling_r2
    tol = data.ceiling_tol
    has_signal = data.has_signal
    gap = None
    if cv is not None:
        if cv < 0:
            reasons.append("worse than simply predicting the mean on held-out folds")
        if has_signal is False:
            reasons.insert(
                0,
                f"no detectable signal: even a flexible random forest cannot predict the target "
                f"(out-of-fold R2 {ceiling:.3f})",
            )
        elif ceiling is not None:
            gap = ceiling - cv
            diag["ceiling_gap"] = _r(gap, 3)
            if cv > ceiling + tol:
                reasons.append(
                    f"exceeds the nonparametric benchmark (CV R2 {cv:.3f} vs ~{ceiling:.3f}; the "
                    "benchmark underestimates achievable accuracy on small or smooth data)"
                )
            elif gap <= tol:
                reasons.insert(
                    0,
                    f"matches the noise ceiling (CV R2 {cv:.3f} vs ~{ceiling:.3f}); remaining error looks like noise",
                )
            else:
                reasons.append(
                    f"leaves explainable variance: CV R2 {cv:.3f} vs noise ceiling ~{ceiling:.3f}"
                )

    strong_structure = (
        any(v >= 0.1 for _, v in shape_flags)
        or any(s >= 0.1 for _, s, _ in missing)
        or (autocorr is not None and autocorr >= 0.5)
    )
    sound_fit = not ill_conditioned and not unidentified
    if cv is None:
        result.verdict = "poor"
    elif has_signal is False:
        result.verdict = "no_signal" if cv <= SIGNAL_MIN_R2 else "adequate"
    elif gap is not None:
        if gap <= tol and cv > SIGNAL_MIN_R2 and not strong_structure and sound_fit:
            result.verdict = "good"
        elif gap <= 0.10:
            result.verdict = "adequate"
        else:
            result.verdict = "poor"
    else:
        good = cv >= 0.9 and sound_fit
        result.verdict = "good" if good else "adequate" if cv >= 0.7 else "poor"
    result.diagnostics = diag


def score_holdout(
    expr: ParsedExpression,
    params: dict[str, float],
    X: dict[str, np.ndarray],
    y: np.ndarray,
    target_transform: str | None,
    fill_value: float,
) -> dict[str, float] | None:
    """
    Score fixed parameters on held-out data (original target scale). Rows where the
    model is undefined are predicted by ``fill_value`` (the training mean) so they
    count as errors.
    """
    _, inv = TRANSFORMS[target_transform]
    with np.errstate(all="ignore"):
        pred = inv(expr.evaluate(X, params))
    bad = ~np.isfinite(pred)
    if bad.mean() > 0.5:
        return None
    return holdout_metrics(y, np.where(bad, fill_value, pred), bad)


def holdout_metrics(y: np.ndarray, pred: np.ndarray, undefined: np.ndarray) -> dict[str, Any]:
    """Held-out scores; ``undefined`` marks rows predicted by the fill value."""
    err = y - pred
    return {
        "r2": round(r2_score(y, pred), 4),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mae": float(np.mean(np.abs(err))),
        "n": len(y),
        "n_undefined": int(undefined.sum()),
    }


def predict(
    expr: ParsedExpression,
    params: dict[str, float],
    X: dict[str, np.ndarray],
    target_transform: str | None,
) -> np.ndarray:
    _, inv = TRANSFORMS[target_transform]
    with np.errstate(all="ignore"):
        return inv(expr.evaluate(X, params))
