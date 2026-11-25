"""
Feature stage of a long series: the LLM proposes time-dependent features, the code
computes and measures them, the LLM selects among them, and the selection becomes
ordinary features of the session before the first PySR search.

Generation → selection → PySR. A failure here never stops the run: it continues with
the current features and the reason is recorded in ``session.series["feature_stage"]``.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from backend.services.discovery.features import MAX_PROPOSED, MAX_SELECTED, FeatureSpec

logger = logging.getLogger(__name__)


def parse_specs(text: str) -> tuple[list[FeatureSpec], list[dict[str, str]]]:
    """Specs from the proposer's JSON; malformed entries are rejected with the reason."""
    raw = json.loads(text)
    if isinstance(raw, dict):  # {"specs": [...]}
        raw = next((v for v in raw.values() if isinstance(v, list)), [])
    if not isinstance(raw, list):
        raise ValueError("The proposal is not a JSON list of specs")
    specs, rejected = [], []
    for item in raw:
        try:
            # A proposal cannot claim to come from the orders of the automatic ARIMA fit
            specs.append(FeatureSpec.model_validate(item).model_copy(update={"origin": "proposed"}))
        except ValidationError as e:
            first = e.errors()[0]
            where = ".".join(str(x) for x in first["loc"])
            rejected.append({"spec": json.dumps(item)[:160], "reason": f"{where}: {first['msg']}"})
    return specs, rejected


def parse_note(text: str) -> str:
    """The proposer's note for the equation search ('' when the proposal has none)."""
    try:
        raw = json.loads(text)
    except ValueError:
        return ""
    note = raw.get("search_note") if isinstance(raw, dict) else None
    return note.strip() if isinstance(note, str) else ""


def parse_selection(text: str, known: set[str]) -> tuple[dict[str, str], str, list[str]]:
    """Selected alias -> reason (known aliases only, at most MAX_SELECTED), rationale, ignored."""
    raw = json.loads(text)
    items = raw.get("selected", []) if isinstance(raw, dict) else raw
    reasons: dict[str, str] = {}
    ignored: list[str] = []
    for item in items or []:
        alias = item.get("feature") if isinstance(item, dict) else item
        reason = item.get("reason", "") if isinstance(item, dict) else ""
        if not isinstance(alias, str) or alias not in known:
            ignored.append(str(alias))
        elif alias not in reasons and len(reasons) < MAX_SELECTED:
            reasons[alias] = str(reason)
        elif alias not in reasons:
            ignored.append(f"{alias} (beyond {MAX_SELECTED})")
    rationale = raw.get("rationale", "") if isinstance(raw, dict) else ""
    return reasons, str(rationale), ignored


SOURCES = ("both", "llm", "orders")


async def run_series_feature_stage(
    session: Any,
    make_lm: Callable[[], Any],
    project: dict[str, Any],
    source: str = "both",
    images: bool = True,
) -> None:
    """
    Generation → selection for a long series; adds the selection to ``session``.
    ``source`` says where the features come from: the LLM's proposals ("llm"), the orders
    of an automatic ARIMA fit of the target ("orders"), or both. With both, the LLM is
    shown what that fit found and what it leaves open (``images``: also as a picture), and
    proposes what the fit cannot: longer cycles, earlier conditions of the other columns,
    and a note on nonlinear dynamics for the equation search.
    ``make_lm`` builds the DSPy model (an error there counts as a stage failure);
    ``project`` is the agent's project description (target and variable descriptions).
    The CPU work (computing and measuring candidates) runs in a worker thread.
    """
    from backend.services.llm_service import propose_series_features, select_series_features

    if session.series is None:
        return
    if source not in SOURCES:
        source = "both"
    stage: dict[str, Any] = {"status": "running", "source": source}
    session.series["feature_stage"] = stage
    try:
        lm = make_lm() if source != "orders" else None
        context = session.series_feature_context()

        # ORDERS: the earlier values and earlier errors an automatic ARIMA fit names
        from_orders: list[FeatureSpec] = []
        try:
            if source != "llm":
                from_orders = await asyncio.to_thread(session.series_order_specs)
        except Exception as e:  # the proposals below do not depend on it
            logger.warning(f"Automatic ARIMA orders failed: {e}", exc_info=True)
            session.series["orders"] = {"status": "failed", "message": str(e)[:300]}
        context["from_orders"] = [s.label() for s in from_orders]
        found = session.series.get("orders") or {}
        sarimax_json = json.dumps(found, default=str) if "p" in found else ""
        plots = [session.series_plot] if images and sarimax_json and session.series_plot else []
        note = ""
        context_json = json.dumps(context, default=str)
        project_json = json.dumps(project, default=str)

        # GENERATION (one retry when nothing proposed could be computed)
        feedback = ""
        candidates, rejected, evidence, proposed = [], [], None, 0
        if source == "orders":
            candidates, rejected, evidence = await asyncio.to_thread(
                session.evaluate_feature_specs, from_orders
            )
        for attempt in range(2 if source != "orders" else 0):
            text = await asyncio.to_thread(
                propose_series_features,
                project_json,
                context_json,
                feedback,
                lm,
                sarimax_json,
                plots,
            )
            try:
                specs, bad = parse_specs(text)
            except ValueError as e:  # not JSON, or not a list: ask once more
                if attempt and not from_orders:
                    raise
                if attempt:  # the features named by the orders are still computed
                    candidates, refused, evidence = await asyncio.to_thread(
                        session.evaluate_feature_specs, from_orders
                    )
                    rejected += refused
                    break
                feedback = json.dumps(
                    {
                        "error": f"not a JSON list of specs ({str(e)[:160]})",
                        "max_specs": MAX_PROPOSED,
                    }
                )
                continue
            computed, refused, ev = await asyncio.to_thread(
                session.evaluate_feature_specs, from_orders + specs
            )
            proposed += len(specs) + len(bad)
            note = parse_note(text) or note
            rejected += [r for r in bad + refused if r not in rejected]
            if computed:
                candidates, evidence = computed, ev
            if any(c.spec.origin == "proposed" for c in computed):
                break
            if not specs and not bad:
                break  # nothing proposed: the LLM sees no time dependence
            feedback = json.dumps({"rejected": bad + refused, "max_specs": MAX_PROPOSED})
        await session.emit(
            "features",
            f"Feature stage: {len(candidates)} time-dependent candidates computed "
            f"({len(rejected)} specs rejected)",
        )

        # SELECTION
        reasons, rationale, ignored = {}, "", []
        fixed = {c.alias: c.spec.rationale for c in candidates if c.spec.origin == "orders"}
        if len(candidates) > len(fixed):
            text = await asyncio.to_thread(
                select_series_features,
                project_json,
                context_json,
                json.dumps(evidence["candidates"]),
                json.dumps(evidence["residual_autocorrelation_current"]),
                MAX_SELECTED,
                lm,
            )
            reasons, rationale, ignored = parse_selection(
                text, {c.alias for c in candidates} - set(fixed)
            )
        reasons = fixed | reasons
        selected = [c for c in candidates if c.alias in reasons]
        stage |= {
            "status": "done",
            "proposed": proposed,
            "computed": len(candidates),
            "selected": len(selected),
            "from_orders": len(fixed),
            "rationale": rationale,
            "ignored_selection": ignored,
        }
        if note:
            session.series["search_note"] = note[:1200]
        await asyncio.to_thread(
            session.add_series_features,
            selected,
            reasons,
            {"rejected": rejected, "evidence": evidence},
        )
        names = ", ".join(c.alias for c in selected) or "none"
        await session.emit("features", f"Selected time-dependent features: {names}")
    except Exception as e:
        logger.warning(f"Series feature stage failed: {e}", exc_info=True)
        stage |= {"status": "failed", "message": str(e)[:300]}
        session.note(
            "data_issue",
            "The time-dependent feature stage failed, so the run continues with the current "
            f"values only ({str(e)[:160]})",
        )
