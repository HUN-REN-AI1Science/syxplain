"""
Relation of the discovered equations to known laws (the RELATE step).

Exploration is blind to existing knowledge: the agent never sees the classic catalog
or the literature, so its equations come from the data alone. Afterwards the catalog
is screened on the variables the discoveries use (``screen_named_laws``) and the
published laws are fitted (``literature.fit_literature_laws``), and ``relations``
decides in code how each discovered equation relates to each known law. Known laws
are references; the headline is chosen among the discovered equations (``report.py``).

Relations, from the predictions of both models on the fit data:
- equivalent: the same variables and agreement R2 >= EQUIVALENT_R2 (the law in another
  algebraic form, e.g. a PySR ``x/(c + x)`` that is Michaelis-Menten),
- similar: agreement R2 >= SIMILAR_R2,
- partial: the law uses a subset of the variables and has the shape of the discovered
  equation along them, the other variables held at a typical value (median, or the most
  common level of a category; unlike ``DiscoverySession.partial_dependence``, which
  averages over background rows, this keeps one prediction per row to correlate),
- different: none of these.
"""

from itertools import chain
from typing import Any

import numpy as np

from backend.services.discovery.fitting import ModelResult, predict, r2_score
from backend.services.discovery.selection import Selection, usable
from backend.services.discovery.session import DiscoverySession

KNOWN_KINDS = ("classic", "literature")
EQUIVALENT_R2 = 0.99
SIMILAR_R2 = 0.9
MIN_ROWS = 10
MAX_DISCOVERED = 6  # discovered equations related to the known laws
MAX_SCREENED_FEATURES = 5

RELATION_ORDER = {"equivalent": 0, "similar": 1, "partial": 2, "different": 3}


def is_known(m: ModelResult) -> bool:
    return m.kind in KNOWN_KINDS


def screen_named_laws(session: DiscoverySession) -> int:
    """Screen the classic catalog on the variables the discovered equations use."""
    used: list[str] = []
    for m in usable([m for m in session.ranked_models() if not is_known(m)])[:MAX_DISCOVERED]:
        used += [f for f in m.features if f not in used]
    continuous = [f for f in used if session.kinds.get(f) != "categorical"]
    # Without a usable discovery, fall back to the most important features.
    n = min(len(continuous), MAX_SCREENED_FEATURES) or 3
    return session.auto_screen(n_univariate=n, priority=used)


def _predictions(m: ModelResult, X: dict[str, np.ndarray]) -> np.ndarray | None:
    return None if m.parsed is None else predict(m.parsed, m.params, X, m.target_transform)


def _agreement(ref: np.ndarray, other: np.ndarray) -> float | None:
    """R2 of ``other`` as a prediction of ``ref`` (no rescaling)."""
    ok = np.isfinite(ref) & np.isfinite(other)
    return r2_score(ref[ok], other[ok]) if ok.sum() >= MIN_ROWS else None


def _shape_r2(a: np.ndarray, b: np.ndarray) -> float | None:
    """Squared correlation: the same shape up to scale and offset."""
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < MIN_ROWS or np.ptp(a[ok]) == 0 or np.ptp(b[ok]) == 0:
        return None
    return float(np.corrcoef(a[ok], b[ok])[0, 1] ** 2)


def _typical(session: DiscoverySession) -> dict[str, float]:
    """Median of each continuous feature, most common level of each category."""
    out = {}
    for f, v in session.fit_data.X.items():
        if session.kinds.get(f) == "categorical":
            levels, counts = np.unique(v, return_counts=True)
            out[f] = float(levels[np.argmax(counts)])
        else:
            out[f] = float(np.median(v))
    return out


def _comparison(d: ModelResult, k: ModelResult) -> str:
    """Accuracy of the law against the discovered equation: better / tied / worse (1-SE)."""
    if k.cv_rmse + (k.cv_se or 0.0) < d.cv_rmse:
        return "better"
    if d.cv_rmse + (d.cv_se or 0.0) < k.cv_rmse:
        return "worse"
    return "tied"


class _Predictor:
    """Predictions on the fit data, computed once per model (and per held-feature set)."""

    def __init__(self, session: DiscoverySession):
        self.X = session.fit_data.X
        self.typical = _typical(session)
        self._full: dict[str, np.ndarray | None] = {}
        self._held: dict[tuple[str, frozenset[str]], np.ndarray | None] = {}

    def full(self, m: ModelResult) -> np.ndarray | None:
        if m.model_id not in self._full:
            self._full[m.model_id] = _predictions(m, self.X)
        return self._full[m.model_id]

    def held(self, m: ModelResult, keep: frozenset[str]) -> np.ndarray | None:
        """``m``'s predictions with every feature outside ``keep`` at its typical value."""
        key = (m.model_id, keep)
        if key not in self._held:
            X = {f: v if f in keep else np.full(len(v), self.typical[f]) for f, v in self.X.items()}
            self._held[key] = _predictions(m, X)
        return self._held[key]


def relate(d: ModelResult, known: list[ModelResult], pred: _Predictor) -> list[dict[str, Any]]:
    """Every known law's relation to the discovered equation ``d``, closest first."""
    ref = pred.full(d)
    out = []
    for k in known:
        pk = pred.full(k)
        agree = _agreement(ref, pk) if ref is not None and pk is not None else None
        d_vars, k_vars = set(d.features), frozenset(k.features)
        entry: dict[str, Any] = {
            "law_id": k.model_id,
            "kind": k.kind,
            "label": k.label,
            "equation": k.fitted_expression,
            "features": k.features,
            "shared_features": sorted(d_vars & k_vars),
            "complexity": k.complexity,
            "cv_r2": k.cv_r2,
            "comparison": _comparison(d, k),
            "agreement_r2": agree,
        }
        relation = "different"
        if agree is not None and agree >= EQUIVALENT_R2 and d_vars == k_vars:
            relation = "equivalent"
        elif agree is not None and agree >= SIMILAR_R2:
            relation = "similar"
        elif k_vars and k_vars < d_vars and pk is not None:
            held = pred.held(d, k_vars)
            shape = _shape_r2(held, pk) if held is not None else None
            entry["shape_r2"] = shape
            if shape is not None and shape >= SIMILAR_R2:
                relation = "partial"
        entry["relation"] = relation
        out.append(entry)
    out.sort(
        key=lambda r: (
            RELATION_ORDER[r["relation"]],
            -(r["agreement_r2"] if r["agreement_r2"] is not None else -np.inf),
        )
    )
    return out


def relations(
    session: DiscoverySession, selection: Selection, ranked: list[ModelResult]
) -> dict[str, list[dict[str, Any]]]:
    """
    Every usable known law's relation to each discovered equation of interest (the
    headline's shortlist, the symbolic Pareto front, then the best by CV), keyed by
    model id. Callers truncate for display.
    """
    pool = usable(ranked)
    known = [m for m in pool if is_known(m)]
    discovered = [m for m in pool if not is_known(m)]
    symbolic = session.pareto([m for m in discovered if m.kind == "symbolic"])
    interest: dict[str, ModelResult] = {}
    for m in chain(selection.shortlist, symbolic, discovered):
        if len(interest) == MAX_DISCOVERED:
            break
        if not is_known(m):
            interest.setdefault(m.model_id, m)
    pred = _Predictor(session)
    return {mid: relate(m, known, pred) for mid, m in interest.items()}
