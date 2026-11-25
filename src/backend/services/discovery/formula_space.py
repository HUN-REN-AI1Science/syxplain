"""
The formula space of the data: the literature's relationships, measured against the data.

A dataset holds several relationships at once. Over the symbols a, v, s, t the
literature may state ``v = a*t`` (over v, a, t) and ``v = s/t`` (over v, s, t): each is
a relationship over a subset of the symbols, and the equation for the target is only
one of them. The scout's relationships that are not about the target are measured here
on the data, as published and with their constants fitted again. A relationship that
holds says the literature describes the context of the data; one that does not is a
hint that the context differs, and the literature's own conditions are shown with it.

The same question is put to the literature's statements: ``statement_checks`` asks the
data whether a variable the literature calls "not a cause" explains what the coherent
recommendation leaves unexplained. The answer labels the better-fitting expression that
conflicts with the literature as a possible paradigm shift (the data speaks against the
statement) or a wrong relationship (it does not). It never changes the recommendation.
"""

import logging
import re
from typing import Any

import numpy as np
from scipy import stats

from backend.services.discovery.expression import (
    ExpressionError,
    parameterize_constants,
    parse_expression,
    substitute_parameters,
)
from backend.services.discovery.fitting import (
    ModelResult,
    _least_squares,
    binned_dependence,
    r2_score,
)
from backend.services.discovery.session import DiscoverySession

logger = logging.getLogger(__name__)

MAX_RELATIONS = 12
HOLDS_R2 = 0.9  # the relationship reproduces the measured variable
PARTLY_R2 = 0.5
# Share of the recommendation's residual variance a "not a cause" variable must explain
# for the data to speak against the statement
CONTRADICTED_SHARE = 0.5

# A relationship that explains part of its variable (R2 above PARTIAL_MIN_R2) while another
# variable of the data explains this share of what it leaves: stated for the other
# variables held fixed, so the data cannot test it alone
PARTIAL_MIN_R2 = 0.1
LEFT_OUT_SHARE = 0.3

STATUS_TEXT = {
    "not_testable_alone": "cannot be tested alone on the data",
    "holds": "holds in the data as published",
    "holds_in_form": "holds in the data in form, with other constants than published",
    "partly": "holds only partly in the data",
    "does_not_hold": "does not hold in the data",
}


def _columns(session: DiscoverySession, frame) -> dict[str, np.ndarray]:
    names = [*session.features, session.target_alias]
    return {n: frame[n].to_numpy(dtype=float) for n in names if n in frame}


def _score(expr, X: dict[str, np.ndarray], y: np.ndarray, params: dict[str, float]):
    pred = expr.evaluate(X, params)
    ok = np.isfinite(pred) & np.isfinite(y)
    if ok.sum() < max(5, 0.8 * len(y)):
        return None
    return float(r2_score(y[ok], pred[ok]))


def _left_out(
    expr, X: dict[str, np.ndarray], y: np.ndarray, params: dict[str, float], left: str
) -> dict[str, float]:
    """
    Variables of the data that the relationship does not use and that explain a large
    share of what it leaves unexplained: the sign of a relationship stated for the other
    variables held fixed (rate against one setting, while another setting also varies).
    """
    resid = y - expr.evaluate(X, params)
    ok = np.isfinite(resid)
    out: dict[str, float] = {}
    if ok.sum() < 30 or np.var(resid[ok]) == 0:
        return out
    for name, x in X.items():
        if name == left or name in expr.variables or np.ptp(x[ok]) == 0:
            continue
        dep = binned_dependence(resid[ok], x[ok])
        rho = stats.spearmanr(resid[ok], x[ok]).statistic
        share = max(dep[0] if dep else 0.0, float(rho) ** 2 if np.isfinite(rho) else 0.0)
        if share >= LEFT_OUT_SHARE:
            out[name] = round(share, 3)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def is_other_relation(session: DiscoverySession, equation: str) -> bool:
    """True when the equation's left side is a variable of the data other than the target."""
    # Imported here: literature.py imports this module for the RELATE step.
    from backend.services.discovery.literature import _map_identifier

    lhs, sep, _ = str(equation or "").partition("=")
    alias = _map_identifier(lhs.strip(), session) if sep and lhs.strip() else None
    return bool(alias) and alias != session.target_alias


def measure_relation(session: DiscoverySession, raw: dict[str, Any]) -> dict[str, Any]:
    """One relationship of the literature among the data's variables, measured on the data."""
    from backend.services.discovery.literature import _looks_like_parameter, _map_identifier

    text = str(raw.get("equation") or "").strip()
    record: dict[str, Any] = {
        "equation": text,
        "source": str(raw.get("source") or "; ".join(map(str, raw.get("citations") or [])))[:200],
        "conditions": str(raw.get("conditions") or "").strip()[:300],
        "variable": None,
        "variables": [],
        "fitted_equation": None,
        "r2_published": None,
        "r2_refitted": None,
        "status": "na",
        "left_out": {},
        "error": None,
    }
    lhs, sep, rhs = text.partition("=")
    left = _map_identifier(lhs.strip(), session) if sep and lhs.strip() else None
    if not left:
        record["error"] = "the left side is not a variable of the data"
        return record
    record["variable"] = left
    try:
        raw_expr = parse_expression(rhs, variables=[])
    except ExpressionError as e:
        record["error"] = f"could not parse: {e}"
        return record

    renames: dict[str, str] = {}
    free: list[str] = []
    unmapped: list[str] = []
    for name in raw_expr.parameters:
        alias = _map_identifier(name, session)
        if alias:
            renames[name] = alias
        elif _looks_like_parameter(name):
            free.append(name)
        else:
            unmapped.append(name)
    if unmapped:
        record["error"] = f"variables not in the data: {unmapped}"
        return record
    if not renames:
        record["error"] = "uses none of the data's variables"
        return record
    if left in renames.values():
        record["error"] = "the variable is on both sides"
        return record

    expression = rhs
    for name, alias in sorted(renames.items(), key=lambda kv: -len(kv[0])):
        expression = re.sub(
            rf"(?<![A-Za-z_0-9]){re.escape(name)}(?![A-Za-z_0-9])", alias, expression
        )
    columns = [*session.features, session.target_alias]
    template, published = parameterize_constants(expression, taken=[*columns, *free])
    try:
        expr = parse_expression(template, columns)
    except ExpressionError as e:
        record["error"] = f"could not parse: {e}"
        return record
    record["variables"] = list(expr.variables)

    train = _columns(session, session.train)
    held = _columns(session, session.holdout) if session.has_holdout else train
    y_train, y_held = train[left], held[left]
    if np.ptp(y_train) == 0:
        record["error"] = f"{left} does not vary in the data"
        return record

    # As published: only when the literature gives every constant
    if not free:
        record["r2_published"] = _score(expr, held, y_held, published)
    # Constants fitted again on the training rows, scored on the held-out rows
    names = expr.parameters
    best_params = dict(published)
    if names:
        p0 = np.array([published.get(n, 1.0) for n in names], dtype=float)
        fit = _least_squares(expr, train, y_train, p0, np.full(len(names), -np.inf), 2000)
        if fit is not None:
            params = dict(zip(names, map(float, fit[0]), strict=True))
            record["r2_refitted"] = _score(expr, held, y_held, params)
            best_params = params
            record["fitted_equation"] = f"{left} = {substitute_parameters(template, params)}"
    else:
        record["r2_refitted"] = record["r2_published"]

    pub, refit = record["r2_published"], record["r2_refitted"]
    best = max((v for v in (pub, refit) if v is not None), default=None)
    if best is None:
        record["error"] = "undefined on the data"
    elif pub is not None and pub >= HOLDS_R2:
        record["status"] = "holds"
    elif refit is not None and refit >= HOLDS_R2:
        record["status"] = "holds_in_form"
    elif best >= PARTLY_R2:
        record["status"] = "partly"
    else:
        record["status"] = "does_not_hold"
    if record["status"] in ("partly", "does_not_hold") and best is not None:
        record["left_out"] = _left_out(expr, train, y_train, best_params, left)
        if best >= PARTIAL_MIN_R2 and record["left_out"]:
            record["status"] = "not_testable_alone"
    for key in ("r2_published", "r2_refitted"):
        if record[key] is not None:
            record[key] = round(record[key], 4)
    return record


def measure_relations(session: DiscoverySession, raw: list[Any]) -> list[dict[str, Any]]:
    """Every relationship the scout returned, measured; one bad entry never sinks the rest."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = re.sub(r"\s+", "", str(item.get("equation") or ""))
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            out.append(measure_relation(session, item))
        except Exception as e:
            logger.warning(f"Measuring a literature relationship failed: {e}")
        if len(out) >= MAX_RELATIONS:
            break
    return out


def statement_checks(
    session: DiscoverySession, headline: ModelResult, challenger: ModelResult | None
) -> list[dict[str, Any]]:
    """
    The literature's "not a cause" statements, tested on the data through the
    recommendation: does the variable explain what the recommendation leaves unexplained?
    Only statements the recommendation itself respects can be tested this way.
    """
    missing = (headline.diagnostics or {}).get("missing_variables") or {}
    out = []
    for c in session.literature_constraints or []:
        if c.get("type") != "not_a_cause" or c.get("variable") in headline.features:
            continue
        variable = c["variable"]
        share = float(missing.get(variable) or 0.0)
        out.append(
            {
                "variable": variable,
                "source": c.get("source") or "",
                "conditions": c.get("conditions") or "",
                "residual_share": round(share, 3),
                "data": "contradicts" if share >= CONTRADICTED_SHARE else "does_not_contradict",
                "used_by_challenger": bool(challenger and variable in challenger.features),
            }
        )
    return out


def challenger_reading(checks: list[dict[str, Any]]) -> str | None:
    """
    How the data reads the better-fitting expression that conflicts with the literature:
    "paradigm_shift" when the data speaks against a statement it breaks, otherwise
    "wrong_relationship". A hint for the user's judgement, never a decision.
    """
    used = [c for c in checks if c["used_by_challenger"]]
    if not used:
        return None  # it breaks statements the data cannot be asked about this way
    if any(c["data"] == "contradicts" for c in used):
        return "paradigm_shift"
    return "wrong_relationship"
