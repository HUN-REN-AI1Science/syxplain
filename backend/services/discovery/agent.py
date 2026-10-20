"""
The equation-discovery agent: a resilient, budget-aware DSPy ReAct loop.

On top of DSPy's ReAct it adds what a long scientific run on a modest model needs:
- a live STATE line after every observation (step/time budget, search status,
  top models, new events such as "pysr_2 completed"),
- a guarded finish: the agent cannot stop while search results are pending or
  unread and time remains,
- resilience: an unparseable step becomes a corrective observation, transient LLM
  errors are retried with backoff, and a failed final extraction falls back to a
  report built from the session (so a run always has a report),
- trajectory compaction: old steps are condensed so the prompt does not grow
  quadratically.
"""

import asyncio
import json
import logging
import re
import time
from typing import Any

import dspy
from dspy.utils.exceptions import ContextWindowExceededError

from backend.infrastructure.llm.signatures import DiscoveryReview, EquationDiscoveryAgent
from backend.services.discovery.selection import guard
from backend.services.discovery.session import DiscoverySession
from backend.utils.json_utils import clean_and_fix_json_string

logger = logging.getLogger(__name__)

try:  # DSPy >= 3.4
    from dspy.utils.exceptions import AdapterParseError
except ImportError:  # pragma: no cover - older DSPy
    AdapterParseError = ValueError

_transient: list[type[BaseException]] = []
try:
    from dspy.utils import exceptions as _dspy_exc

    _transient += [
        getattr(_dspy_exc, n)
        for n in ("LMRateLimitError", "LMTimeoutError", "LMServerError", "LMTransportError")
        if hasattr(_dspy_exc, n)
    ]
except ImportError:  # pragma: no cover
    pass
try:
    import litellm

    _transient += [
        litellm.RateLimitError,
        litellm.ServiceUnavailableError,
        litellm.InternalServerError,
        litellm.APIConnectionError,
        litellm.Timeout,
    ]
except (ImportError, AttributeError):  # pragma: no cover
    pass
TRANSIENT_ERRORS = tuple(_transient) or (ConnectionError,)

BACKOFF_S = (15, 30, 60)
KEEP_VERBATIM_STEPS = 6
_ID_RE = re.compile(r'"model_id":"([CMSL]\d+)"')
_CV_RE = re.compile(r'"cv_r2":(-?[\d.]+|null)')
_VERDICT_RE = re.compile(r'"verdict":"(\w+)"')


def _compact_observation(obs: Any) -> str:
    text = str(obs)
    if text.startswith(("Error", "BUDGET", "Execution error", "Your last output", "Not finished")):
        return text[:160]
    ids = _ID_RE.findall(text)[:4]
    cvs = _CV_RE.findall(text)[:4]
    verdicts = _VERDICT_RE.findall(text)[:4]
    if ids:
        parts = [
            f"{i} cv_r2={c} {v}"
            for i, c, v in zip(ids, cvs + [""] * 4, verdicts + [""] * 4, strict=False)
        ]
        return "(condensed) " + "; ".join(parts)
    return "(condensed) " + text[:160]


class BudgetedReAct(dspy.ReAct):
    def __init__(
        self,
        signature,
        tools,
        session: DiscoverySession,
        max_iters: int,
        guard_finish: bool = True,
    ):
        super().__init__(signature, tools=tools, max_iters=max_iters)
        self.session = session
        self.guard_finish = guard_finish
        # finish | steps | time | context | invalid | llm_error | cancelled
        self.ended = "finish"

    # -- prompt size -------------------------------------------------------

    def _format_trajectory(self, trajectory: dict[str, Any]):
        # DSPy's truncation drops the oldest steps, so indices need not start at 0.
        idxs = sorted({int(k.rsplit("_", 1)[1]) for k in trajectory if k.startswith("tool_name_")})
        if len(idxs) <= KEEP_VERBATIM_STEPS:
            return super()._format_trajectory(trajectory)
        cutoff = idxs[-KEEP_VERBATIM_STEPS]
        compact: dict[str, Any] = {}
        for key, value in trajectory.items():
            idx = int(key.rsplit("_", 1)[1])
            if idx >= cutoff:
                compact[key] = value
            elif key.startswith("thought_"):
                compact[key] = str(value)[:150]
            elif key.startswith("tool_args_"):
                compact[key] = json.dumps(value, default=str)[:200]
            elif key.startswith("observation_"):
                compact[key] = _compact_observation(value)
            else:
                compact[key] = value
        return super()._format_trajectory(compact)

    # -- one LM decision, with resilience ----------------------------------

    async def _decide(self, trajectory, input_args):
        """Next step from the LM, or None when the loop must stop."""
        for attempt in range(len(BACKOFF_S) + 1):
            try:
                return await self._async_call_with_potential_trajectory_truncation(
                    self.react, trajectory, **input_args
                )
            except asyncio.CancelledError:
                raise
            except ContextWindowExceededError as err:
                logger.warning(f"Discovery agent hit the context window: {err}")
                self.ended = "context"
                return None
            except TRANSIENT_ERRORS as err:
                if attempt == len(BACKOFF_S) or self.session.remaining_s < BACKOFF_S[attempt] + 60:
                    logger.warning(f"Discovery agent giving up after LM errors: {err}")
                    self.ended = "llm_error"
                    return None
                await self.session.emit("agent", "LLM busy, retrying shortly")
                await asyncio.sleep(BACKOFF_S[attempt])
        return None

    async def aforward(self, **input_args):
        trajectory: dict[str, Any] = {}
        tool_names = [n for n in self.tools if n != "finish"]
        invalid_streak = 0
        refused_for: set[str] = set()
        idx = 0
        self.ended = "steps"
        while idx < self.max_iters:
            if self.session.cancelled:
                self.ended = "cancelled"
                break
            if self.session.remaining_s <= 0:
                await self.session.emit("agent", "Time budget used up — writing the report")
                self.ended = "time"
                break
            try:
                pred = await self._decide(trajectory, input_args)
            except (AdapterParseError, ValueError) as err:
                invalid_streak += 1
                trajectory[f"thought_{idx}"] = "(invalid step)"
                trajectory[f"tool_name_{idx}"] = "invalid"
                trajectory[f"tool_args_{idx}"] = {}
                trajectory[f"observation_{idx}"] = (
                    f"Your last output could not be parsed ({type(err).__name__}: {str(err)[:300]}). "
                    f"Reply with next_thought, next_tool_name (one of: {', '.join(tool_names)}, "
                    "finish) and next_tool_args as a JSON object."
                )
                idx += 1
                if invalid_streak >= 2:
                    self.ended = "invalid"
                    break
                continue
            if pred is None:
                break
            invalid_streak = 0
            name, args = pred.next_tool_name, pred.next_tool_args or {}
            trajectory[f"thought_{idx}"] = pred.next_thought
            trajectory[f"tool_name_{idx}"] = name
            trajectory[f"tool_args_{idx}"] = args
            if pred.next_thought:
                await self.session.emit("thought", str(pred.next_thought)[:400])

            if name == "finish":
                blocking = self._finish_blockers()
                key = ",".join(blocking)
                if blocking and key not in refused_for:
                    refused_for.add(key)
                    idx += 1
                    trajectory[f"observation_{idx - 1}"] = (
                        f"Not finished yet: {', '.join(blocking)} still pending or unread. Call "
                        "wait_for_searches and then search_results for each, so the report covers "
                        "them (or cancel_search a search you no longer need).\n"
                        + self.session.state_line(idx, self.max_iters)
                    )
                    self.session.steps_used = idx
                    continue
                trajectory[f"observation_{idx}"] = "Completed."
                self.ended = "finish"
                idx += 1
                break

            try:
                observation = await self.tools[name].acall(**args)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                observation = f"Execution error in {name}: {str(err)[:400]}"
            idx += 1
            self.session.steps_used = idx
            trajectory[f"observation_{idx - 1}"] = (
                f"{observation}\n{self.session.state_line(idx, self.max_iters)}"
            )
        self.session.steps_used = max(self.session.steps_used, idx)

        try:
            extract = await self._async_call_with_potential_trajectory_truncation(
                self.extract, trajectory, **input_args
            )
            return dspy.Prediction(trajectory=trajectory, **extract)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            logger.warning(f"Discovery report extraction failed: {err}")
            return dspy.Prediction(trajectory=trajectory, report_json="", extract_error=str(err))

    def _finish_blockers(self) -> list[str]:
        if not self.guard_finish or self.session.remaining_s <= 180:
            return []
        return [s.search_id for s in self.session.pending_or_unread()]


# ---------------------------------------------------------------------------
# Report parsing (LLM output -> validated report)
# ---------------------------------------------------------------------------


def _as_text(value: Any, limit: int = 500) -> str:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, dict):
        for key in ("text", "insight", "question", "description", "value"):
            if isinstance(value.get(key), str):
                extra = value.get("evidence") or value.get("model_id")
                return (value[key] + (f" — {extra}" if isinstance(extra, str) else ""))[:limit]
        return "; ".join(f"{k}: {v}" for k, v in value.items())[:limit]
    return str(value)[:limit]


def fallback_report(session: DiscoverySession, reason: str) -> dict[str, Any]:
    """Report built from session state when the agent could not write one."""
    candidates = [m for m in session.ranked_models() if guard(m) is None][:3]
    return {
        "summary": "The agent could not write its final report; the recommendation below is "
        f"based on the cross-validated leaderboard and the notebook ({reason}).",
        "recommended_models": [
            {"model_id": m.model_id, "why": f"top cross-validated model (CV R2 {m.cv_r2:.3f})"}
            for m in candidates
        ],
        "rejected_forms": [
            {"form": n["text"][:120], "model_id": (n.get("model_ids") or [None])[0], "reason": ""}
            for n in session.notebook
            if n["kind"] == "rejected_form"
        ],
        "insights": [n["text"] for n in session.notebook if n["kind"] == "insight"][:20],
        "open_questions": [],
        "source": "auto_fallback",
    }


def parse_report(raw: str, session: DiscoverySession) -> dict[str, Any]:
    """Parse and coerce the agent's report; fall back to session state when unusable."""
    try:
        report = json.loads(clean_and_fix_json_string(raw or ""))
        if not isinstance(report, dict):
            raise ValueError("report is not an object")
    except Exception as e:
        logger.warning(f"Could not parse discovery report: {e}; raw={str(raw)[:300]!r}")
        return fallback_report(session, "unparseable report")

    recommended = []
    for item in report.get("recommended_models") or []:
        mid = item.get("model_id") if isinstance(item, dict) else item
        if isinstance(mid, str) and mid in session.models:
            why = item.get("why", "") if isinstance(item, dict) else ""
            recommended.append({"model_id": mid, "why": _as_text(why)})
    rejected = []
    for item in report.get("rejected_forms") or []:
        if isinstance(item, dict):
            mid = item.get("model_id")
            rejected.append(
                {
                    "form": _as_text(item.get("form", ""), 200),
                    "model_id": mid if isinstance(mid, str) and mid in session.models else None,
                    "reason": _as_text(item.get("reason", "")),
                }
            )
        else:
            rejected.append({"form": _as_text(item, 200), "model_id": None, "reason": ""})
    out = {
        "summary": _as_text(report.get("summary", ""), 3000),
        "recommended_models": recommended,
        "rejected_forms": rejected[:30],
        "insights": [_as_text(x) for x in (report.get("insights") or []) if x][:20],
        "open_questions": [_as_text(x) for x in (report.get("open_questions") or []) if x][:20],
        "source": "agent",
    }
    if not out["summary"] and not recommended:
        return fallback_report(session, "empty report")
    return out


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


def _budget_info(session: DiscoverySession, max_iters: int) -> dict[str, Any]:
    return {
        "max_steps": max_iters,
        "wall_clock_minutes": round(session.remaining_s / 60),
        "pysr_searches_max": session.budget.max_pysr_runs,
        "pysr_searches_used": len(session.searches),
        "max_concurrent_pysr_searches": session.budget.max_concurrent_pysr,
        "pysr_timeout_minutes": round(session.budget.pysr_timeout_s / 60),
    }


async def run_discovery_agent(
    session: DiscoverySession,
    tools: list,
    lm: dspy.LM,
    project_description: dict[str, Any],
    max_iters: int,
) -> dict[str, Any]:
    """Run the agent to completion and return its (validated) report."""
    await session.ensure_profile()
    agent = BudgetedReAct(EquationDiscoveryAgent, tools, session=session, max_iters=max_iters)
    initial = [s.summary(session.models) for s in session.searches.values()]

    await session.emit("agent", "Discovery agent started")
    with dspy.settings.context(lm=lm):
        prediction = await agent.acall(
            project_description=json.dumps(project_description, indent=1),
            data_overview=json.dumps(session.overview(), separators=(",", ":")),
            budget=json.dumps(_budget_info(session, max_iters)),
            initial_searches=json.dumps(initial),
        )
    session.agent_finished_at = time.monotonic()
    if getattr(prediction, "extract_error", None):
        report = fallback_report(session, "report extraction failed")
    else:
        report = parse_report(getattr(prediction, "report_json", ""), session)
    report["steps"] = sum(1 for k in prediction.trajectory if k.startswith("tool_name_"))
    report["ended"] = agent.ended
    await session.emit("agent", f"Discovery agent finished ({agent.ended})")
    return report


async def run_review(
    session: DiscoverySession,
    tools: list,
    lm: dspy.LM,
    project_description: dict[str, Any],
    previous_report: dict[str, Any],
    late_searches: list[str],
    max_iters: int,
) -> dict[str, Any]:
    """Short read-only pass over searches that finished after the agent stopped."""
    allowed = {"search_results", "inspect_model", "leaderboard", "note"}
    agent = BudgetedReAct(
        DiscoveryReview,
        [t for t in tools if t.__name__ in allowed],
        session=session,
        max_iters=max_iters,
        guard_finish=False,
    )
    new = [session.searches[s].summary(session.models) for s in late_searches]
    await session.emit("agent", f"Reviewing late results: {', '.join(late_searches)}")
    with dspy.settings.context(lm=lm):
        prediction = await agent.acall(
            project_description=json.dumps(project_description, indent=1),
            previous_report=json.dumps(previous_report, default=str)[:6000],
            new_results=json.dumps(new, default=str),
        )
    if getattr(prediction, "extract_error", None):
        return previous_report | {"review_steps": 0}
    report = parse_report(getattr(prediction, "report_json", ""), session)
    if report.get("source") == "auto_fallback":
        return previous_report | {"review_steps": 0}
    report["steps"] = previous_report.get("steps")
    report["ended"] = previous_report.get("ended")
    report["review_steps"] = sum(1 for k in prediction.trajectory if k.startswith("tool_name_"))
    return report
