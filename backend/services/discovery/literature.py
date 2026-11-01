"""
Literature scout: published laws, found by web search and fitted to the data.

The scout runs once, in the background, from the start of the run (it is slow: a
web-searching research model). Its laws are parsed, their variables mapped onto
the data's aliases, and every law that predicts the target is fitted like any
other model (ids L<n>, published constants as starting values). The agent never sees
them: they are fitted after exploration and compared with what it discovered
(``relate.py``); the explanation step gets the citations. Nothing here ever calls the
research model twice.
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

MAX_LAWS = 12

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
# A coefficient named after its variable (a_PDSI, b0_SMI, beta_CO2, b_trend): a
# parameter, never fuzzily mapped onto that variable.
_COEFFICIENT = re.compile(rf"^(?:[a-z]\d*|{'|'.join(GREEK)})_[A-Za-z]\w*$", re.I)


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
    return (
        name.lower() in GREEK
        or bool(_COEFFICIENT.match(name))
        or any(p.search(name) for p in _PARAM_PATTERNS)
    )


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
    if len(name) > 2 and not _COEFFICIENT.match(name):
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
        "citation_titles": [str(t).strip() for t in law.get("citation_titles") or []][:5],
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
    parameters: list[str] = []
    unmapped = []
    for name in raw.parameters:
        alias = _map_identifier(name, session)
        if alias and alias != session.target_alias:
            renames[name] = alias
        elif _looks_like_parameter(name):
            parameters.append(name)
        else:
            unmapped.append(name)
    if unmapped:
        record["unmapped"] = unmapped
        record["fit_error"] = f"variables not in the data: {unmapped}"
        return record
    if not renames:
        # Nothing mapped: the identifiers that are not obviously parameters are the
        # law's variables, and the data does not have them.
        unmapped = [
            n
            for n in raw.parameters
            if len(n) > 1 and n.lower() not in GREEK and not _COEFFICIENT.match(n)
        ]
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
    template, values = parameterize_constants(expression, taken=[*session.features, *parameters])
    try:
        model = session.fit_custom(
            template,
            # declared, so a_PDSI is not taken for a typo of PDSI
            initial_params=dict.fromkeys(parameters, 1.0) | values,
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
    """
    Background task: research and collect, without fitting. Never raises.

    Exploration is blind to known laws, so nothing reaches the agent: the laws are
    fitted after exploration by ``fit_literature_laws`` (the RELATE step).
    """
    session.known_laws = {"status": "pending", "laws": []}
    try:
        result = await lookup()
        equations = (result or {}).get("equations") or []
        raw = [law for law in equations[:MAX_LAWS] if isinstance(law, dict)]
        if not raw:
            session.known_laws = {
                "status": "empty",
                "laws": [],
                "error": (result or {}).get("_parse_error"),
            }
            await session.emit("literature", "Literature search found no published laws")
            return
        session.literature_raw = raw  # known_laws stays pending until RELATE fits them
        await session.emit(
            "literature",
            f"Literature: {len(raw)} published laws found; they are compared with the "
            "discovered equations at the end",
        )
    except asyncio.CancelledError:
        session.known_laws = {"status": "failed", "laws": [], "error": "cancelled"}
        raise
    except Exception as e:
        logger.warning(f"Literature scout failed: {e}", exc_info=True)
        session.known_laws = {"status": "failed", "laws": [], "error": str(e)}
        await session.emit("literature", f"Literature search failed: {str(e)[:150]}")


def fit_literature_laws(session: DiscoverySession) -> list[dict[str, Any]]:
    """Fit the collected published laws to the data (RELATE step); returns the fitted ones."""
    if session.literature_raw is None:
        return []
    laws = []
    for i, law in enumerate(session.literature_raw, start=1):
        try:
            laws.append(fit_law(session, law, i))
        except Exception as e:  # one malformed published law must not sink the run
            logger.warning(f"Fitting published law {i} failed: {e}")
            laws.append(
                {
                    "equation": str(law.get("equation") or "").strip(),
                    "citations": [],
                    "model_id": None,
                    "cv_r2": None,
                    "unmapped": [],
                    "fit_error": f"fit failed: {str(e)[:150]}",
                }
            )
    session.known_laws = {"status": "ok", "laws": laws}
    return [law for law in laws if law["model_id"] and law["cv_r2"] is not None]


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
