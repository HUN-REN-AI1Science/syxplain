"""RELATE: known laws are fitted after the blind exploration and compared with the discoveries."""

import json

import numpy as np
import pandas as pd

from backend.services.discovery.relate import _Predictor, relate, relations, screen_named_laws
from backend.services.discovery.report import build_results
from backend.services.discovery.selection import Selection
from backend.services.discovery.session import DiscoverySession


def _session() -> DiscoverySession:
    """Michaelis-Menten in S plus a linear effect of z."""
    rng = np.random.default_rng(7)
    n = 400
    S = rng.uniform(0.5, 20, n)
    z = rng.uniform(0, 2, n)
    df = pd.DataFrame({"S": S, "z": z, "y": 10 * S / (3 + S) + 4 * z + rng.normal(0, 0.2, n)})
    s = DiscoverySession(df, "y", ["S", "z"])
    s.profile()
    return s


def _relation(s: DiscoverySession, discovered, law) -> dict:
    return relate(discovered, [law], _Predictor(s))[0]


def test_rewritten_law_is_equivalent():
    s = _session()
    # The law in another algebraic form, as PySR or the agent might write it
    found = s.fit_custom("k/(1 + h/S)", initial_params={"k": 10, "h": 3}, label="found")
    law = s.fit_family("michaelis_menten", ["S"])
    rel = _relation(s, found, law)
    assert rel["relation"] == "equivalent" and rel["agreement_r2"] > 0.99
    assert rel["comparison"] == "tied" and rel["shared_features"] == ["S"]


def test_law_on_part_of_the_variables_is_partial():
    s = _session()
    found = s.fit_custom("k*S/(h + S) + c*z", initial_params={"k": 10, "h": 3}, label="found")
    law = s.fit_family("michaelis_menten", ["S"])
    rel = _relation(s, found, law)
    assert rel["relation"] == "partial" and rel["shape_r2"] > 0.95
    assert rel["comparison"] == "worse"


def test_unrelated_law_is_different():
    s = _session()
    found = s.fit_custom("k*S/(h + S)", initial_params={"k": 10, "h": 3}, label="found")
    law = s.fit_family("linear", ["z"])  # a variable the discovered equation does not use
    assert _relation(s, found, law)["relation"] == "different"


def test_known_laws_are_fitted_after_exploration_on_the_discovered_features():
    s = _session()
    s.fit_custom("k*S/(h + S) + c*z", initial_params={"k": 10, "h": 3}, label="found")
    assert not any(m.kind == "classic" for m in s.models.values())
    assert screen_named_laws(s) > 0
    classic = [m for m in s.models.values() if m.kind == "classic"]
    assert {"S", "z"} <= {f for m in classic for f in m.features}


def test_headline_is_discovered_even_when_a_known_law_is_better():
    s = _session()
    found = s.fit_custom("k*S/(h + S)", initial_params={"k": 10, "h": 3}, label="misses z")
    law = s.fit_custom(
        "k*S/(h + S) + c*z",
        initial_params={"k": 10, "h": 3},
        label="Published law 1",
        kind="literature",
    )
    results = build_results(s, {"recommended_models": [{"model_id": law.model_id}]}, None)
    d = results["discovery"]
    assert d["selection"]["headline_model_id"] == found.model_id
    assert d["relations"]["headline"][0]["law_id"] == law.model_id
    lit = next(c for c in d["coherence"]["checks"] if c["key"] == "literature")
    assert lit["status"] == "warn" and lit["value"] == law.model_id
    assert any(e["model_id"] == law.model_id for e in results["equations"])  # a reference card
    json.dumps(results, allow_nan=False)


def test_known_law_is_the_fallback_headline():
    s = _session()
    law = s.fit_family("michaelis_menten", ["S"])
    results = build_results(s, None, "agent failed")
    selection = results["discovery"]["selection"]
    assert selection["headline_model_id"] == law.model_id
    assert selection["headline_is_reference"]


def test_relations_cover_the_shortlist_and_skip_known_headlines():
    s = _session()
    found = s.fit_custom("k*S/(h + S) + c*z", initial_params={"k": 10, "h": 3}, label="found")
    law = s.fit_family("michaelis_menten", ["S"])
    ranked = s.ranked_models()
    related = relations(s, Selection(found, "test", [found]), ranked)
    assert list(related) == [found.model_id]  # known laws are never related to themselves
    assert related[found.model_id][0]["law_id"] == law.model_id
    assert law.model_id not in relations(s, Selection(law, "test", [law]), ranked)
