"""
Data profiling for the discovery agent.

Cheap-to-read signals the agent can act on: correlations, mutual information,
permutation importance, a nonparametric "noise ceiling" (out-of-fold R2 of
flexible tree ensembles) that tells whether a poor classic fit is caused by noise
or by the wrong functional form, and gated SHAP effects (importance, interacting
pairs, partial-effect shapes).

The CPU-heavy part (``compute_profile``) is a pure function of arrays so it can run
in a separate process: tree ensembles and SHAP hold the GIL for long stretches and
would otherwise freeze the backend's event loop.
"""

import asyncio
import contextlib
import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import Any

import numpy as np
from scipy import stats

from backend.services.discovery.fitting import binned_dependence, r2_score

logger = logging.getLogger(__name__)

PROFILE_TIMEOUT_S = 240
MAX_CEILING_ROWS = 2000
CEILING_REPEATS = 3
NEGLIGIBLE_SHARE = 0.02  # SHAP share below which a feature gets no shape advice
RELIABLE_CEILING = 0.1  # below this, SHAP effects are not reported


# ---------------------------------------------------------------------------
# Pure computation (runs in the profiling process)
# ---------------------------------------------------------------------------


def _kfold(n: int, k: int, rng: np.random.Generator) -> list[np.ndarray]:
    return np.array_split(rng.permutation(n), k)


def _forests(seed: int):
    from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor

    return [
        RandomForestRegressor(n_estimators=100, min_samples_leaf=3, n_jobs=1, random_state=seed),
        ExtraTreesRegressor(n_estimators=100, min_samples_leaf=3, n_jobs=1, random_state=seed),
    ]


def noise_ceiling(
    X: np.ndarray, y: np.ndarray, seed: int = 0, repeats: int = CEILING_REPEATS
) -> tuple[float, float, list[float], np.ndarray, np.ndarray]:
    """
    Nonparametric benchmark: out-of-fold R2 of the better of a random forest and
    extra-trees, over ``repeats`` reshuffled 5-fold splits.

    Returns:
        (mean R2, sd over repeats, per-repeat R2, permutation-importance mean, sd)
        Importance = drop in out-of-fold R2 when a column is shuffled (5 shuffles,
        pooled over the folds of the first repeat).
    """
    n, p = X.shape
    k = 5 if n >= 25 else 3
    runs = []
    perm_drops = np.zeros((5, p))
    for r in range(repeats):
        rng = np.random.default_rng(seed + r)
        folds = _kfold(n, k, rng)
        oofs = [np.zeros(n), np.zeros(n)]
        fold_models = []
        for test_idx in folds:
            train_mask = np.ones(n, dtype=bool)
            train_mask[test_idx] = False
            models = _forests(seed + r)
            for oof, model in zip(oofs, models, strict=True):
                model.fit(X[train_mask], y[train_mask])
                oof[test_idx] = model.predict(X[test_idx])
            fold_models.append((test_idx, models[0]))
        scores = [r2_score(y, oof) for oof in oofs]
        runs.append(max(scores))
        if r == 0:
            # Pooled permutation importance: shuffle a column in every test fold,
            # recompute the pooled OOF R2, repeat 5 times.
            base = r2_score(y, oofs[0])
            for rep in range(5):
                rng_p = np.random.default_rng(seed + 1000 + rep)
                for j in range(p):
                    pred = np.zeros(n)
                    for test_idx, model in fold_models:
                        Xp = X[test_idx].copy()
                        Xp[:, j] = rng_p.permutation(Xp[:, j])
                        pred[test_idx] = model.predict(Xp)
                    perm_drops[rep, j] = base - r2_score(y, pred)
    return (
        float(np.mean(runs)),
        float(np.std(runs, ddof=1)) if len(runs) > 1 else 0.0,
        [round(v, 4) for v in runs],
        perm_drops.mean(axis=0),
        perm_drops.std(axis=0),
    )


def _interaction_strengths(model, X: np.ndarray, explainer_cls) -> tuple[np.ndarray, float]:
    """Pairwise mean |SHAP interaction| (symmetric, zero diagonal) and total attribution."""
    inter = np.abs(np.asarray(explainer_cls(model).shap_interaction_values(X))).mean(axis=0)
    total = float(inter.sum()) or 1.0
    pairs = inter + inter.T
    np.fill_diagonal(pairs, 0.0)
    return pairs, total


def shap_analysis(
    X: np.ndarray,
    y: np.ndarray,
    names: list[str],
    categorical: list[bool] | None = None,
    ceiling_r2: float | None = None,
    seed: int = 0,
    max_rows: int = 300,
    max_interaction_rows: int = 100,
    max_interaction_features: int = 10,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    """
    Gated SHAP view of a random forest fitted to the training rows.

    - importance: mean |SHAP| per feature (share of total attribution)
    - partial_effects: shape of each feature's SHAP dependence (its effect with the
      others accounted for). Features with a negligible share get no shape advice.
    - interactions: pairs whose interaction share exceeds the maximum share seen when
      the same forest is fitted to a permuted target (a null reference).
    When the noise ceiling shows no reliable signal, only importance is reported.

    Returns:
        (summary, sampled X rows, SHAP values for those rows)
    """
    import shap
    from sklearn.ensemble import RandomForestRegressor

    categorical = categorical or [False] * len(names)
    rng = np.random.default_rng(seed)

    def forest(target: np.ndarray, cols: np.ndarray):
        return RandomForestRegressor(
            n_estimators=60, max_depth=8, min_samples_leaf=3, n_jobs=1, random_state=seed
        ).fit(cols, target)

    model = forest(y, X)
    idx = rng.choice(len(y), size=min(max_rows, len(y)), replace=False)
    Xs = X[idx]
    values = np.asarray(shap.TreeExplainer(model).shap_values(Xs))

    mean_abs = np.abs(values).mean(axis=0)
    total = float(mean_abs.sum()) or 1.0
    share = mean_abs / total
    order = np.argsort(-mean_abs)
    importance = [
        {"feature": names[j], "mean_abs_shap": _g(mean_abs[j]), "share": round(float(share[j]), 3)}
        for j in order
    ]
    reliable = ceiling_r2 is None or ceiling_r2 >= RELIABLE_CEILING

    partial: dict[str, str] = {}
    interactions: list[dict[str, Any]] = []
    if reliable:
        y_sd = float(np.std(y)) or 1.0
        for j in order[:10]:
            if categorical[j]:
                partial[names[j]] = "categorical code: compare levels, do not fit a curve"
            elif share[j] < NEGLIGIBLE_SHARE:
                partial[names[j]] = (
                    f"negligible effect (share {share[j]:.1%}); model only if fit diagnostics "
                    "flag it as a missing variable"
                )
            else:
                partial[names[j]] = profile_shape(Xs[:, j], values[:, j], ref_sd=y_sd)["shape"]

        top = [int(j) for j in order[:max_interaction_features] if share[j] >= NEGLIGIBLE_SHARE]
        if len(top) >= 2:
            fit_idx = rng.choice(len(y), size=min(2000, len(y)), replace=False)
            Xt = X[fit_idx][:, top]
            yt = y[fit_idx]
            rows = rng.choice(len(yt), size=min(max_interaction_rows, len(yt)), replace=False)
            # Compare absolute interaction strength with a forest fitted to a permuted
            # target (same data, no real structure): spurious tree interactions are
            # of that size.
            real, real_total = _interaction_strengths(forest(yt, Xt), Xt[rows], shap.TreeExplainer)
            null, _ = _interaction_strengths(
                forest(rng.permutation(yt), Xt), Xt[rows], shap.TreeExplainer
            )
            threshold = max(float(null.max()), 0.02 * real_total)
            for a in range(len(top)):
                for b in range(a + 1, len(top)):
                    if real[a, b] > threshold:
                        interactions.append(
                            {
                                "a": names[top[a]],
                                "b": names[top[b]],
                                "share_of_attribution": round(float(real[a, b] / real_total), 3),
                            }
                        )
            interactions.sort(key=lambda d: -d["share_of_attribution"])

    summary = {
        "reliable": reliable,
        "rows_used": len(idx),
        "importance": importance,
        "interactions": interactions[:8],
        "partial_effects": partial,
        "note": (
            "Random-forest SHAP. interactions = share of total attribution carried by a pair, "
            "kept only above a permuted-target null (try a product, ratio or multiplicative law). "
            "partial_effects = shape of each feature's effect with the others accounted for; "
            "'negligible' features should not be modelled."
            if reliable
            else "No reliable signal (noise ceiling below 0.1): SHAP effects are not interpretable."
        ),
    }
    return summary, Xs, values


def compute_profile(
    X: np.ndarray,
    y: np.ndarray,
    names: list[str],
    categorical: list[bool],
    seed: int = 0,
) -> dict[str, Any]:
    """
    Everything CPU-heavy about the training data, as plain arrays/dicts (picklable).
    """
    from sklearn.feature_selection import mutual_info_regression

    rng = np.random.default_rng(seed)
    if len(y) > MAX_CEILING_ROWS:
        sub = rng.choice(len(y), size=MAX_CEILING_ROWS, replace=False)
        Xc, yc = X[sub], y[sub]
    else:
        Xc, yc = X, y
    ceiling, ceiling_sd, runs, imp_mean, imp_sd = noise_ceiling(Xc, yc, seed=seed)
    mi = mutual_info_regression(Xc, yc, random_state=seed) if X.shape[1] else np.array([])

    shap_summary: dict[str, Any]
    sample = None
    try:
        summary, Xs, values = shap_analysis(
            Xc, yc, names, categorical=categorical, ceiling_r2=ceiling, seed=seed
        )
        shap_summary = {"available": True} | summary
        sample = (Xs, values)
    except ImportError:
        shap_summary = {"available": False, "reason": "shap is not installed"}
    except Exception as e:  # SHAP is an aid, never a reason to fail profiling
        shap_summary = {"available": False, "reason": str(e)}

    return {
        "ceiling_r2": ceiling,
        "ceiling_sd": ceiling_sd,
        "ceiling_runs": runs,
        "importance_mean": [float(v) for v in imp_mean],
        "importance_sd": [float(v) for v in imp_sd],
        "mutual_info": [float(v) for v in mi],
        "rows_used": len(yc),
        "shap": shap_summary,
        "shap_sample": sample,
    }


# ---------------------------------------------------------------------------
# Process pool (keeps the event loop responsive)
# ---------------------------------------------------------------------------

_executor: ProcessPoolExecutor | None = None


def _get_executor() -> ProcessPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ProcessPoolExecutor(
            max_workers=1, mp_context=multiprocessing.get_context("spawn")
        )
    return _executor


def _reset_executor() -> None:
    """Kill a stuck or broken profiling process so the next run gets a fresh one."""
    global _executor
    ex, _executor = _executor, None
    if ex is None:
        return
    for proc in list(getattr(ex, "_processes", {}).values()):
        with contextlib.suppress(Exception):
            proc.terminate()
    with contextlib.suppress(Exception):
        ex.shutdown(wait=False, cancel_futures=True)


async def compute_profile_async(
    X: np.ndarray,
    y: np.ndarray,
    names: list[str],
    categorical: list[bool],
    seed: int = 0,
    timeout_s: float = PROFILE_TIMEOUT_S,
) -> dict[str, Any]:
    """Run ``compute_profile`` in the profiling process with a wall-clock cap."""
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(_get_executor(), compute_profile, X, y, names, categorical, seed)
    try:
        return await asyncio.wait_for(future, timeout=timeout_s)
    except (asyncio.TimeoutError, BrokenProcessPool):
        _reset_executor()
        raise


def describe_features(
    X: dict[str, np.ndarray],
    y: np.ndarray,
    original_names: dict[str, str],
    importance: dict[str, tuple[float, float]],
    mutual_info: dict[str, float],
    kinds: dict[str, str],
) -> list[dict[str, Any]]:
    """Per-feature summary: range, sign, correlations, mutual information, importance."""
    out = []
    for name, x in X.items():
        const = np.ptp(x) == 0 or np.ptp(y) == 0
        imp = importance.get(name)
        out.append(
            {
                "alias": name,
                "column": original_names.get(name, name),
                "kind": kinds.get(name, "continuous"),
                "min": _g(x.min()),
                "max": _g(x.max()),
                "mean": _g(x.mean()),
                "all_positive": bool(np.all(x > 0)),
                "n_unique": len(np.unique(x)),
                "pearson_r": None if const else round(float(stats.pearsonr(x, y).statistic), 3),
                "spearman_rho": None if const else round(float(stats.spearmanr(x, y).statistic), 3),
                "mutual_info": round(float(mutual_info.get(name, 0.0)), 3),
                "permutation_importance": round(imp[0], 3) if imp else None,
                "permutation_importance_sd": round(imp[1], 3) if imp else None,
            }
        )
    return out


def collinear_pairs(X: dict[str, np.ndarray], threshold: float = 0.9) -> list[dict[str, Any]]:
    names = list(X)
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = X[names[i]], X[names[j]]
            if np.ptp(a) == 0 or np.ptp(b) == 0:
                continue
            r = float(stats.spearmanr(a, b).statistic)
            if abs(r) >= threshold:
                pairs.append({"a": names[i], "b": names[j], "spearman_rho": round(r, 3)})
    return pairs


def profile_shape(
    x: np.ndarray, y: np.ndarray, n_bins: int = 10, ref_sd: float | None = None
) -> dict[str, Any]:
    """
    Binned mean of the target along one feature and a coarse shape label.

    Labels: increasing/decreasing (linear, saturating, accelerating),
    peaked, valley, sigmoidal, flat — a hint for which families to try.

    With ``ref_sd`` (used for SHAP dependence, where ``y`` is an effect rather than
    the noisy target) the curve is flat when its span is below 5% of ``ref_sd`` and
    bin noise is taken from the within-bin spread.
    """
    if np.ptp(x) == 0:
        return {"shape": "constant feature", "bins": []}
    edges = np.unique(np.quantile(x, np.linspace(0, 1, n_bins + 1)))
    labels = np.clip(np.searchsorted(edges, x, side="right") - 1, 0, len(edges) - 2)
    bins = []
    for b in range(len(edges) - 1):
        m = labels == b
        if m.sum() == 0:
            continue
        bins.append(
            {
                "x_mid": _g(np.median(x[m])),
                "y_mean": _g(y[m].mean()),
                "y_sd": _g(y[m].std()),
                "n": int(m.sum()),
            }
        )
    means = np.array([b["y_mean"] for b in bins], dtype=float)
    mids = np.array([b["x_mid"] for b in bins], dtype=float)
    mean_n = max(np.mean([b["n"] for b in bins]), 1.0)

    dep = binned_dependence(y - y.mean(), x)
    if ref_sd is not None:
        within_sd = float(np.mean([b["y_sd"] or 0.0 for b in bins]))
        se = within_sd / np.sqrt(mean_n)
        if np.ptp(means) < 0.05 * ref_sd:
            shape = "flat (effect smaller than 5% of the target's spread)"
        else:
            shape = _classify(mids, means, se)
    else:
        # Standard error of a bin mean: differences smaller than a few SEs are noise.
        se = float(np.std(y)) / np.sqrt(mean_n)
        if dep is not None and dep[0] < 0.02:
            shape = "flat (bins explain <2% of the variance; no clear marginal effect)"
        else:
            shape = _classify(mids, means, se)
    return {
        "shape": shape,
        "variance_explained_by_bins": round(dep[0], 3) if dep else None,
        "spearman_rho": round(float(stats.spearmanr(x, y).statistic), 3),
        "bins": bins,
    }


def _classify(mids: np.ndarray, means: np.ndarray, se: float) -> str:
    """Shape label from binned means; ``se`` is the standard error of one bin mean."""
    k = len(means)
    if k < 4:
        return "too few distinct values to classify"
    span = means.max() - means.min()
    if span < 3 * se:
        return "flat (bin means differ by less than their noise)"
    i_max, i_min = int(np.argmax(means)), int(np.argmin(means))
    interior = range(1, k - 1)
    margin = max(0.2 * span, 3 * se)
    if i_max in interior and means[0] < means[i_max] - margin and means[-1] < means[i_max] - margin:
        return "peaked (optimum inside the range) — try gaussian_peak or quadratic"
    if i_min in interior and means[0] > means[i_min] + margin and means[-1] > means[i_min] + margin:
        return "valley (minimum inside the range) — try quadratic"
    rho = stats.spearmanr(mids, means).statistic
    direction = "increasing" if rho > 0 else "decreasing"
    if abs(rho) < 0.6:
        return "non-monotonic / noisy"
    d = np.diff(means) * (1 if rho > 0 else -1)
    third = max(1, len(d) // 3)
    first, middle, last = (
        d[:third].mean(),
        d[third:-third].mean() if len(d) > 2 * third else d.mean(),
        d[-third:].mean(),
    )
    if middle > 1.5 * max(first, last, 1e-12) and first < 0.5 * middle and last < 0.5 * middle:
        return f"sigmoidal {direction} — try logistic or gompertz"
    if last < 0.4 * first:
        return f"saturating {direction} — try mitscherlich, michaelis_menten, power, logarithmic, linear_plateau"
    if first < 0.4 * last:
        return f"accelerating {direction} — try exponential, power, quadratic"
    return f"roughly linear {direction}"


def _g(v: float) -> float:
    """Round to 4 significant digits for compact JSON."""
    v = float(v)
    if not np.isfinite(v) or v == 0:
        return v if np.isfinite(v) else None
    return float(f"{v:.4g}")
