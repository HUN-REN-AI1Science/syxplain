"""
Literature scout: published laws, found by web search and fitted to the data.

The scout runs once, in the background, from the start of the run (it is slow: a
web-searching research model). Its laws are parsed, their variables mapped onto
the data's aliases, and every law that predicts the target is fitted like any
other model (ids L<n>, published constants as starting values). The agent sees the
outcome as an inbox event and through ``literature_status``; the explanation step
gets the citations. Nothing here ever calls the research model twice.
"""

import asyncio
import difflib
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from backend.services.discovery.expression import (
    ExpressionError,
    parameterize_constants,
    parse_expression,
)
from backend.services.discovery.session import DiscoverySession

logger = logging.getLogger(__name__)

GREEK = {
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "theta",
    "kappa",
    "lambda_",
    "lam",
    "mu",
    "nu",
    "rho",
    "sigma",
    "tau",
    "phi",
    "omega",
    "eta",
    "xi",
    "zeta",
}
_PARAM_PATTERNS = (
    re.compile(r"^[A-Za-z]{1,2}\d*$"),  # a, b0, Km, k2
    re.compile(r"^[A-Za-z]+_?\d+$"),  # R0, T_0, k_1
    re.compile(r"(max|min|opt|half|sat|ref)$", re.I),  # Pmax, Topt, Kref
)


def literature_features(
    session: DiscoverySession, descriptions: dict[str, str], project_description: str = ""
) -> dict[str, str]:
    """Alias-keyed variable descriptions for the research model, including the target."""
    out = {
        session.alias_of[col]: str(desc or col)
        for col, desc in descriptions.items()
        if col in session.alias_of
    }
    target_desc = descriptions.get(session.target_column) or project_description[:300]
    out[session.target_alias] = f"TARGET variable ({session.target_column})" + (
        f": {target_desc}" if target_desc else ""
    )
    return out


def _looks_like_parameter(name: str) -> bool:
    return name.lower() in GREEK or any(p.search(name) for p in _PARAM_PATTERNS)


def _map_identifier(name: str, session: DiscoverySession) -> str | None:
    aliases = [*session.features, session.target_alias]
    if name in aliases:
        return name
    lowered = {a.lower(): a for a in aliases}
    if name.lower() in lowered:
        return lowered[name.lower()]
    columns = {str(c): a for c, a in session.alias_of.items()}
    columns[session.target_column] = session.target_alias
    if name in columns:
        return columns[name]
    if len(name) > 2:
        close = difflib.get_close_matches(name, aliases, n=1, cutoff=0.85)
        if close:
            return close[0]
    return None


def fit_law(session: DiscoverySession, law: dict[str, Any], index: int) -> dict[str, Any]:
    """Map a published equation onto the data and fit it. Returns the law record."""
    text = str(law.get("equation") or "").strip()
    record: dict[str, Any] = {
        "equation": text,
        "citations": [str(c) for c in law.get("citations") or []][:5],
        "model_id": None,
        "cv_r2": None,
        "unmapped": [],
        "fit_error": None,
    }
    lhs, _, rhs = text.partition("=") if "=" in text else ("", "", text)
    lhs = lhs.strip()
    if lhs:
        target = _map_identifier(lhs, session)
        if target != session.target_alias:
            record["fit_error"] = f"relates other variables (left side '{lhs}'), not the target"
            return record
    try:
        raw = parse_expression(rhs, variables=[])  # every identifier as a "parameter" for now
    except ExpressionError as e:
        record["fit_error"] = f"could not parse: {e}"
        return record

    renames: dict[str, str] = {}
    unmapped = []
    for name in raw.parameters:
        alias = _map_identifier(name, session)
        if alias and alias != session.target_alias:
            renames[name] = alias
        elif not _looks_like_parameter(name):
            unmapped.append(name)
    if unmapped:
        record["unmapped"] = unmapped
        record["fit_error"] = f"variables not in the data: {unmapped}"
        return record
    if not renames:
        # Nothing mapped: the identifiers that are not obviously parameters are the
        # law's variables, and the data does not have them.
        unmapped = [n for n in raw.parameters if len(n) > 1 and n.lower() not in GREEK]
        record["unmapped"] = unmapped
        record["fit_error"] = (
            f"variables not in the data: {unmapped}"
            if unmapped
            else "uses none of the data's variables"
        )
        return record

    expression = rhs
    for name, alias in sorted(renames.items(), key=lambda kv: -len(kv[0])):
        expression = re.sub(
            rf"(?<![A-Za-z_0-9]){re.escape(name)}(?![A-Za-z_0-9])", alias, expression
        )
    # Published numeric constants become parameters started at their published values.
    template, values = parameterize_constants(expression, taken=session.features)
    try:
        model = session.fit_custom(
            template,
            initial_params=values,
            label=f"Published law {index}",
            kind="literature",
        )
    except ExpressionError as e:
        record["fit_error"] = str(e)
        return record
    record["model_id"] = model.model_id
    record["cv_r2"] = model.cv_r2
    if model.error:
        record["fit_error"] = model.error
    return record


async def run_literature(
    session: DiscoverySession, lookup: Callable[[], Awaitable[dict[str, Any]]]
) -> None:
    """Background task: research, fit, announce. Never raises."""
    session.known_laws = {"status": "pending", "laws": []}
    try:
        result = await lookup()
        equations = (result or {}).get("equations") or []
        if not equations:
            session.known_laws = {
                "status": "empty",
                "laws": [],
                "error": (result or {}).get("_parse_error"),
            }
            await session.emit("literature", "Literature search found no published laws")
            return
        laws = []
        for i, law in enumerate(equations[:12], start=1):
            if isinstance(law, dict):
                laws.append(await asyncio.to_thread(fit_law, session, law, i))
        session.known_laws = {"status": "ok", "laws": laws}
        fitted = [law for law in laws if law["model_id"] and law["cv_r2"] is not None]
        best = max(fitted, key=lambda law: law["cv_r2"], default=None)
        await session.emit(
            "literature",
            f"Literature: {len(laws)} published laws, {len(fitted)} fitted to the data"
            + (f"; best {best['model_id']} CV R2 {best['cv_r2']:.3f}" if best else ""),
        )
    except asyncio.CancelledError:
        session.known_laws = {"status": "failed", "laws": [], "error": "cancelled"}
        raise
    except Exception as e:
        logger.warning(f"Literature scout failed: {e}", exc_info=True)
        session.known_laws = {"status": "failed", "laws": [], "error": str(e)}
        await session.emit("literature", f"Literature search failed: {str(e)[:150]}")


def literature_summary(session: DiscoverySession) -> dict[str, Any]:
    laws = session.known_laws or {"status": "not_started", "laws": []}
    return {
        "status": laws.get("status"),
        "laws": [
            {k: law.get(k) for k in ("equation", "model_id", "cv_r2", "unmapped", "fit_error")}
            for law in laws.get("laws", [])
        ],
    }


def literature_context(known_laws: dict[str, Any] | None) -> dict[str, Any] | None:
    """Shape expected by the literature explanation signature, or None when nothing was found."""
    if not known_laws or known_laws.get("status") != "ok" or not known_laws.get("laws"):
        return None
    return {
        "equations": [
            {
                "equation": law["equation"],
                "citations": law.get("citations", []),
                "model_id": law.get("model_id"),
                "cv_r2": law.get("cv_r2"),
            }
            for law in known_laws["laws"]
        ]
    }
