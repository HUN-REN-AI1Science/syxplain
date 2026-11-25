"""
LLM usage and cost of one analysis run.

Every DSPy call inside ``dspy.track_usage()`` records its token usage per model (DSPy
does this itself, across asyncio tasks and worker threads). This module adds the web
searches of the literature search, prices everything, and writes one machine-readable
``ANALYTICS run_usage {...}`` log line per run, so cost can be read back from the logs:

    docker logs syxplain-backend 2>&1 | grep "ANALYTICS run_usage"
"""

import json
import logging
import os
from typing import Any

import dspy

logger = logging.getLogger(__name__)

# USD per 1M tokens: (input, cached input, output). Reasoning tokens are billed as output
# and are already part of the output count. Override or extend with LLM_PRICES_JSON, e.g.
# '{"gpt-6.1-sol": [2.0, 0.1, 10.0]}'.
DEFAULT_PRICES: dict[str, tuple[float, float, float]] = {
    "gpt-6.1-sol": (2.00, 0.10, 10.00),
    "gpt-6-sol": (2.00, 0.20, 10.00),
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-6-astra": (10.00, 1.00, 50.00),
    "gpt-5.6-sol": (4.00, 0.40, 20.00),
    "gpt-5.6-terra": (2.00, 0.20, 12.00),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-5.5": (5.00, 0.50, 30.00),
    "gpt-5.4": (2.50, 0.25, 15.00),
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
    "gpt-5.4-nano": (0.20, 0.02, 1.25),
}
WEB_SEARCH_USD = float(os.environ.get("LLM_WEB_SEARCH_USD", "0.01"))  # per search call
WEB_SEARCHES_KEY = "web_search_calls"


def _prices() -> dict[str, tuple[float, float, float]]:
    prices = dict(DEFAULT_PRICES)
    raw = os.environ.get("LLM_PRICES_JSON")
    if raw:
        try:
            prices.update({k: tuple(map(float, v)) for k, v in json.loads(raw).items()})
        except (ValueError, TypeError) as e:
            logger.warning(f"Ignoring LLM_PRICES_JSON: {e}")
    return prices


def _price_for(model: str) -> tuple[float, float, float] | None:
    """Price of 'openai/gpt-5.5-2026-04-23' is found under 'gpt-5.5' (longest prefix)."""
    name = model.split("/", 1)[-1]
    prices = _prices()
    matches = [k for k in prices if name == k or name.startswith(k + "-")]
    return prices[max(matches, key=len)] if matches else None


def _tokens(usage: dict[str, Any]) -> dict[str, int]:
    """Chat Completions and Responses API usage, in one shape."""

    def details(*keys: str) -> dict[str, Any]:
        for key in keys:
            if isinstance(usage.get(key), dict):
                return usage[key]
        return {}

    return {
        "input_tokens": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
        "cached_input_tokens": int(
            details("prompt_tokens_details", "input_tokens_details").get("cached_tokens") or 0
        ),
        "output_tokens": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        "reasoning_tokens": int(
            details("completion_tokens_details", "output_tokens_details").get("reasoning_tokens")
            or 0
        ),
        WEB_SEARCHES_KEY: int(usage.get(WEB_SEARCHES_KEY) or 0),
    }


def record_web_searches(lm: dspy.LM) -> int:
    """Count the web searches of the LM's last Responses API call into the active tracker."""
    if not lm.history:
        return 0
    response = lm.history[-1].get("response")
    output = getattr(response, "output", None) or []
    n = sum(1 for item in output if getattr(item, "type", None) == "web_search_call")
    tracker = dspy.settings.usage_tracker
    if n and tracker is not None:
        tracker.add_usage(lm.model, {WEB_SEARCHES_KEY: n})
    return n


def summarize(tracker: Any) -> dict[str, Any]:
    """Tokens, calls, web searches and USD cost per model, plus the run total."""
    models: dict[str, dict[str, Any]] = {}
    unpriced = []
    total = 0.0
    for model, entries in tracker.usage_data.items():
        row = {"calls": 0, **dict.fromkeys(_tokens({}), 0)}
        for entry in entries:
            tokens = _tokens(entry or {})
            for key, value in tokens.items():
                row[key] += value
            if not tokens[WEB_SEARCHES_KEY]:  # web-search entries are added per LM call
                row["calls"] += 1
        price = _price_for(model)
        cost = row[WEB_SEARCHES_KEY] * WEB_SEARCH_USD
        if price is None:
            unpriced.append(model)
        else:
            in_rate, cached_rate, out_rate = price
            uncached = max(row["input_tokens"] - row["cached_input_tokens"], 0)
            cost += (
                uncached * in_rate
                + row["cached_input_tokens"] * cached_rate
                + row["output_tokens"] * out_rate
            ) / 1e6
        row["cost_usd"] = round(cost, 4)
        total += cost
        models[model] = row
    return {"models": models, "total_cost_usd": round(total, 4), "unpriced_models": unpriced}


def log_run_usage(run_id: str, outcome: str, summary: dict[str, Any]) -> None:
    """One grep-able line per run (completed, failed or cancelled)."""
    logger.info(
        "ANALYTICS run_usage %s",
        json.dumps({"run_id": run_id, "outcome": outcome, **summary}, separators=(",", ":")),
    )
