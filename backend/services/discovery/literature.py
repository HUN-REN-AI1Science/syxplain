"""
Literature scout: published laws, found by web search (or read from the literature the
user supplied) and fitted to the data.

The scout runs once, in the background, from the start of the run (it is slow: a
web-searching research model). Its laws are parsed, their variables mapped onto
the data's aliases, and every law that predicts the target is fitted like any
other model (ids L<n>, published constants as starting values). The agent never sees
them: they are fitted after exploration and compared with what it discovered
(``relate.py``); the explanation step gets the citations. Nothing here ever calls the
research model twice.

When the user supplies their own literature, the scout reads only that text, with no web
search, and also returns constraints (``literature_coherence.py``) that the selection
uses: the recommended equation is then chosen among those coherent with the literature.
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
from backend.services.discovery.formula_space import is_other_relation, measure_relations
from backend.services.discovery.literature_coherence import normalize_constraints
from backend.services.discovery.session import DiscoverySession

logger = logging.getLogger(__name__)

MAX_LAWS = 12
MAX_COMPOSED = 4

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
        "origin": law.get("origin"),
        "composed_from": law.get("composed_from"),
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
            label=f"Composed law {index}" if law.get("composed_from") else f"Published law {index}",
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


def merged_lookup(
    lookups: dict[str, Callable[[], Awaitable[dict[str, Any]]]],
) -> Callable[[], Awaitable[dict[str, Any]]]:
    """
    One lookup for both kinds of literature research ("supplied" and "web"), run side by
    side. Every equation, statement and relationship is marked with its origin; the
    supplied literature comes first. One kind failing does not lose the other.
    """

    async def lookup() -> dict[str, Any]:
        order = [k for k in ("supplied", "web") if k in lookups]
        results = await asyncio.gather(*(lookups[k]() for k in order), return_exceptions=True)
        merged: dict[str, Any] = {"equations": [], "constraints": [], "relations": []}
        errors, used = [], []
        for origin, result in zip(order, results, strict=True):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException):
                logger.warning(f"Literature research ({origin}) failed: {result}")
                errors.append(f"{origin}: {str(result)[:150]}")
                continue
            used.append(origin)
            for key in ("equations", "constraints", "relations"):
                items = (result or {}).get(key)
                for item in items if isinstance(items, list) else []:
                    if isinstance(item, dict):
                        merged[key].append(item | {"origin": origin})
            if (result or {}).get("_parse_error"):
                errors.append(f"{origin}: {result['_parse_error']}")
        if not used:
            raise RuntimeError("; ".join(errors) or "no literature research ran")
        merged["source"] = "both" if len(used) == 2 else used[0]
        if errors:
            merged["_parse_error"] = "; ".join(errors)
        return merged

    return lookup


def compose_laws(session: DiscoverySession, relations: list[dict[str, Any]]) -> list[dict]:
    """
    Laws for the target implied by the literature: a relationship that holds in the data
    (``v = a*t``) is put into a law for the target that uses its left variable
    (``s = v*t`` gives ``s = (a*t)*t``). One step only, and only what both state.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for law in session.literature_raw or []:
        text = str(law.get("equation") or "") if isinstance(law, dict) else ""
        lhs, sep, rhs = text.partition("=")
        rhs = rhs.strip()
        if not sep or _map_identifier(lhs.strip(), session) != session.target_alias:
            continue
        for rel in relations:
            if rel.get("status") not in ("holds", "holds_in_form"):
                continue
            name, _, body = str(rel.get("equation") or "").partition("=")
            name, body = name.strip(), body.strip()
            pattern = rf"(?<![A-Za-z_0-9]){re.escape(name)}(?![A-Za-z_0-9])"
            if not name or not body or not re.search(pattern, rhs):
                continue
            # the relationship's free parameters must not collide with the law's
            try:
                names = parse_expression(body, variables=[]).parameters
            except ExpressionError:
                continue
            free = [n for n in names if _map_identifier(n, session) is None]
            for i, n in enumerate(sorted(free, key=len, reverse=True), start=1):
                body = re.sub(rf"(?<![A-Za-z_0-9]){re.escape(n)}(?![A-Za-z_0-9])", f"q{i}", body)
            composed = f"{lhs.strip()} = " + re.sub(pattern, lambda _m, b=body: f"({b})", rhs)
            key = re.sub(r"\s+", "", composed)
            if key in seen or len(out) >= MAX_COMPOSED:
                continue
            seen.add(key)
            out.append(
                {
                    "equation": composed,
                    "citations": [str(c) for c in law.get("citations") or []],
                    "citation_titles": list(law.get("citation_titles") or []),
                    "origin": law.get("origin"),
                    "composed_from": [text.strip(), str(rel.get("equation") or "").strip()],
                }
            )
    return out


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
        constraints = (result or {}).get("constraints")
        if isinstance(constraints, list) and constraints:
            session.literature_constraints_raw = constraints
        relations = (result or {}).get("relations")
        if isinstance(relations, list) and relations:
            session.literature_relations_raw = relations
        if (result or {}).get("source") in ("supplied", "both"):
            session.literature_source = result["source"]
        if not raw and session.literature_constraints_raw:
            session.literature_raw = []  # statements about the target, but no equation for it
            await session.emit(
                "literature",
                f"Literature: {len(constraints)} statements about the target; the "
                "recommendation is chosen among the equations coherent with them",
            )
            return
        if not raw and session.literature_relations_raw:
            session.literature_raw = []  # relationships among the other variables only
            await session.emit(
                "literature",
                f"Literature: {len(relations)} relationships among the other variables; they "
                "are measured against the data at the end",
            )
            return
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
            "discovered equations at the end"
            + (
                f", and {len(constraints)} statements about the target decide which "
                "equations are coherent with the literature"
                if session.literature_constraints_raw
                else ""
            ),
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
    session.known_laws = {"status": "ok", "laws": laws, "source": session.literature_source}
    if session.literature_constraints_raw:
        try:
            kept, dropped = normalize_constraints(session, session.literature_constraints_raw)
        except Exception as e:  # the scout's text must never sink the run
            logger.warning(f"Reading the literature constraints failed: {e}")
            kept, dropped = [], []
        session.literature_constraints = kept or None
        session.known_laws["constraints"] = kept
        session.known_laws["dropped_constraints"] = dropped[:20]
    # The formula space: every relationship of the literature that is not about the target
    # is measured against the data too
    others = [
        law
        for law in session.literature_raw
        if isinstance(law, dict) and is_other_relation(session, law.get("equation"))
    ]
    try:
        relations = measure_relations(session, [*(session.literature_relations_raw or []), *others])
    except Exception as e:  # the scout's text must never sink the run
        logger.warning(f"Measuring the literature's relationships failed: {e}")
        relations = []
    if relations:
        session.known_laws["relations"] = relations
        for i, law in enumerate(compose_laws(session, relations), start=len(laws) + 1):
            try:
                laws.append(fit_law(session, law, i))
            except Exception as e:
                logger.warning(f"Fitting a composed law failed: {e}")
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
