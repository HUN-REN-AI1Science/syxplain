"""
Reconciler: makes the agent's report consistent with what actually happened.

Runs after all searches settled and before selection. It
1. finds searches whose results the agent never read (finished after it stopped,
   or simply never opened),
2. lets the agent look at them in a short read-only review pass when that is
   possible, otherwise marks the report stale and records the late results as
   notebook candidates,
3. checks the report's claims: every cited model id must exist and every R2 quoted
   next to an id must match the registry.
"""

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from backend.services.discovery.session import MODEL_ID_RE, DiscoverySession

logger = logging.getLogger(__name__)

R2_TOLERANCE = 0.02
_CLAIM_RE = re.compile(r"\b([CMSL]\d+)\b[^.;\n]{0,60}?\bR(?:2|²)\b\D{0,12}?(-?\d*\.\d+)")

ReviewFn = Callable[[dict[str, Any], list[str]], Awaitable[dict[str, Any]]]


def unread_searches(session: DiscoverySession) -> list[str]:
    return [s.search_id for s in session.searches.values() if s.unread]


def _claim_texts(session: DiscoverySession, report: dict[str, Any]) -> list[str]:
    texts = [str(report.get("summary", ""))]
    texts += [
        f"{r.get('form', '')}: {r.get('reason', '')}" for r in report.get("rejected_forms", [])
    ]
    texts += [str(x) for x in report.get("insights", [])]
    texts += [str(r.get("why", "")) for r in report.get("recommended_models", [])]
    texts += [n["text"] for n in session.notebook]
    return [t for t in texts if t.strip()]


def check_claims(session: DiscoverySession, report: dict[str, Any]) -> list[dict[str, str]]:
    failed: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for text in _claim_texts(session, report):
        for mid in MODEL_ID_RE.findall(text):
            if mid not in session.models and ("unknown", mid) not in seen:
                seen.add(("unknown", mid))
                failed.append({"text": text[:200], "issue": f"cites {mid}, which does not exist"})
        for mid, value in _CLAIM_RE.findall(text):
            m = session.models.get(mid)
            if m is None or (mid, value) in seen:
                continue
            seen.add((mid, value))
            actual = [
                v for v in (m.cv_r2, (m.holdout or {}).get("r2"), m.train_r2) if v is not None
            ]
            if actual and min(abs(float(value) - a) for a in actual) > R2_TOLERANCE:
                failed.append(
                    {
                        "text": text[:200],
                        "issue": f"quotes R2 {value} for {mid}; recorded CV R2 is {m.cv_r2:.3f}"
                        if m.cv_r2 is not None
                        else f"quotes R2 {value} for {mid}, which has no CV score",
                    }
                )
    return failed


async def reconcile(
    session: DiscoverySession,
    report: dict[str, Any],
    review: ReviewFn | None,
) -> dict[str, Any]:
    """Return the report with stale/late flags, review results and failed claims."""
    report = dict(report)
    late = unread_searches(session)
    if late and review is not None:
        try:
            report = await review(report, late)
        except Exception as e:  # the review is an improvement, never a requirement
            logger.warning(f"Review pass failed: {e}")
            report.setdefault("review_steps", 0)
    still_late = unread_searches(session)
    for sid in still_late:
        summary = session.searches[sid].summary(session.models)
        best = summary.get("best_model_id")
        if best:
            session.note(
                "candidate",
                f"{sid} finished after the agent stopped; its best equation {best} has CV R2 "
                f"{summary.get('best_cv_r2')} (not reviewed by the agent)",
                model_ids=[best],
            )
    report["stale"] = bool(still_late)
    report["late_searches"] = still_late
    report["reviewed_searches"] = [
        s.search_id for s in session.searches.values() if s.read_at is not None
    ]
    report["claims_failed"] = check_claims(session, report)
    report.setdefault("review_steps", 0)
    return report
