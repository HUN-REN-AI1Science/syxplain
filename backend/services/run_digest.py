"""
Compact views of a run for API clients and chat models.

The stored results of a run are large (scatter data, the agent's full activity log,
every fitted model). The digest keeps what a reader needs to judge the outcome: the
headline equation and its shortlist with their scores, how the data was split, what
the series feature stage added, how the result relates to known laws, the
explanation, the warnings and the LLM cost.
"""

from typing import Any

from backend.core.constants import RunStatus
from backend.services.progress_service import get_progress_phases

MAX_DIGEST_EQUATIONS = 10
MAX_DIGEST_LAWS = 8
MAX_DIGEST_RELATIONS = 5

_EQUATION_FIELDS = (
    "model_id",
    "equation",
    "origin",
    "complexity",
    "n_params",
    "target_transform",
    "metric_basis",
    "holdout_r2",
    "holdout_n",
    "cv_r2",
    "cv_rmse",
    "verdict",
    "reasons",
    "variables",
    "is_headline",
    "agent_recommended",
    "agent_why",
    "literature_conflicts",
)
_SPLIT_FIELDS = (
    "uploaded",
    "complete_rows",
    "dropped_incomplete",
    "train",
    "holdout",
    "has_holdout",
    "order",
    "metric_basis",
    "scored_on",
    "excluded_columns",
    "holdout_extrapolates",
)
_SERIES_FIELDS = (
    "time_column",
    "group_column",
    "n_series",
    "time_step",
    "padded_rows",
    "rows_without_history",
    "residual_autocorrelation",
)
_LAG_FIELDS = ("feature", "description", "reason", "padded_rows")
_AGENT_FIELDS = ("summary", "insights", "open_questions", "rejected_forms", "source", "error")
_LAW_FIELDS = (
    "equation",
    "citations",
    "citation_titles",
    "cv_r2",
    "unmapped",
    "fit_error",
    "origin",
    "composed_from",
)


def _pick(source: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    """The listed keys of a dict that are present and not None."""
    if not isinstance(source, dict):
        return {}
    return {k: source[k] for k in fields if source.get(k) is not None}


def phase_for(status: str, progress: int | None) -> dict[str, str] | None:
    """
    The pipeline phase a pending or running run is in, from its progress percentage
    (the phases and where each begins come from progress_config.yaml).
    """
    if status not in (RunStatus.PENDING, RunStatus.RUNNING):
        return None
    if status == RunStatus.PENDING:
        return {"name": "queued", "label": "Queued", "description": "Waiting to start."}
    current = None
    for phase in get_progress_phases():
        if (progress or 0) >= phase.get("progress_start", 0):
            current = phase
    if current is None:
        return None
    return {
        "name": current["name"],
        "label": current.get("label", current["name"]),
        "description": current.get("description", ""),
    }


def run_warnings(results: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Warnings of a run (a skipped literature step, an agent error, a failed explanation)."""
    warnings = (results or {}).get("warnings")
    return [w for w in warnings if isinstance(w, dict)] if isinstance(warnings, list) else []


def _series_digest(series: Any) -> dict[str, Any] | None:
    if not isinstance(series, dict):
        return None
    out = _pick(series, _SERIES_FIELDS)
    out["derived_features"] = [
        _pick(f, _LAG_FIELDS) for f in series.get("lag_features") or [] if isinstance(f, dict)
    ]
    stage = series.get("feature_stage")
    if isinstance(stage, dict):
        out["feature_stage"] = _pick(stage, ("status", "rationale", "error"))
    return out


def _literature_digest(literature: Any) -> dict[str, Any] | None:
    if not isinstance(literature, dict):
        return None
    laws = [law for law in literature.get("laws") or [] if isinstance(law, dict)]
    constraints = [c for c in literature.get("constraints") or [] if isinstance(c, dict)]
    out = _pick(literature, ("status", "error", "source")) | {
        "n_laws": len(laws),
        "laws": [_pick(law, _LAW_FIELDS) for law in laws[:MAX_DIGEST_LAWS]],
    }
    if constraints:
        out["constraints"] = [
            _pick(c, ("id", "type", "text", "source", "conditions", "origin", "binding"))
            for c in constraints
        ]
    relations = [r for r in literature.get("relations") or [] if isinstance(r, dict)]
    if relations:
        out["relations"] = [
            _pick(
                r,
                ("equation", "status", "r2_published", "r2_refitted", "fitted_equation")
                + ("source", "conditions", "error"),
            )
            for r in relations
        ]
    return out


def _explanation_digest(explanations: Any, headline_id: str | None) -> dict[str, Any] | None:
    if not isinstance(explanations, dict):
        return None
    out = _pick(explanations, ("summary", "recommendation", "coherence", "error"))
    cards = [c for c in explanations.get("equations") or [] if isinstance(c, dict)]
    card = next((c for c in cards if headline_id and c.get("model_id") == headline_id), None)
    if card:
        out["headline"] = _pick(
            card, ("overview", "term_explanations", "citations", "citation_titles")
        )
    return out or None


def build_run_digest(results: dict[str, Any] | None) -> dict[str, Any]:
    """
    The compact summary of a run's stored results. Works on the interim results of a
    running analysis too (sections that are not there yet are left out).
    """
    results = results if isinstance(results, dict) else {}
    discovery = results.get("discovery") if isinstance(results.get("discovery"), dict) else {}
    equations = [e for e in results.get("equations") or [] if isinstance(e, dict)]
    headline = (
        results.get("best_equation") if isinstance(results.get("best_equation"), dict) else None
    )
    headline_id = headline.get("model_id") if headline else None

    digest: dict[str, Any] = {
        "headline": _pick(headline, _EQUATION_FIELDS) if headline else None,
        "equations": [_pick(e, _EQUATION_FIELDS) for e in equations[:MAX_DIGEST_EQUATIONS]],
        "n_models_fitted": discovery.get("n_models_total"),
    }

    if discovery:
        digest["target"] = discovery.get("target")
        digest["data"] = _pick(discovery.get("split"), _SPLIT_FIELDS) | _pick(
            discovery, ("noise_ceiling_r2", "has_signal")
        )
        selection = _pick(
            discovery.get("selection"),
            (
                "headline_reason",
                "headline_is_reference",
                "agent_pick_rejected",
                "coherence_first",
            ),
        )
        if selection:
            digest["selection"] = selection
        series = _series_digest(discovery.get("series"))
        if series is not None:
            digest["series"] = series
        agent = _pick(discovery.get("agent"), _AGENT_FIELDS)
        if agent:
            digest["agent"] = agent
        literature = _literature_digest(discovery.get("literature"))
        if literature is not None:
            digest["literature"] = literature
        relations = discovery.get("relations")
        if isinstance(relations, dict):
            digest["known_laws"] = {
                "n_known_laws": relations.get("n_known_laws"),
                "headline_relations": (relations.get("headline") or [])[:MAX_DIGEST_RELATIONS],
            }

    explanation = _explanation_digest(results.get("explanations"), headline_id)
    if explanation is not None:
        digest["explanation"] = explanation

    digest["warnings"] = run_warnings(results)
    usage = results.get("usage")
    if isinstance(usage, dict):
        digest["llm_cost_usd"] = usage.get("total_cost_usd")
    if results.get("completed_at"):
        digest["completed_at"] = results["completed_at"]
    return digest


def run_state(run) -> dict[str, Any]:
    """Where a run stands: the fields every status view of a run shares."""
    return {
        "run_id": str(run.id),
        "status": str(getattr(run.status, "value", run.status)),
        "progress": run.progress or 0,
        "phase": phase_for(run.status, run.progress),
        "target_variable": (run.problem_description or {}).get("target_variable"),
        "error": run.error,
    }


def run_digest_payload(run) -> dict[str, Any]:
    """State of a run with its compact summary (summary endpoint and MCP result tool)."""
    return run_state(run) | {"summary": build_run_digest(run.results) if run.results else None}
