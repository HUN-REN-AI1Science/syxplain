"""
Model selection: the single owner of "the recommended equation".

Protocol (deterministic, no LLM):
1. Candidates are ranked on cross-validated error only; the holdout is used once,
   for display, never to choose (choosing on it would make its scores optimistic).
2. Guards veto models that should not be recommended: undefined/failed fits, CV R2
   <= 0, near-singular fits, verdicts 'poor'/'failed'/'no_signal'. If no model passes,
   the guards relax to "usable and better than the mean" and the headline is marked weak.
3. One-standard-error rule: every model whose CV RMSE is within one SE of the best is
   statistically tied with it. The agent's first recommendation wins if it is in that
   tie set; otherwise the simplest tied model does.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.services.discovery.fitting import ModelResult

STRICT_BAD_VERDICTS = ("poor", "failed", "no_signal")


def guard(m: ModelResult, strict: bool = True) -> str | None:
    """Why ``m`` cannot be recommended, or None."""
    if m.error:
        return f"fit failed: {m.error}"
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "headline_model_id": self.headline.model_id if self.headline else None,
            "headline_reason": self.headline_reason,
            "shortlist": [m.model_id for m in self.shortlist],
            "agent_pick_rejected": self.agent_pick_rejected,
            "tie_threshold_rmse": self.tie_threshold,
        }


def _simplicity(m: ModelResult) -> tuple:
    return (m.complexity, m.n_params, m.cv_rmse)


def select(models: list[ModelResult], recommended_ids: list[str]) -> Selection:
    by_id = {m.model_id: m for m in models}
    strict_pool = [m for m in models if guard(m, strict=True) is None]
    strict = bool(strict_pool)
    pool = strict_pool or [m for m in models if guard(m, strict=False) is None]
    rejected: list[dict[str, str]] = []
    if not pool:
        for mid in recommended_ids:
            m = by_id.get(mid)
            rejected.append({"model_id": mid, "reason": guard(m) if m else "unknown model"})
        return Selection(None, "no_eligible_model", [], rejected)

    best = min(pool, key=lambda m: m.cv_rmse)
    threshold = best.cv_rmse + (best.cv_se or 0.0)
    tied = [m for m in pool if m.cv_rmse <= threshold]

    headline, reason = None, ""
    for mid in recommended_ids:
        m = by_id.get(mid)
        if m is None:
            rejected.append({"model_id": mid, "reason": "unknown model"})
            continue
        why = guard(m, strict=strict)
        if why:
            rejected.append({"model_id": mid, "reason": why})
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

    shortlist = [headline]
    for m in [best, *sorted(tied, key=_simplicity)]:
        if m not in shortlist and len(shortlist) < 3:
            shortlist.append(m)
    return Selection(headline, reason, shortlist, rejected, threshold)
