"""
Coherence of the headline equation: do the independent lines of evidence agree on it?

Each check compares the headline with one source (the noise ceiling, the holdout,
SHAP, published laws, named laws, its own parameters, the agent) and gets a status
decided by fixed thresholds here, never by an LLM. The known-law checks read the
relations computed after the blind exploration (``relate.py``). ``effect_directions`` describes
how the equation moves with each of its features; the explanation LLM judges those
against domain knowledge.
"""

from typing import Any

import numpy as np

from backend.services.discovery.fitting import ModelResult
from backend.services.discovery.profiling import _shape_kind, profile_shape
from backend.services.discovery.relate import is_known
from backend.services.discovery.selection import Selection
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


# Known-law checks: check key -> (relation kind, noun, detail when there is none)
KNOWN_LAW_CHECKS = {
    "literature": ("literature", "published law", "no published law was found or fitted"),
    "named_laws": ("classic", "named law", "no named law fits better than the mean"),
}


def _known_law_verdict(
    h: ModelResult, rels: list[dict[str, Any]], noun: str
) -> tuple[str, dict[str, Any], str]:
    """(status, law, detail) for the headline against one kind of known law."""

    def vs(r: dict[str, Any]) -> str:
        return f"CV R2 {r['cv_r2']:.3f} vs {h.cv_r2:.3f}"

    def name(r: dict[str, Any]) -> str:
        return f"{noun} {r['law_id']} ({r['label']})"

    better = [r for r in rels if r["comparison"] == "better"]
    if better:
        r = max(better, key=lambda r: r["cv_r2"])
        return (
            "warn",
            r,
            f"the {name(r)} fits better than the discovered headline beyond noise ({vs(r)})",
        )
    r = rels[0]  # closest relation first
    if r["relation"] == "equivalent":
        detail = (
            f"rediscovered: the headline is the {name(r)} in another form "
            f"(their predictions agree, R2 {r['agreement_r2']:.3f})"
        )
        return "pass", r, detail
    if r["relation"] == "similar":
        detail = f"the headline behaves like the {name(r)}: predictions agree with R2 {r['agreement_r2']:.3f}, {vs(r)}"
        return "pass", r, detail
    if r["relation"] == "partial":
        extra = ", ".join(sorted(set(h.features) - set(r["features"])))
        shared = ", ".join(r["shared_features"])
        return "pass", r, f"extends the {name(r)}: same shape along {shared}, plus {extra}"
    tied = sorted(
        (r for r in rels if r["comparison"] == "tied"),
        key=lambda r: r["complexity"] > h.complexity,
    )
    if tied and tied[0]["complexity"] <= h.complexity:
        r = tied[0]
        detail = (
            f"the simpler {name(r)} is statistically tied but predicts differently ({vs(r)}): "
            "the data cannot tell them apart"
        )
        return "warn", r, detail
    if tied:
        return (
            "pass",
            tied[0],
            f"fits as well as the {name(tied[0])} with a different form ({vs(tied[0])})",
        )
    r = max(rels, key=lambda r: r["cv_r2"])
    detail = (
        f"a new relationship: it beats all {len(rels)} {noun}s beyond noise and matches none "
        f"(best {r['law_id']}, {vs(r)})"
    )
    return "pass", r, detail


def _known_laws(h: ModelResult, rels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    The headline against the published and the named laws, from ``relate.relations``. Known
    laws are fitted after the blind exploration, so a match is a rediscovery, not a start.
    """
    checks = []
    for key, (kind, noun, none_detail) in KNOWN_LAW_CHECKS.items():
        if is_known(h):
            # Only the headline's own kind is worth a caution; the other has nothing to add.
            if h.kind == kind:
                detail = f"no discovered equation was usable; the headline is the {noun} {h.label}"
                checks.append(_check(key, "warn", detail))
            else:
                checks.append(_check(key, "na", "the headline is a known law"))
            continue
        of_kind = [r for r in rels if r["kind"] == kind]
        if not of_kind:
            checks.append(_check(key, "na", none_detail))
            continue
        status, r, detail = _known_law_verdict(h, of_kind, noun)
        checks.append(_check(key, status, detail, r["law_id"]))
    return checks


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
    shap_agreement: list[dict[str, Any]],
    agent: dict[str, Any],
    headline_relations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    All coherence checks of the headline, the worst one as the overall status.
    ``headline_relations`` are the headline's relations to every known law (``relate.py``).
    """
    h = selection.headline
    if h is None:
        return None
    checks = [
        _fit_vs_ceiling(session, h),
        _generalization(session, h),
        _shap(shap_agreement),
        *_known_laws(h, headline_relations),
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
