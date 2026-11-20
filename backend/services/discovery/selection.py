"""
Model selection: the single owner of "the recommended equation".

Protocol (deterministic, no LLM):
1. Candidates are ranked on cross-validated error only; the holdout is used once,
   for display, never to choose (choosing on it would make its scores optimistic).
2. Guards veto models that should not be recommended: undefined/failed fits, CV R2
   <= 0, near-singular fits, verdicts 'poor'/'failed'/'no_signal'. If no model passes,
   the guards relax to "usable and better than the mean" and the headline is marked weak.
3. Reference models (known laws fitted after the blind exploration) are only compared
   with, unless no discovered model is usable.
4. One-standard-error rule: every model whose CV RMSE is within one SE of the best is
   statistically tied with it. The agent's first recommendation wins if it is in that
   tie set; otherwise the simplest tied model does.
5. Rate laws (d target/dt) are scored on the derivative, so they get their own headline
   (``select_dynamic``) by the same protocol, after a simulation guard: a law that
   diverges, or does not reproduce the training trajectories when integrated, is vetoed.
6. Coherence first (only when the user supplied literature, ``literature_coherence.py``):
   the models without a conflict with that literature are selected among by steps 1-4,
   and the best-scoring model overall is kept beside the headline as the challenger,
   with the gap between the two in standard errors. A small gap with a conflicting
   challenger points to a wrong relationship, a large one to data that disagree with
   the literature; which of the two it is, is the reader's judgement. If no discovered
   model is coherent, a coherent supplied law is recommended; if there is none either,
   the metric alone decides and the reason says so.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.services.discovery.fitting import ModelResult

STRICT_BAD_VERDICTS = ("poor", "failed", "no_signal")


def guard(
    m: ModelResult,
    strict: bool = True,
    extra: Callable[[ModelResult], str | None] | None = None,
) -> str | None:
    """Why ``m`` cannot be recommended, or None. ``extra`` is a problem-specific veto."""
    if m.error:
        return f"fit failed: {m.error}"
    if extra is not None and (why := extra(m)):
        return why
    if m.cv_r2 is None or m.cv_rmse is None or not np.isfinite(m.cv_rmse):
        return "no cross-validated score"
    if m.cv_r2 <= 0:
        return f"cross-validated R2 {m.cv_r2:.3f} is not better than the mean"
    if strict:
        if m.verdict in STRICT_BAD_VERDICTS:
            return f"verdict '{m.verdict}'"
        if m.ill_conditioned:
            return "near-singular fit (parameters not identifiable)"
    elif m.verdict in ("failed", "no_signal"):
        return f"verdict '{m.verdict}'"
    return None


@dataclass
class Selection:
    headline: ModelResult | None
    headline_reason: str
    shortlist: list[ModelResult] = field(default_factory=list)
    agent_pick_rejected: list[dict[str, str]] = field(default_factory=list)
    tie_threshold: float | None = None
    # True when no candidate was usable and the headline fell back to a reference model
    headline_is_reference: bool = False
    # model_id -> why it is not usable (relaxed guard); not stored, the report shows it per card
    vetoes: dict[str, str] = field(default_factory=dict)
    # Coherence-first selection (supplied literature): counts, the challenger and the gap
    coherence_first: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {
            "headline_model_id": self.headline.model_id if self.headline else None,
            "headline_reason": self.headline_reason,
            "shortlist": [m.model_id for m in self.shortlist],
            "agent_pick_rejected": self.agent_pick_rejected,
            "tie_threshold_rmse": self.tie_threshold,
            "headline_is_reference": self.headline_is_reference,
        }
        if self.coherence_first is not None:
            out["coherence_first"] = self.coherence_first
        return out


def _simplicity(m: ModelResult) -> tuple:
    return (m.complexity, m.n_params, m.cv_rmse)


def usable(
    models: list[ModelResult], extra: Callable[[ModelResult], str | None] | None = None
) -> list[ModelResult]:
    """Models that pass the relaxed guard (usable and better than the mean)."""
    return [m for m in models if guard(m, strict=False, extra=extra) is None]


def _gap(challenger: ModelResult, coherent: ModelResult) -> float | None:
    """How much worse the coherent model's CV RMSE is, in standard errors of the challenger."""
    if not challenger.cv_se:
        return None
    return float((coherent.cv_rmse - challenger.cv_rmse) / challenger.cv_se)


def _coherent_reference(
    models: list[ModelResult],
    discovered: Selection,
    reference: Callable[[ModelResult], bool],
    conflicts: Callable[[ModelResult], list[str]],
    extra_guard: Callable[[ModelResult], str | None] | None,
) -> Selection | None:
    """
    No discovered model is coherent with the supplied literature: recommend the best
    coherent supplied law instead, with the discovered headline as the challenger.
    """
    laws = [
        m
        for m in models
        if reference(m)
        and m.kind == "literature"
        and guard(m, strict=False, extra=extra_guard) is None
        and not conflicts(m)
    ]
    challenger = discovered.headline
    if not laws or challenger is None:
        return None
    law = min(laws, key=lambda m: m.cv_rmse)
    info = dict(discovered.coherence_first or {})
    info.update(
        {
            "status": "coherent_reference",
            "challenger_model_id": challenger.model_id,
            "challenger_cv_rmse": challenger.cv_rmse,
            "best_coherent_cv_rmse": law.cv_rmse,
            "gap_se": _gap(challenger, law),
            "challenger_conflicts": conflicts(challenger),
            "headline_conflicts": [],  # the law is coherent; the challenger's are above
        }
    )
    shortlist = [law, *[m for m in discovered.shortlist if m is not law]][:3]
    return Selection(
        law,
        "coherent_literature_law",
        shortlist,
        discovered.agent_pick_rejected,
        discovered.tie_threshold,
        headline_is_reference=True,
        vetoes=discovered.vetoes,
        coherence_first=info,
    )


def select(
    models: list[ModelResult],
    recommended_ids: list[str],
    reference: Callable[[ModelResult], bool] | None = None,
    extra_guard: Callable[[ModelResult], str | None] | None = None,
    conflicts: Callable[[ModelResult], list[str]] | None = None,
) -> Selection:
    """
    The headline among the candidates; models matching ``reference`` (known laws) are
    for comparison and become the headline only when no candidate is usable.
    ``extra_guard`` vetoes models on a problem-specific test (rate-law simulation).
    ``conflicts`` lists a model's conflicts with the supplied literature; when given,
    the selection is coherence first (step 6 of the protocol).
    """
    if reference is not None:
        selection = select(
            [m for m in models if not reference(m)],
            recommended_ids,
            extra_guard=extra_guard,
            conflicts=conflicts,
        )
        if selection.headline is None:
            selection = select(
                models, recommended_ids, extra_guard=extra_guard, conflicts=conflicts
            )
            selection.headline_is_reference = selection.headline is not None
        elif conflicts is not None and (selection.coherence_first or {}).get("n_coherent") == 0:
            selection = (
                _coherent_reference(models, selection, reference, conflicts, extra_guard)
                or selection
            )
        return selection
    by_id = {m.model_id: m for m in models}
    vetoes = {m.model_id: why for m in models if (why := guard(m, strict=False, extra=extra_guard))}
    strict_pool = [m for m in models if guard(m, strict=True, extra=extra_guard) is None]
    strict = bool(strict_pool)
    pool = strict_pool or [m for m in models if m.model_id not in vetoes]
    rejected: list[dict[str, str]] = []
    if not pool:
        for mid in recommended_ids:
            m = by_id.get(mid)
            rejected.append(
                {"model_id": mid, "reason": guard(m, extra=extra_guard) if m else "unknown model"}
            )
        return Selection(None, "no_eligible_model", [], rejected, vetoes=vetoes)

    # Coherence first: rank among the models without a conflict with the supplied literature
    challenger = min(pool, key=lambda m: m.cv_rmse)
    conflict_of = {m.model_id: conflicts(m) for m in pool} if conflicts is not None else {}
    coherent = [m for m in pool if not conflict_of.get(m.model_id)] if conflicts else []
    rank_pool = coherent or pool

    best = min(rank_pool, key=lambda m: m.cv_rmse)
    threshold = best.cv_rmse + (best.cv_se or 0.0)
    tied = [m for m in rank_pool if m.cv_rmse <= threshold]

    headline, reason = None, ""
    for mid in recommended_ids:
        m = by_id.get(mid)
        if m is None:
            rejected.append({"model_id": mid, "reason": "unknown model"})
            continue
        why = guard(m, strict=strict, extra=extra_guard)
        if why:
            rejected.append({"model_id": mid, "reason": why})
        elif coherent and conflict_of.get(mid):
            rejected.append(
                {
                    "model_id": mid,
                    "reason": "conflicts with the supplied literature: "
                    + "; ".join(conflict_of[mid][:3]),
                }
            )
        elif m.cv_rmse > threshold:
            rejected.append(
                {
                    "model_id": mid,
                    "reason": f"CV RMSE {m.cv_rmse:.4g} is more than one standard error worse "
                    f"than the best ({best.model_id}, {best.cv_rmse:.4g})",
                }
            )
        else:
            headline, reason = m, "agent_pick_within_1se"
            break
    if headline is None:
        headline = min(tied, key=_simplicity)
        reason = "simplest_within_1se" if headline is not best else "best_cv"
    if not strict:
        reason += "_weak"  # nothing passed the strict guards

    coherence_first = None
    if conflicts is not None:
        if coherent:
            reason = "coherent_" + reason
        else:
            reason += "_no_coherent_model"
        shown = challenger is not best
        coherence_first = {
            "status": "coherent" if coherent else "no_coherent_model",
            "n_candidates": len(pool),
            "n_coherent": len(coherent),
            "challenger_model_id": challenger.model_id if shown else None,
            "challenger_cv_rmse": challenger.cv_rmse if shown else None,
            "best_coherent_cv_rmse": best.cv_rmse if coherent else None,
            "gap_se": _gap(challenger, best) if shown else 0.0 if coherent else None,
            "challenger_conflicts": conflict_of.get(challenger.model_id, []) if shown else [],
            "headline_conflicts": conflict_of.get(headline.model_id, []),
        }

    shortlist = [headline]
    for m in [challenger, best, *sorted(tied, key=_simplicity)]:
        if m not in shortlist and len(shortlist) < 3:
            shortlist.append(m)
    return Selection(
        headline,
        reason,
        shortlist,
        rejected,
        threshold,
        vetoes=vetoes,
        coherence_first=coherence_first,
    )


SIMULATION_MIN_R2 = 0.0


def simulation_guard(m: ModelResult) -> str | None:
    """Why a rate law cannot be recommended on its training-trajectory simulation, or None."""
    sim = m.simulation
    if not sim:
        return "not simulated"
    if sim.get("n_diverged"):
        return f"simulation diverges on {sim['n_diverged']} of {sim['n_episodes']} trajectories"
    if sim.get("r2") is None or sim["r2"] <= SIMULATION_MIN_R2:
        return "the integrated law does not reproduce the trajectories"
    return None


def select_dynamic(models: list[ModelResult], recommended_ids: list[str]) -> Selection:
    """The headline rate law: the usual protocol with the simulation guard."""
    return select(models, recommended_ids, extra_guard=simulation_guard)
