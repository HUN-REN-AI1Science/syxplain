"""
Coherence of the headline equation: do the independent lines of evidence agree on it?

Each check compares the headline with one source (the noise ceiling, the holdout,
SHAP, published laws, named laws, its own parameters, the agent) and gets a status
decided by fixed thresholds here, never by an LLM. ``effect_directions`` describes
how the equation moves with each of its features; the explanation LLM judges those
against domain knowledge.
"""

from typing import Any

import numpy as np

from backend.services.discovery.fitting import ModelResult
from backend.services.discovery.profiling import _shape_kind, profile_shape
from backend.services.discovery.selection import Selection, guard
from backend.services.discovery.session import DiscoverySession

CEILING_PASS = 0.9  # headline CV R2 / noise ceiling
CEILING_WARN = 0.7
GAP_PASS = 0.05  # CV R2 - holdout R2
GAP_WARN = 0.15
DIRECTION_GRID = 40
DIRECTION_BACKGROUND = 100

STATUS_ORDER = {"pass": 0, "warn": 1, "fail": 2}

LABELS = {
    "fit_vs_ceiling": "Fit vs. noise ceiling",
    "generalization": "Held-out generalization",
    "shap": "Agreement with SHAP effects",
    "literature": "Published laws",
    "named_laws": "Named laws",
    "parameters": "Parameters and domain of definition",
    "agent": "Agent's own conclusion",
}


def _check(key: str, status: str, detail: str, value: Any = None) -> dict[str, Any]:
    return {"key": key, "label": LABELS[key], "status": status, "value": value, "detail": detail}


def _best_usable(models: list[ModelResult]) -> ModelResult | None:
    usable = [m for m in models if guard(m, strict=False) is None]
    return min(usable, key=lambda m: m.cv_rmse, default=None)


def _fit_vs_ceiling(session: DiscoverySession, h: ModelResult) -> dict[str, Any]:
    ceiling = session.ceiling_r2
    if session.fit_data.has_signal is False:
        return _check(
            "fit_vs_ceiling",
            "fail",
            f"no detectable relationship: a flexible model reaches only R2 {ceiling:.2f}",
        )
    if ceiling is None or ceiling <= 0 or h.cv_r2 is None:
        return _check("fit_vs_ceiling", "na", "no noise ceiling estimate")
    ratio = h.cv_r2 / ceiling
    status = "pass" if ratio >= CEILING_PASS else "warn" if ratio >= CEILING_WARN else "fail"
    return _check(
        "fit_vs_ceiling",
        status,
        f"CV R2 {h.cv_r2:.3f} is {ratio:.0%} of the noise ceiling {ceiling:.3f}",
        round(ratio, 3),
    )


def _generalization(session: DiscoverySession, h: ModelResult) -> dict[str, Any]:
    if not session.has_holdout or h.cv_r2 is None or h.parsed is None:
        return _check("generalization", "na", "no holdout (the dataset is cross-validated only)")
    if not h.holdout:
        # score_holdout gives up when the equation is undefined on most held-out rows
        return _check("generalization", "fail", "undefined on more than half of the held-out rows")
    gap = h.cv_r2 - h.holdout["r2"]
    status = "pass" if gap <= GAP_PASS else "warn" if gap <= GAP_WARN else "fail"
    return _check(
        "generalization",
        status,
        f"holdout R2 {h.holdout['r2']:.3f} vs CV R2 {h.cv_r2:.3f} "
        f"on {len(session.holdout)} unseen rows",
        round(gap, 3),
    )


def _shap(agreement: list[dict[str, Any]]) -> dict[str, Any]:
    judged = [a for a in agreement if a.get("verdict") != "undetermined"]
    if not judged:
        return _check("shap", "na", "no reliable SHAP effects to compare")
    misses = [a for a in judged if a["verdict"] != "agrees"]
    status = (
        "fail" if any(a["verdict"] == "opposite" for a in misses) else "warn" if misses else "pass"
    )
    agree_share = sum(a["shap_share"] for a in judged if a["verdict"] == "agrees")
    total_share = sum(a["shap_share"] for a in judged)
    parts = [f"{a['feature']} {a['verdict']}" for a in misses]
    detail = (
        f"the equation follows the data's effect for {len(judged) - len(misses)} of "
        f"{len(judged)} important features" + (f"; {', '.join(parts)}" if parts else "")
    )
    return _check("shap", status, detail, round(agree_share / total_share, 3))


def _literature(session: DiscoverySession, h: ModelResult, selection: Selection) -> dict[str, Any]:
    known = session.known_laws or {}
    ids = [law.get("model_id") for law in known.get("laws", []) if law.get("model_id")]
    if known.get("status") != "ok" or not ids:
        return _check("literature", "na", "no published law was found or fitted")
    if h.kind == "literature":
        return _check("literature", "pass", f"the headline is a published law ({h.label})")
    laws = [session.models[i] for i in ids if i in session.models]
    best = _best_usable(laws)
    if best is None:
        return _check(
            "literature",
            "warn",
            f"none of the {len(laws)} published laws fits these data better than the mean",
        )
    if selection.is_tied(best):
        shared = sorted(set(best.features) & set(h.features))
        return _check(
            "literature",
            "pass",
            f"published law {best.model_id} ({best.label}) fits as well "
            f"(CV R2 {best.cv_r2:.3f} vs {h.cv_r2:.3f}); shared variables: "
            + (", ".join(shared) or "none"),
            best.model_id,
        )
    return _check(
        "literature",
        "warn",
        f"the headline beats the best published law {best.model_id} (CV R2 {best.cv_r2:.3f} "
        f"vs {h.cv_r2:.3f}): a new relationship that needs checking",
        best.model_id,
    )


def _named_laws(h: ModelResult, ranked: list[ModelResult], selection: Selection) -> dict[str, Any]:
    if h.kind == "classic":
        return _check("named_laws", "pass", f"the headline is a named law ({h.label})")
    best = _best_usable([m for m in ranked if m.kind == "classic"])
    if best is None:
        return _check("named_laws", "na", "no named law fits better than the mean")
    if selection.is_tied(best):
        if best.complexity <= h.complexity:
            return _check(
                "named_laws",
                "warn",
                f"the simpler named law {best.model_id} ({best.label}) is statistically tied "
                f"(CV R2 {best.cv_r2:.3f} vs {h.cv_r2:.3f})",
                best.model_id,
            )
        return _check(
            "named_laws",
            "pass",
            f"the named law {best.model_id} ({best.label}) fits as well "
            f"(CV R2 {best.cv_r2:.3f} vs {h.cv_r2:.3f}) but is more complex",
            best.model_id,
        )
    return _check(
        "named_laws",
        "pass",
        f"improves on the best named law {best.model_id} ({best.label}) beyond noise "
        f"(CV R2 {best.cv_r2:.3f} → {h.cv_r2:.3f})",
        best.model_id,
    )


def _parameters(h: ModelResult) -> dict[str, Any]:
    undefined = h.n_undefined_total
    if undefined:
        return _check("parameters", "fail", f"undefined on {undefined} rows of the data", undefined)
    weak = h.diagnostics.get("weak_parameters", []) + h.diagnostics.get(
        "nonsignificant_parameters", []
    )
    if h.ill_conditioned or weak:
        return _check(
            "parameters",
            "warn",
            f"poorly determined parameters: {', '.join(weak)}" if weak else "near-singular fit",
        )
    return _check("parameters", "pass", "every parameter is determined by the data", h.n_params)


def _agent(h: ModelResult, agent: dict[str, Any]) -> dict[str, Any]:
    if agent.get("source") == "auto_fallback":
        # Its picks are the CV leaderboard, not an independent conclusion.
        return _check("agent", "na", "the agent did not finish its report")
    picks = [r.get("model_id") for r in agent.get("recommended_models") or []]
    failed = agent.get("claims_failed") or []
    if not picks and not failed:
        return _check("agent", "na", "the agent made no recommendation")
    if failed:
        return _check(
            "agent", "warn", f"{len(failed)} of the agent's claims did not hold when checked"
        )
    if h.model_id in picks:
        first = picks[0] == h.model_id
        return _check(
            "agent",
            "pass",
            "the agent's first pick is the headline"
            if first
            else "the agent recommended the headline",
        )
    return _check(
        "agent",
        "warn",
        f"the agent preferred {', '.join(p for p in picks if p)}; the selection protocol "
        "chose another model",
    )


def effect_directions(session: DiscoverySession, h: ModelResult) -> list[dict[str, Any]]:
    """Shape of the equation's partial dependence on each continuous feature it uses."""
    if h.parsed is None:
        return []
    X = session.fit_data.X
    n = session.fit_data.n
    rng = np.random.default_rng(session.seed)
    bg = rng.choice(n, size=min(DIRECTION_BACKGROUND, n), replace=False)
    background = {g: X[g][bg] for g in h.features if g in X}
    y_sd = float(np.std(session.fit_data.y)) or 1.0
    out = []
    for f in h.features:
        if f not in X or session.kinds.get(f) == "categorical":
            continue
        # Evenly spaced over the central 95%, so the shape is the equation's, not the data's.
        lo, hi = np.quantile(X[f], [0.025, 0.975])
        if hi <= lo:
            continue
        grid = np.linspace(lo, hi, DIRECTION_GRID)
        pdp = session.partial_dependence(h, f, grid, background)
        ok = np.isfinite(pdp)
        if ok.sum() < 3:
            out.append(
                {
                    "feature": f,
                    "x_low": float(lo),
                    "x_high": float(hi),
                    "shape": "undefined over the data range",
                }
            )
            continue
        xs, ys = grid[ok], pdp[ok]
        out.append(
            {
                "feature": f,
                # the ends where the equation is defined, so each x matches its prediction
                "x_low": float(xs[0]),
                "x_high": float(xs[-1]),
                "shape": _shape_kind(profile_shape(xs, ys, ref_sd=y_sd)["shape"]),
                "prediction_at_low": float(ys[0]),
                "prediction_at_high": float(ys[-1]),
            }
        )
    return out


def coherence_report(
    session: DiscoverySession,
    selection: Selection,
    ranked: list[ModelResult],
    shap_agreement: list[dict[str, Any]],
    agent: dict[str, Any],
) -> dict[str, Any] | None:
    """All coherence checks of the headline, the worst one as the overall status."""
    h = selection.headline
    if h is None:
        return None
    checks = [
        _fit_vs_ceiling(session, h),
        _generalization(session, h),
        _shap(shap_agreement),
        _literature(session, h, selection),
        _named_laws(h, ranked, selection),
        _parameters(h),
        _agent(h, agent),
    ]
    rated = [c["status"] for c in checks if c["status"] in STATUS_ORDER]
    return {
        "model_id": h.model_id,
        "overall": max(rated, key=STATUS_ORDER.get) if rated else "na",
        "checks": checks,
        "effect_directions": effect_directions(session, h),
    }
