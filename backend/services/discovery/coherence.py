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

from backend.services.discovery import literature_coherence
from backend.services.discovery.fitting import ModelResult
from backend.services.discovery.formula_space import (
    STATUS_TEXT,
    challenger_reading,
    statement_checks,
)
from backend.services.discovery.profiling import _shape_kind, profile_shape
from backend.services.discovery.relate import is_known
from backend.services.discovery.selection import Selection, disagrees
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
    "supplied_literature": "Coherence with the literature",
    "literature_relations": "The literature's relationships in the data",
    "web_statements": "Statements of the web literature research",
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


def _known_laws(
    h: ModelResult,
    rels: list[dict[str, Any]],
    fitted: dict[str, int] | None = None,
    headline_reason: str = "",
) -> list[dict[str, Any]]:
    """
    The headline against the published and the named laws, from ``relate.relations``. Known
    laws are fitted after the blind exploration, so a match is a rediscovery, not a start.
    ``fitted`` counts the laws of each kind that were fitted: relations only cover the ones
    better than the mean, so "none related" can still mean several were fitted.
    ``headline_reason`` tells why a known law is the headline: no discovered equation was
    usable, or none was coherent with the literature.
    """
    fitted = fitted or {}
    checks = []
    for key, (kind, noun, none_detail) in KNOWN_LAW_CHECKS.items():
        if is_known(h):
            # Only the headline's own kind is worth a caution; the other has nothing to add.
            if h.kind == kind:
                why = (
                    "no discovered equation is coherent with the literature"
                    if headline_reason == "coherent_literature_law"
                    else "no discovered equation was usable"
                )
                detail = f"{why}; the headline is the {noun} {h.label}"
                checks.append(_check(key, "warn", detail))
            else:
                checks.append(_check(key, "na", "the headline is a known law"))
            continue
        of_kind = [r for r in rels if r["kind"] == kind]
        if not of_kind:
            n = fitted.get(kind, 0)
            detail = (
                f"{n} {noun}{'s' if n != 1 else ''} fitted, none better than the mean, so none "
                "is compared with the headline"
                if n
                else none_detail
            )
            checks.append(_check(key, "na", detail))
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


def _reading_text(statements: list[dict[str, Any]] | None) -> str:
    """What the data says about the statements the better-fitting expression breaks."""
    reading = challenger_reading(statements or [])
    if reading == "paradigm_shift":
        parts = []
        for s in statements or []:
            if s["used_by_challenger"] and s["data"] == "contradicts":
                text = (
                    f"{s['variable']} explains {s['residual_share']:.0%} of what the "
                    "recommendation leaves unexplained"
                )
                if s.get("conditions"):
                    text += f" (the literature states it for: {s['conditions']})"
                parts.append(text)
        return (
            ". The data speaks against the literature here, so this may be a paradigm shift: "
            + "; ".join(parts[:3])
        )
    if reading == "wrong_relationship":
        return (
            ". The data does not speak against the statements it breaks, so this is more "
            "likely a wrong relationship"
        )
    return ""


def _web_statements(session: DiscoverySession, h: ModelResult) -> list[dict[str, Any]]:
    """
    The headline against the statements of the web literature research whose validity
    in the context of this data is unknown: they warn, and never decide the selection.
    """
    literature = literature_coherence.build(session)
    if literature is None or not any(not c.get("binding", True) for c in literature.constraints):
        return []
    open_conflicts = literature.conflicts(h, binding=False)
    if open_conflicts:
        return [
            _check(
                "web_statements",
                "warn",
                "the headline conflicts with statements of the web literature research that "
                "may not be valid in the context of this data: " + "; ".join(open_conflicts[:3]),
                len(open_conflicts),
            )
        ]
    return [
        _check(
            "web_statements",
            "pass",
            "the headline agrees with the statements of the web literature research whose "
            "validity in the context of this data is unknown",
            0,
        )
    ]


def _literature_relations(session: DiscoverySession, h: ModelResult) -> list[dict[str, Any]]:
    """
    The literature's relationships among the other variables, measured on the data
    (``formula_space.py``): do they hold in the context of this data? Also says when the
    headline uses variables together that a holding relationship already connects.
    """
    measured = [
        r for r in (session.known_laws or {}).get("relations") or [] if r.get("status") != "na"
    ]
    if not measured:
        return []
    holding = [r for r in measured if r["status"] in ("holds", "holds_in_form")]
    failing = [r for r in measured if r not in holding]

    def one(r: dict[str, Any]) -> str:
        scores = [v for v in (r.get("r2_published"), r.get("r2_refitted")) if v is not None]
        score = r["r2_published"] if r["status"] == "holds" else max(scores)
        text = f"{r['equation']} {STATUS_TEXT[r['status']]} (R2 {score:.2f})"
        if r in failing and r.get("conditions"):
            text += f", the literature states it for: {r['conditions']}"
        return text

    connected = []
    for r in holding:
        together = [v for v in r.get("variables") or [] if v in h.features]
        if r.get("variable") in h.features and together:
            connected.append(
                f"{r['variable']} together with {', '.join(together)}, which the literature "
                f"connects by {r['equation']}"
            )
    note = (
        ". The headline uses " + "; ".join(connected[:2]) + ": check that it does not count "
        "the same effect twice"
        if connected
        else ""
    )
    counts = f"{len(holding)} of {len(measured)}"
    if failing:
        return [
            _check(
                "literature_relations",
                "warn",
                f"{counts} relationships of the literature among the other variables hold in "
                "the data, a hint that the context of the data differs from the literature's: "
                + "; ".join(one(r) for r in failing[:3])
                + note,
                len(failing),
            )
        ]
    return [
        _check(
            "literature_relations",
            "pass",
            f"all {len(measured)} relationships of the literature among the other variables "
            "hold in the data: " + "; ".join(one(r) for r in holding[:3]) + note,
            0,
        )
    ]


def _supplied_literature(
    selection: Selection, statements: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """
    The headline against what the user's own literature states (coherence-first
    selection). Absent when no literature was supplied. ``statements`` are the data
    tests of the literature's statements (``formula_space.statement_checks``).
    """
    info = selection.coherence_first
    if not info:
        return []
    conflicts = info.get("headline_conflicts") or []
    if conflicts:
        return [
            _check(
                "supplied_literature",
                "fail",
                "the headline conflicts with the literature: " + "; ".join(conflicts[:3]),
                len(conflicts),
            )
        ]
    gap, challenger = info.get("gap_se"), info.get("challenger_model_id")
    if disagrees(info):
        lead = (
            "the headline is a law of the literature, because no discovered "
            "equation is coherent with it; "
            if info.get("status") == "coherent_reference"
            else "the headline is coherent with the literature, but "
        )
        return [
            _check(
                "supplied_literature",
                "warn",
                f"{lead}{challenger} fits better by {gap:.1f} standard errors and conflicts "
                "with it: "
                + "; ".join((info.get("challenger_conflicts") or [])[:3])
                + _reading_text(statements),
                gap,
            )
        ]
    counts = f"{info.get('n_coherent')} of {info.get('n_candidates')} candidates are"
    if info.get("status") == "coherent_reference":
        counts += ", none of them a discovered equation"
    return [
        _check(
            "supplied_literature",
            "pass",
            f"the headline is coherent with the literature ({counts})",
            gap,
        )
    ]


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


def _fitted_known_laws(session: DiscoverySession) -> dict[str, int]:
    """How many known laws of each kind were fitted (usable or not)."""
    counts: dict[str, int] = {}
    for m in session.ranked_models():
        if is_known(m):
            counts[m.kind] = counts.get(m.kind, 0) + 1
    return counts


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
    info = selection.coherence_first or {}
    statements = (
        statement_checks(session, h, session.models.get(info.get("challenger_model_id") or ""))
        if info and not info.get("headline_conflicts")
        else []
    )
    checks = [
        _fit_vs_ceiling(session, h),
        _generalization(session, h),
        _shap(shap_agreement),
        *_known_laws(h, headline_relations, _fitted_known_laws(session), selection.headline_reason),
        *_supplied_literature(selection, statements),
        *_web_statements(session, h),
        *_literature_relations(session, h),
        _parameters(h),
        _agent(h, agent),
    ]
    rated = [c["status"] for c in checks if c["status"] in STATUS_ORDER]
    return {
        "model_id": h.model_id,
        "overall": max(rated, key=STATUS_ORDER.get) if rated else "na",
        "checks": checks,
        "literature_statements": statements,
        "challenger_reading": challenger_reading(statements) if disagrees(info) else None,
        "effect_directions": effect_directions(session, h),
    }
