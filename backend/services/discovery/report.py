"""
Turn a finished discovery session into stored results (the "discovery brief").

Produces ``equations`` / ``scatter_data`` / ``best_equation`` for the results UI,
``results["discovery"]`` with the leaderboard, notebook, searches, selection and
agent report, the DATA_SPEC handed to the explanation LLM, and the join that merges
the LLM's narration back onto the backend's equations by ``model_id``.

Every number shown anywhere comes from here, never from an LLM.
"""

import logging
import math
import re
from typing import Any

from backend.services.discovery.coherence import coherence_report
from backend.services.discovery.fitting import ModelResult
from backend.services.discovery.relate import KNOWN_KINDS, is_known, relations
from backend.services.discovery.selection import Selection, select, select_dynamic, usable
from backend.services.discovery.session import MODEL_ID_RE, DiscoverySession

logger = logging.getLogger(__name__)

MAX_UI_EQUATIONS = 12
MAX_SYMBOLIC = 8
MAX_LEADERBOARD = 25
MAX_RELATIONS = 3  # known laws stored per discovered equation
MAX_HEADLINE_RELATIONS = 8
MAX_DYNAMIC = 6  # rate-law cards
MAX_TRACED = 3  # rate laws whose simulated trajectories are stored

# Fields the backend owns on every equation card (overwrite whatever the LLM wrote).
EQUATION_FIELDS = (
    "equation",
    "complexity",
    "loss",
    "score",
    "sympy_format",
    "origin",
    "model_id",
    "source",
    "metric_basis",
    "holdout_r2",
    "holdout_n",
    "cv_r2",
    "cv_se",
    "n_params",
    "target_transform",
    "verdict",
    "reasons",
    "n_undefined",
    "variables",
    "target_alias",
    "is_headline",
    "agent_recommended",
    "agent_why",
    "scatter_data",
)


def _loss(m: ModelResult) -> float | None:
    if m.holdout:
        return m.holdout["rmse"] ** 2
    return m.cv_rmse**2 if m.cv_rmse is not None else None


def _score(m: ModelResult) -> float | None:
    return m.holdout["r2"] if m.holdout else m.cv_r2


def _origin(m: ModelResult) -> str:
    if m.kind == "symbolic":
        return "symbolic"
    prefix = {"classic": "classic", "literature": "literature"}.get(m.kind, "custom")
    return f"{prefix}: {m.label}"


def _equation_entry(
    session: DiscoverySession,
    m: ModelResult,
    selection: Selection,
    agent_why: dict[str, str],
) -> dict[str, Any]:
    return {
        "equation": m.fitted_expression,
        "complexity": m.complexity,
        "loss": _loss(m),
        "score": _score(m),
        "sympy_format": m.fitted_expression,
        "origin": _origin(m),
        "model_id": m.model_id,
        "source": m.source,
        "metric_basis": session.metric_basis,
        "holdout_r2": m.holdout["r2"] if m.holdout else None,
        "holdout_n": len(session.holdout),
        "cv_r2": m.cv_r2,
        "cv_se": m.cv_se,
        "n_params": m.n_params,
        "target_transform": m.target_transform,
        "verdict": m.verdict,
        "reasons": m.reasons[:3],
        "n_undefined": m.n_undefined_total,
        "variables": session.variables_for(m.features),
        "target_alias": session.target_alias,
        "is_headline": selection.headline is m,
        "agent_recommended": m.model_id in agent_why,
        "agent_why": agent_why.get(m.model_id),
        "scatter_data": session.scatter(m),
    }


def _leaderboard_entry(
    session: DiscoverySession, m: ModelResult, selection: Selection, agent_why: dict[str, str]
) -> dict[str, Any]:
    return {
        "model_id": m.model_id,
        "kind": m.kind,
        "name": m.name,
        "label": m.label,
        "features": m.features,
        "equation": m.fitted_expression,
        "target_transform": m.target_transform,
        "complexity": m.complexity,
        "n_params": m.n_params,
        "metric_basis": session.metric_basis,
        "cv_r2": m.cv_r2,
        "cv_se": m.cv_se,
        "holdout_r2": m.holdout["r2"] if m.holdout else None,
        "holdout_rmse": m.holdout["rmse"] if m.holdout else None,
        "holdout_n": len(session.holdout),
        "aic": m.aic,
        "verdict": m.verdict,
        "reasons": m.reasons,
        "n_undefined": m.n_undefined,
        "source": m.source,
        "is_headline": selection.headline is m,
        "agent_recommended": m.model_id in agent_why,
    }


def select_equations(
    session: DiscoverySession,
    selection: Selection,
    recommended_ids: list[str],
    ranked: list[ModelResult],
) -> list[ModelResult]:
    """
    Cards for the results page: the shortlist (headline first), the symbolic Pareto
    front, agent picks and, as references, the best classic and literature laws — only
    models that pass the relaxed guard (usable and better than the mean).
    """
    pool = usable(ranked)
    chosen: dict[str, ModelResult] = {m.model_id: m for m in selection.shortlist}
    symbolic = session.pareto([m for m in pool if m.kind == "symbolic"])
    if len(symbolic) > MAX_SYMBOLIC:
        # keep the simplest and the most accurate ends of the front
        symbolic = symbolic[: MAX_SYMBOLIC // 2] + symbolic[-(MAX_SYMBOLIC - MAX_SYMBOLIC // 2) :]
    for m in symbolic:
        chosen.setdefault(m.model_id, m)
    by_id = {m.model_id: m for m in pool}
    for mid in recommended_ids:
        if mid in by_id:
            chosen.setdefault(mid, by_id[mid])
    for kind, n in (("classic", 2), ("custom", 1), ("literature", 2)):
        for m in [m for m in pool if m.kind == kind][:n]:
            chosen.setdefault(m.model_id, m)
    picked = list(chosen.values())[:MAX_UI_EQUATIONS]
    return sorted(picked, key=lambda m: (m.complexity, m.cv_rmse or 0.0))


def build_results(
    session: DiscoverySession,
    agent_report: dict[str, Any] | None,
    agent_error: str | None,
) -> dict[str, Any]:
    """Score once on the holdout, select, and assemble the stored results."""
    session.final_scoring()
    report = agent_report or {}
    agent_why = {
        r["model_id"]: r.get("why", "")
        for r in report.get("recommended_models", [])
        if r.get("model_id")
    }
    # By the registry, not the ranking: a failed or superseded rate law is still a rate law.
    dynamic_ids = {
        mid for mid in agent_why if getattr(session.models.get(mid), "problem", "") == "dynamic"
    }
    recommended = [mid for mid in agent_why if mid not in dynamic_ids]
    ranked = session.ranked_models()
    selection = select(ranked, recommended, reference=is_known)

    models = select_equations(session, selection, recommended, ranked)
    equations = [_equation_entry(session, m, selection, agent_why) for m in models]
    scatter_data = {e["equation"]: e["scatter_data"] for e in equations if e["scatter_data"]}
    best_equation = next((e for e in equations if e["is_headline"]), None)

    failed = [
        m for m in session.snapshot() if m.error and m.kind != "symbolic" and m.problem == "static"
    ]
    profile = session._profile or {}
    shap_agreement = session.shap_agreement(selection.headline)
    discovery = {
        "target": {"alias": session.target_alias, "column": session.target_column},
        "aliases": {a: c for a, c in session.column_of.items() if a != session.target_alias},
        "variable_kinds": session.kinds,
        "split": session.split_info(),
        "series": session.series,
        "noise_ceiling_r2": session.ceiling_r2,
        "noise_ceiling_sd": session.fit_data.ceiling_sd,
        "has_signal": session.fit_data.has_signal,
        "feature_profile": profile.get("features", []),
        "shap": profile.get("shap"),
        "shap_agreement": shap_agreement,
        "shap_plots": [{k: p[k] for k in ("name", "title")} for p in session.shap_plots],
        "selection": selection.to_dict(),
        "n_models_total": len(ranked),
        "leaderboard": [
            _leaderboard_entry(session, m, selection, agent_why) for m in ranked[:MAX_LEADERBOARD]
        ],
        "failed_fits": [
            {"model_id": m.model_id, "label": m.label, "features": m.features, "reason": m.error}
            for m in failed[:20]
        ],
        "notebook": session.notebook,
        "searches": [s.summary(session.models) for s in session.searches.values()],
        "budget": session.budget_status(),
        "agent": {
            "summary": report.get("summary", ""),
            "recommended_models": report.get("recommended_models", []),
            "rejected_forms": report.get("rejected_forms", []),
            "insights": report.get("insights", []),
            "open_questions": report.get("open_questions", []),
            "steps": report.get("steps"),
            "source": report.get("source", "agent" if agent_report else "none"),
            "stale": report.get("stale", False),
            "late_searches": report.get("late_searches", []),
            "review_steps": report.get("review_steps", 0),
            "claims_failed": report.get("claims_failed", []),
            "reviewed_searches": report.get("reviewed_searches", []),
            "error": agent_error,
        },
        "activity": session.events[-200:],
    }
    if session.known_laws is not None:
        discovery["literature"] = session.known_laws
    try:
        discovery["dynamics"] = build_dynamics(
            session, [mid for mid in agent_why if mid in dynamic_ids], agent_why
        )
    except Exception as e:  # rate laws are an addition; never sink the static results
        logger.warning(f"Dynamics results failed: {e}", exc_info=True)
        discovery["dynamics"] = None
    try:
        related = relations(session, selection, ranked)
    except Exception as e:  # a display-only comparison must never sink the results
        logger.warning(f"Relating to known laws failed: {e}")
        related = None
    h = selection.headline
    headline_relations = related.get(h.model_id, []) if related and h else []
    known_pool = [m for m in usable(ranked) if is_known(m)]
    discovery["relations"] = (
        {
            "n_known_laws": {
                kind: sum(1 for m in known_pool if m.kind == kind) for kind in KNOWN_KINDS
            },
            "headline": headline_relations[:MAX_HEADLINE_RELATIONS],
            "by_model": {mid: rels[:MAX_RELATIONS] for mid, rels in related.items()},
        }
        if related is not None
        else None
    )
    try:
        discovery["coherence"] = coherence_report(
            session, selection, shap_agreement, report, headline_relations
        )
    except Exception as e:  # a display-only check must never sink the results
        logger.warning(f"Coherence report failed: {e}")
        discovery["coherence"] = None
    return json_safe(
        {
            "equations": equations,
            "scatter_data": scatter_data,
            "best_equation": best_equation,
            "discovery": discovery,
        }
    )


def _dynamic_entry(
    session: DiscoverySession,
    m: ModelResult,
    selection: Selection,
    agent_why: dict[str, str],
    traces: bool,
) -> dict[str, Any]:
    """A rate-law card; integrating it on the holdout sets ``m.holdout`` (once, here)."""
    # A law that diverged on the training trajectories is not integrated again on the holdout.
    held = bool(session.dynamics.holdout_episodes) and not m.simulation.get("n_diverged")
    sim = (
        session.simulate_model(m, holdout=held, traces=traces)
        if (held or traces) and m.parsed is not None
        else None
    )
    if held and sim:
        m.holdout = {k: v for k, v in sim.items() if k != "traces"}
    return {
        "model_id": m.model_id,
        "label": m.label,
        "source": m.source,
        "equation": m.fitted_expression,
        "dydt_cv_r2": m.cv_r2,
        "simulation_train_r2": m.simulation.get("r2"),
        "simulation_diverged": m.simulation.get("n_diverged"),
        "holdout_r2": m.holdout["r2"] if m.holdout else None,
        "verdict": m.verdict,
        "reasons": m.reasons[:4],
        "not_recommended": selection.vetoes.get(m.model_id),
        "is_headline": selection.headline is m,
        "agent_recommended": m.model_id in agent_why,
        "agent_why": agent_why.get(m.model_id),
        "traces": (sim or {}).get("traces"),
        "traces_basis": "holdout" if held else "train",
    }


def _simulation_r2(m: ModelResult) -> float:
    r2 = m.simulation.get("r2")
    return -math.inf if r2 is None else r2


def build_dynamics(
    session: DiscoverySession, recommended_ids: list[str], agent_why: dict[str, str]
) -> dict[str, Any] | None:
    """Rate-law results: the confirmed structure, the headline law and simulated traces."""
    dyn = session.dynamics
    if dyn is None:
        return None
    ranked = session.ranked_models("dynamic")
    selection = select_dynamic(ranked, recommended_ids)
    pool = [m for m in ranked if m.model_id not in selection.vetoes]
    chosen: dict[str, ModelResult] = {m.model_id: m for m in selection.shortlist}
    # Vetoed laws still get cards (with the reason), best simulation first, so a run
    # whose rate laws all failed shows what was tried and how far off it was.
    vetoed = sorted(
        (m for m in ranked if m.model_id in selection.vetoes), key=_simulation_r2, reverse=True
    )
    for m in [
        *(m for m in pool if m.model_id in recommended_ids),
        *session.pareto(pool),
        *vetoed,
    ]:
        if len(chosen) >= MAX_DYNAMIC:
            break
        chosen.setdefault(m.model_id, m)
    cards = [
        _dynamic_entry(session, m, selection, agent_why, traces=i < MAX_TRACED)
        for i, m in enumerate(chosen.values())
    ]
    return {
        **dyn.summary(),
        "selection": selection.to_dict(),
        "n_models": len(ranked),
        "equations": cards,
    }


def json_safe(value: Any) -> Any:
    """Replace NaN/inf (rejected by Postgres JSONB) with None and numpy scalars with floats."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, bool) or value is None or isinstance(value, str | int):
        return value
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f if math.isfinite(f) else None


# ---------------------------------------------------------------------------
# Hand-off to the explanation LLM and back
# ---------------------------------------------------------------------------


def explanation_data_spec(results: dict[str, Any]) -> dict[str, Any]:
    """DATA_SPEC for the explanation LLM: the discovery brief, keyed by model_id."""
    equations = results["equations"]
    discovery = results["discovery"]
    agent = discovery.get("agent") or {}
    selection = discovery.get("selection") or {}
    headline_id = selection.get("headline_model_id")
    headline_position = next(
        (i + 1 for i, e in enumerate(equations) if e["model_id"] == headline_id), None
    )
    classic = [
        {
            "model_id": e["model_id"],
            "model": e["label"],
            "equation": e["equation"],
            "cv_r2": e["cv_r2"],
            "holdout_r2": e["holdout_r2"],
            "verdict": e["verdict"],
            "reasons": e["reasons"][:4],
        }
        for e in discovery["leaderboard"]
        if e["kind"] == "classic"
    ][:8]
    literature = discovery.get("literature") or {}
    related = discovery.get("relations") or {}
    dynamics = discovery.get("dynamics")
    rate_keys = (
        "model_id",
        "source",
        "dydt_cv_r2",
        "simulation_train_r2",
        "holdout_r2",
        "verdict",
        "reasons",
        "not_recommended",
        "agent_recommended",
    )

    def rate_law(e: dict[str, Any]) -> dict[str, Any]:
        return {"equation": f"{dynamics['rate']} = {e['equation']}"} | {
            k: e.get(k) for k in rate_keys
        }

    relation_keys = (
        "law_id",
        "kind",
        "label",
        "equation",
        "relation",
        "comparison",
        "agreement_r2",
        "shared_features",
        "cv_r2",
    )
    return {
        "equations": [
            {
                "position": i + 1,
                "model_id": e["model_id"],
                "equation": e["equation"],
                "origin": e["origin"],
                "complexity": e["complexity"],
                "n_params": e["n_params"],
                "loss": e["loss"],
                "cv_r2": e["cv_r2"],
                "holdout_r2": e["holdout_r2"],
                "target_transform": e["target_transform"],
                "verdict": e["verdict"],
                "reasons": e["reasons"],
                "source": e["source"],
                "n_undefined": e["n_undefined"],
                "is_headline": e["is_headline"],
                "agent_recommended": e["agent_recommended"],
                "agent_why": e["agent_why"],
            }
            for i, e in enumerate(equations)
        ],
        "split": discovery["split"],
        "series": discovery.get("series")
        and {
            "lag_features": discovery["series"]["lag_features"],
            "residual_autocorrelation": discovery["series"]["screening"][
                "residual_autocorrelation"
            ],
        },
        "variable_aliases": discovery["aliases"]
        | {discovery["target"]["alias"]: discovery["target"]["column"]},
        "variable_kinds": discovery.get("variable_kinds", {}),
        "selection": selection | {"headline_position": headline_position},
        "discovery": {
            "noise_ceiling_r2": discovery["noise_ceiling_r2"],
            "has_signal": discovery.get("has_signal"),
            "shap": {
                k: (discovery.get("shap") or {}).get(k)
                for k in ("reliable", "importance", "interactions", "partial_effects")
            },
            "headline_vs_shap": discovery.get("shap_agreement", []),
            "coherence": discovery.get("coherence"),
            "classic_baselines": classic,
            "relations_to_known_laws": {
                "headline": [
                    {k: r.get(k) for k in relation_keys} for r in related.get("headline", [])[:5]
                ],
                "others": {
                    mid: [
                        {k: r.get(k) for k in ("law_id", "relation", "agreement_r2")} for r in rels
                    ]
                    for mid, rels in (related.get("by_model") or {}).items()
                    if mid != headline_id
                },
            },
            "notebook": [
                {k: n.get(k) for k in ("kind", "text", "evidence", "model_ids")}
                for n in discovery["notebook"]
            ],
            "agent_summary": agent.get("summary", ""),
            "agent_recommended_models": agent.get("recommended_models", []),
            "rejected_forms": agent.get("rejected_forms", []),
            "insights": agent.get("insights", []),
            "open_questions": agent.get("open_questions", []),
            "agent_stale": agent.get("stale", False),
            "late_searches": agent.get("late_searches", []),
            "dynamics": (
                {
                    "split": dynamics["split"],
                    "headline": next(
                        (rate_law(e) for e in dynamics["equations"] if e["is_headline"]), None
                    ),
                    "rate_laws": [rate_law(e) for e in dynamics["equations"]],
                }
                if dynamics
                else None
            ),
            "literature_matches": [
                {k: law.get(k) for k in ("equation", "model_id", "cv_r2", "citations")}
                for law in literature.get("laws", [])
                if law.get("model_id")
            ],
        },
    }


def _normalize(eq: str) -> str:
    text = re.sub(r"\s+", "", str(eq)).replace("**", "^")
    text = re.sub(r"\((-?[\d.]+(?:e-?\d+)?)\)", r"\1", text)  # (-62.03) -> -62.03
    return text.replace("+-", "-").replace("-+", "-").replace("--", "+")


def merge_explanations(
    explanations: dict[str, Any], equations: list[dict[str, Any]]
) -> tuple[dict[str, Any], int]:
    """
    Join the LLM's cards to the backend equations: by echoed model_id, then by
    position (when the counts match), then by normalised equation string. Backend
    fields overwrite the card; unmatched backend equations become cards without
    narration. Returns (explanations, number of cards matched).
    """
    if not isinstance(explanations, dict) or not isinstance(explanations.get("equations"), list):
        return explanations, 0
    cards = [c for c in explanations["equations"] if isinstance(c, dict)]
    # New ids skip every id the LLM used, so a stale reference cannot hit a new card.
    next_id = max([c.get("id", 0) for c in cards if isinstance(c.get("id"), int)] + [0]) + 1
    by_id = {e["model_id"]: e for e in equations}
    by_norm = {_normalize(e["equation"]): e for e in equations}
    used: set[str] = set()
    kept: list[dict[str, Any]] = []
    same_count = len(cards) == len(equations)
    for i, card in enumerate(cards):
        model_id = card.get("model_id")
        src = by_id.get(model_id) if isinstance(model_id, str) else None
        if src is None and same_count and equations[i]["model_id"] not in used:
            src = equations[i]
        if src is None:
            src = by_norm.get(_normalize(card.get("equation", "")))
        # A card that matches no backend equation (or repeats one) carries only
        # LLM-made numbers, so it is dropped.
        if src is None or src["model_id"] in used:
            continue
        used.add(src["model_id"])
        for key in EQUATION_FIELDS:
            card[key] = src.get(key)
        kept.append(card)
    cards = kept
    matched = len(kept)
    for e in equations:
        if e["model_id"] in used:
            continue
        card = {"id": next_id, "overview": "", "term_explanations": []}
        card.update({k: e.get(k) for k in EQUATION_FIELDS})
        cards.append(card)
        next_id += 1
    explanations["equations"] = cards

    rec = explanations.get("recommendation")
    headline = next((c for c in cards if c.get("is_headline")), None)
    if headline is not None:
        if not isinstance(rec, dict):
            rec = explanations["recommendation"] = {"rationale": []}
        rec_card = next((c for c in cards if c.get("id") == rec.get("equation_id")), None)
        if rec_card is None:
            rec["equation_id"] = headline["id"]
            rec_card = headline
        rec.setdefault("agrees_with_headline", rec_card is headline)
    return explanations, matched


def cited_ids(text: str) -> list[str]:
    return MODEL_ID_RE.findall(str(text or ""))
