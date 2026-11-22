"""
Coherence with the literature.

When the user supplies their own literature (papers, notes), a scout reads it and writes
down what it states about the target: which variables are not causes, where an equation
must be defined, the direction of an effect, what a quantity tends to in a limit. This
module maps those statements onto the data's variables and tests every fitted equation
against them numerically. The LLM only reads the text; whether an equation agrees with
a statement is computed here.

A constraint evaluates to ``agrees``, ``conflict``, ``silent`` (the equation does not
contain the variable the statement is about) or ``na`` (it could not be tested).
``selection.py`` recommends among the equations without a conflict first.
"""

import itertools
import logging
import re
from typing import Any

import numpy as np

from backend.services.discovery.expression import ExpressionError, parse_expression
from backend.services.discovery.fitting import ModelResult, predict
from backend.services.discovery.session import DiscoverySession

logger = logging.getLogger(__name__)

MAX_CONSTRAINTS = 30
# Points per axis that has a literature range, the axis under test, and the total
RANGE_GRID = 13
LEAD_GRID = 60
MAX_GRID_POINTS = 200_000
QUANTILES = (0.1, 0.5, 0.9)
# "Large" and "towards zero" for a limit, relative to the variable's scale in the data
# Realistic range: characteristic values of a variable (a fine sweep over the range of the
# data, plus the points halfway between neighbouring measured values), tried on a few
# measured rows; a result further than RANGE_MARGIN target spans outside the measured
# target, or beyond a bound of the context by more than BOUND_TOLERANCE spans, is unrealistic
SWEEP_POINTS = 1500
SWEEP_ROWS = 25
RANGE_MARGIN = 2.0
BOUND_TOLERANCE = 0.05
LIMIT_SCALES = {"large": (1e3, 1e6), "zero": (1e-3, 1e-6)}
EXPECTATIONS = ("finite_positive", "zero", "infinite")


def _map(name: Any, session: DiscoverySession) -> str | None:
    """A feature alias for a column name or alias the scout wrote, or None."""
    # Imported here: literature.py imports this module for the RELATE step.
    from backend.services.discovery.literature import _map_identifier

    alias = _map_identifier(str(name).strip(), session) if name else None
    return alias if alias and alias != session.target_alias else None


def _source(c: dict[str, Any]) -> str:
    return str(c.get("source") or c.get("note") or "").strip()[:200]


def normalize_constraints(
    session: DiscoverySession, raw: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    The scout's constraints with their variables mapped onto the data, and the ones
    that could not be used with the reason. Nothing the scout wrote is trusted: every
    name, range and expression is validated.
    """
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    def drop(c: Any, why: str) -> None:
        dropped.append({"constraint": c, "reason": why})

    for c in (raw if isinstance(raw, list) else [])[:MAX_CONSTRAINTS]:
        if not isinstance(c, dict):
            drop(c, "not an object")
            continue
        kind = str(c.get("type") or "")
        origin = "web" if c.get("origin") == "web" else "supplied"
        base = {
            "id": f"K{len(kept) + 1}",
            "type": kind,
            "source": _source(c),
            "reason": str(c.get("reason") or "").strip()[:400],
            "conditions": str(c.get("conditions") or "").strip()[:300],
            "origin": origin,
            # A statement of the web literature research decides the recommendation only
            # when it is valid in the context of this data; otherwise it only warns
            "binding": origin != "web" or str(c.get("applies") or "").lower() == "yes",
        }
        if kind == "defined_over":
            ranges = {}
            stated = c.get("ranges")
            for name, bounds in (stated if isinstance(stated, dict) else {}).items():
                alias = _map(name, session)
                try:
                    lo, hi = float(bounds[0]), float(bounds[1])
                except (TypeError, ValueError, IndexError, KeyError):
                    continue
                if alias and np.isfinite([lo, hi]).all() and lo < hi:
                    ranges[alias] = [lo, hi]
            if not ranges:
                drop(c, "no range for a variable of the data")
                continue
            kept.append(base | {"ranges": ranges, "text": "defined over the stated ranges"})
            continue
        alias = _map(c.get("variable"), session)
        if alias is None:
            drop(c, f"variable {c.get('variable')!r} is not a predictor of the data")
            continue
        if kind == "not_a_cause":
            kept.append(base | {"variable": alias, "text": f"{alias} is not a cause"})
        elif kind == "monotone":
            direction = str(c.get("direction") or "").lower()
            if direction[:4] not in ("incr", "decr"):
                drop(c, "direction is neither increasing nor decreasing")
                continue
            direction = "increasing" if direction.startswith("incr") else "decreasing"
            kept.append(
                base
                | {"variable": alias, "direction": direction, "text": f"{direction} in {alias}"}
            )
        elif kind == "limit":
            toward, expect = str(c.get("toward") or ""), str(c.get("expect") or "")
            if toward not in LIMIT_SCALES or expect not in EXPECTATIONS:
                drop(c, "unknown limit direction or expectation")
                continue
            quantity = _quantity(str(c.get("quantity") or "target"), session)
            if quantity is None:
                drop(c, "the quantity uses names that are not variables of the data")
                continue
            kept.append(
                base
                | {
                    "variable": alias,
                    "toward": toward,
                    "expect": expect,
                    "quantity": quantity,
                    "text": f"{quantity} is {expect.replace('_', ' ')} as {alias} "
                    f"{'becomes large' if toward == 'large' else 'goes to zero'}",
                }
            )
        else:
            drop(c, f"unknown constraint type {kind!r}")
    return kept, dropped


def _quantity(text: str, session: DiscoverySession) -> str | None:
    """The limit's quantity rewritten in aliases (the target as its alias), or None."""
    names = [*session.features, session.target_alias]
    try:
        raw = parse_expression(text, variables=[])
    except ExpressionError:
        return None
    out = text
    # Imported here: literature.py imports this module for the RELATE step.
    from backend.services.discovery.literature import _map_identifier

    for name in sorted(raw.parameters, key=len, reverse=True):
        # The target may be written as the word "target", as its column or as its alias
        # (the name the scout is given for it); every other name must be a predictor.
        alias = session.target_alias if name == "target" else _map_identifier(name, session)
        if alias is None:
            return None
        if alias != name:
            out = re.sub(rf"(?<![A-Za-z_0-9]){re.escape(name)}(?![A-Za-z_0-9])", alias, out)
    try:
        parse_expression(out, variables=names, parameters=[])
    except ExpressionError:
        return None
    return out


class LiteratureCoherence:
    """Evaluates the normalized constraints on fitted models (results are cached per model)."""

    def __init__(self, session: DiscoverySession, constraints: list[dict[str, Any]]):
        self.session = session
        self.constraints = constraints
        self.ranges: dict[str, tuple[float, float]] = {}
        for c in constraints:
            if c["type"] == "defined_over":
                self.ranges.update({k: (v[0], v[1]) for k, v in c["ranges"].items()})
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._level_cache: dict[str, np.ndarray] = {}
        self._by_id = {c["id"]: c for c in constraints}

    # -- grids ---------------------------------------------------------------------------

    def _levels(self, feature: str) -> np.ndarray:
        """Representative values of a feature the literature gives no range for."""
        if feature not in self._level_cache:
            x = np.asarray(self.session.fit_data.X[feature], dtype=float)
            if self.session.kinds.get(feature) == "categorical":
                values, counts = np.unique(x[np.isfinite(x)], return_counts=True)
                levels = values[np.argsort(-counts)][:1]
            else:
                levels = np.unique(np.quantile(x[np.isfinite(x)], QUANTILES))
            self._level_cache[feature] = levels
        return self._level_cache[feature]

    def _grid(
        self, features: list[str], ranges: dict[str, tuple[float, float]], lead: str | None = None
    ) -> dict[str, np.ndarray] | None:
        """
        Flattened mesh over ``features``: the literature's range where it gives one, a few
        data quantiles otherwise. ``lead`` is the first axis, finely spaced.
        """
        X = self.session.fit_data.X
        if any(f not in X for f in features):
            return None
        axes: dict[str, np.ndarray] = {}
        ranged = [f for f in features if f in ranges and f != lead]
        others = [f for f in features if f not in ranges and f != lead]
        fixed = {f: self._levels(f) for f in others}
        budget = MAX_GRID_POINTS / (LEAD_GRID if lead else 1)
        # Every axis multiplies the mesh: an axis without a range that no longer fits in
        # the budget (with three points left for each ranged axis) is held at its middle level.
        room = max(1.0, budget / 3.0 ** len(ranged))
        size = 1
        for f, values in fixed.items():
            if size * len(values) > room:
                fixed[f] = values[len(values) // 2 :][:1]
            size *= len(fixed[f])
        budget /= size
        n = RANGE_GRID
        if ranged:
            n = int(np.clip(budget ** (1 / len(ranged)), 3, RANGE_GRID))
        if lead is not None:
            x = np.asarray(X[lead], dtype=float)
            lo, hi = ranges.get(lead, (float(np.nanmin(x)), float(np.nanmax(x))))
            axes[lead] = np.linspace(lo, hi, LEAD_GRID)
        for f in ranged:
            axes[f] = np.linspace(*ranges[f], n)
        axes.update(fixed)
        mesh = np.meshgrid(*axes.values(), indexing="ij")
        return {f: g.ravel() for f, g in zip(axes, mesh, strict=True)}

    # -- single checks -------------------------------------------------------------------

    def _defined_over(self, m: ModelResult, c: dict[str, Any]) -> tuple[str, str]:
        ranges = {k: (v[0], v[1]) for k, v in c["ranges"].items()}
        if not set(ranges) & set(m.features):
            return "silent", "uses none of the variables the ranges are about"
        grid = self._grid(m.features, ranges)
        if grid is None:
            return "na", "not all variables are available"
        y = predict(m.parsed, m.params, grid, m.target_transform)
        bad = float(np.mean(~np.isfinite(y)))
        if bad:
            return "conflict", f"undefined on {bad:.1%} of the range the literature states"
        return "agrees", "defined over the stated range"

    def _realistic_range(self, m: ModelResult, c: dict[str, Any]) -> tuple[str, str]:
        """
        Characteristic values of each variable, inside the range of the data: does the
        equation give a number there, and does it stay in the realistic range of the target?
        """
        s = self.session
        X = {f: np.asarray(s.fit_data.X[f], dtype=float) for f in m.features}
        y = np.asarray(s.fit_data.y, dtype=float)
        y_lo, y_hi = float(np.nanmin(y)), float(np.nanmax(y))
        span = (y_hi - y_lo) or 1.0
        rows = np.unique(np.linspace(0, len(y) - 1, min(SWEEP_ROWS, len(y))).astype(int))
        low, high = c.get("low"), c.get("high")
        target = s.target_column
        for f in m.features:
            if s.kinds.get(f) == "categorical":
                continue
            x = X[f][np.isfinite(X[f])]
            lo, hi = float(x.min()), float(x.max())
            if lo == hi:
                continue
            measured = np.unique(x)
            sweep = np.unique(
                np.concatenate(
                    [np.linspace(lo, hi, SWEEP_POINTS), (measured[:-1] + measured[1:]) / 2]
                )
            )
            grid = {g: np.repeat(X[g][rows], len(sweep)) for g in m.features}
            grid[f] = np.tile(sweep, len(rows))
            out = predict(m.parsed, m.params, grid, m.target_transform)
            where = f"for {f} near {{:.4g}}, inside the range of the data ({lo:.4g} to {hi:.4g})"
            bad = ~np.isfinite(out)
            if bad.any():
                at = where.format(grid[f][np.argmax(bad)])
                return "conflict", f"gives no number {at}"
            far = (out < y_lo - RANGE_MARGIN * span) | (out > y_hi + RANGE_MARGIN * span)
            if far.any():
                i = int(np.argmax(np.where(far, np.abs(out - (y_lo + y_hi) / 2), -1.0)))
                return "conflict", (
                    f"gives {out[i]:.4g} {where.format(grid[f][i])}, while the measured "
                    f"{target} lies between {y_lo:.4g} and {y_hi:.4g}"
                )
            for bound, beyond, word in (
                (low, out < (low if low is not None else 0) - BOUND_TOLERANCE * span, "below"),
                (high, out > (high if high is not None else 0) + BOUND_TOLERANCE * span, "above"),
            ):
                if bound is not None and beyond.any():
                    i = int(np.argmax(np.where(beyond, np.abs(out - bound), -1.0)))
                    reason = f": {c['reason']}" if c.get("reason") else ""
                    return "conflict", (
                        f"gives {out[i]:.4g} {where.format(grid[f][i])}, {word} {bound:g}, "
                        f"the realistic limit of {target} in the context{reason}"
                    )
        return "agrees", "stays in the realistic range at the characteristic values"

    def _monotone(self, m: ModelResult, c: dict[str, Any]) -> tuple[str, str]:
        v = c["variable"]
        if v not in m.features:
            return "silent", f"does not use {v}"
        grid = self._grid(m.features, self.ranges, lead=v)
        if grid is None:
            return "na", "not all variables are available"
        y = predict(m.parsed, m.params, grid, m.target_transform).reshape(LEAD_GRID, -1)
        ok = np.isfinite(y).all(axis=0)
        if not ok.any():
            return "na", f"undefined along {v}"
        y = y[:, ok]
        steps = np.diff(y, axis=0)
        tol = 1e-9 * (float(np.abs(y).max()) + 1.0)
        wrong = steps < -tol if c["direction"] == "increasing" else steps > tol
        if wrong.any():
            share = float(wrong.any(axis=0).mean())
            return (
                "conflict",
                f"not {c['direction']} in {v} (reverses in {share:.0%} of the tested settings)",
            )
        return "agrees", f"{c['direction']} in {v}"

    def _limit(self, m: ModelResult, c: dict[str, Any]) -> tuple[str, str]:
        s, v = self.session, c["variable"]
        try:
            quantity = parse_expression(
                c["quantity"], variables=[*s.features, s.target_alias], parameters=[]
            )
        except ExpressionError:
            return "na", "the quantity could not be evaluated"
        if v not in m.features and v not in quantity.variables:
            return "silent", f"does not use {v}"
        X = s.fit_data.X
        needed = [
            f for f in dict.fromkeys([*m.features, *quantity.variables]) if f != s.target_alias
        ]
        if any(f not in X for f in needed):
            return "na", "not all variables are available"
        others = [f for f in needed if f != v]
        levels = [self._levels(f) if i < 5 else self._levels(f)[:1] for i, f in enumerate(others)]
        # One row per setting of the other variables; a single empty row when there are none
        settings = list(itertools.product(*levels))
        combos = np.array(settings, dtype=float).reshape(len(settings), len(others))
        x = np.abs(np.asarray(X[v], dtype=float))
        scale = float(np.nanmax(x)) if c["toward"] == "large" else float(np.nanmedian(x))
        scale = scale if np.isfinite(scale) and scale > 0 else 1.0
        values = []
        for factor in LIMIT_SCALES[c["toward"]]:
            cols = {f: combos[:, i].copy() for i, f in enumerate(others)}
            cols[v] = np.full(len(combos), scale * factor)
            cols[s.target_alias] = predict(
                m.parsed, m.params, {f: cols[f] for f in m.features}, m.target_transform
            )
            values.append(quantity.evaluate(cols, {}))
        near, far = values
        observed = {f: np.asarray(X[f], dtype=float) for f in quantity.variables if f in X}
        observed[s.target_alias] = np.asarray(s.fit_data.y, dtype=float)
        ref = float(np.nanmedian(np.abs(quantity.evaluate(observed, {})))) or 1.0
        finite = bool(np.isfinite(near).all() and np.isfinite(far).all())
        with np.errstate(all="ignore"):
            if c["expect"] == "finite_positive":
                ok = (
                    finite
                    and bool((far > 1e-3 * ref).all())
                    and bool((np.abs(far / near - 1) < 0.05).all())
                )
            elif c["expect"] == "zero":
                ok = finite and bool((np.abs(far) < 1e-3 * ref).all())
            else:
                ok = (not finite) or bool((np.abs(far) > 100 * np.abs(near)).all())
        return ("agrees", c["text"]) if ok else ("conflict", f"not true that {c['text']}")

    # -- all checks of a model -----------------------------------------------------------

    def evaluate(self, m: ModelResult) -> list[dict[str, Any]]:
        """Status of every constraint for ``m`` ([] for models that cannot be tested)."""
        if m.model_id in self._cache:
            return self._cache[m.model_id]
        out: list[dict[str, Any]] = []
        if m.parsed is not None and not m.error and m.problem == "static":
            for c in self.constraints:
                try:
                    if c["type"] == "not_a_cause":
                        used = c["variable"] in m.features
                        status, detail = (
                            (
                                "conflict",
                                f"uses {c['variable']}, which the literature says is not a cause",
                            )
                            if used
                            else ("agrees", f"does not use {c['variable']}")
                        )
                    elif c["type"] == "realistic_range":
                        status, detail = self._realistic_range(m, c)
                    elif c["type"] == "defined_over":
                        status, detail = self._defined_over(m, c)
                    elif c["type"] == "monotone":
                        status, detail = self._monotone(m, c)
                    else:
                        status, detail = self._limit(m, c)
                except Exception as e:  # one odd constraint must not sink the selection
                    logger.warning(f"Constraint {c['id']} failed on {m.model_id}: {e}")
                    status, detail = "na", "could not be tested"
                out.append({"id": c["id"], "status": status, "detail": detail})
        self._cache[m.model_id] = out
        return out

    def conflicts(self, m: ModelResult, binding: bool = True) -> list[str]:
        """
        Readable conflicts of ``m`` with the literature ([] = coherent). ``binding=False``
        gives the conflicts with web statements whose validity in this context is unknown:
        they warn, and never remove an equation from the choice.
        """
        by_id = self._by_id
        return [
            r["detail"] + (f" ({by_id[r['id']]['source']})" if by_id[r["id"]]["source"] else "")
            for r in self.evaluate(m)
            if r["status"] == "conflict" and by_id[r["id"]].get("binding", True) == binding
        ]


def realistic_range_constraint(session: DiscoverySession) -> dict[str, Any]:
    """
    The statement the context always makes: at characteristic values inside the range of
    the data, an equation gives a realistic value of the target. The limits of the target
    come from the reading of the scientific context (``session.context_ranges``), when
    there is one; the range of the data needs no reading.
    """
    stated = session.context_ranges if isinstance(session.context_ranges, dict) else {}

    def bound(key: str) -> float | None:
        try:
            value = float(stated.get(key))
        except (TypeError, ValueError):
            return None
        return value if np.isfinite(value) else None

    low, high = bound("low"), bound("high")
    if low is not None and high is not None and low >= high:
        low = high = None
    y = np.asarray(session.fit_data.y, dtype=float)
    # a limit the measured target itself breaks is not a limit of this context
    if low is not None and np.nanmin(y) < low:
        low = None
    if high is not None and np.nanmax(y) > high:
        high = None
    return {
        "id": "K0",
        "type": "realistic_range",
        "source": "the context",
        "reason": str(stated.get("reason") or "").strip()[:300],
        "conditions": "",
        "origin": "context",
        "binding": True,
        "low": low,
        "high": high,
        "text": "realistic values of the target inside the range of the data",
    }


def build(session: DiscoverySession) -> LiteratureCoherence:
    """The evaluator for the statements of the context and of the literature."""
    constraints = [realistic_range_constraint(session), *(session.literature_constraints or [])]
    return LiteratureCoherence(session, constraints)
