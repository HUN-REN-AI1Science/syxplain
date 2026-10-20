"""SHAP plots, SHAP-seeded PySR searches and the equation-vs-SHAP agreement check."""

import asyncio
import base64

import numpy as np
import pandas as pd

from backend.services.discovery.session import DiscoverySession
from backend.tests.test_discovery_session import FakeLauncher

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _interaction_session(launcher=None) -> DiscoverySession:
    rng = np.random.default_rng(0)
    n = 600
    x1, x2, x3 = rng.uniform(1, 3, n), rng.uniform(1, 3, n), rng.uniform(0, 2, n)
    y = 3 * x1 * x2 + np.exp(x3) + rng.normal(0, 0.3, n)
    df = pd.DataFrame({"x1": x1, "x2": x2, "x3": x3, "noise": rng.normal(0, 1, n), "y": y})
    s = DiscoverySession(df, "y", ["x1", "x2", "x3", "noise"], launcher=launcher)
    s.profile()
    return s


def test_plots_rendered_as_png_for_reliable_shap():
    s = _interaction_session()
    kinds = [p["kind"] for p in s.shap_plots]
    assert kinds[0] == "summary" and "dependence" in kinds
    assert len(s.shap_plots) <= 5
    for p in s.shap_plots:
        assert base64.b64decode(p["b64"]).startswith(PNG_MAGIC)
        assert p["name"].startswith("shap_") and p["name"].endswith(".png")
    assert "noise" not in {p["feature"] for p in s.shap_plots}


def test_pure_noise_gives_no_plots_and_no_seeds():
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"x1": rng.normal(size=300), "x2": rng.normal(size=300)})
    df["y"] = rng.normal(size=300)
    s = DiscoverySession(df, "y", ["x1", "x2"])
    s.profile()
    assert s.shap_plots == []
    assert s.shap_seed_guesses(["x1", "x2"], None, [], ["+", "*", "/"]) == []


def test_interaction_seeds_the_search_when_the_agent_gives_none():
    launcher = FakeLauncher()

    async def scenario():
        s = _interaction_session(launcher)
        pairs = {frozenset((d["a"], d["b"])) for d in s._profile["shap"]["interactions"]}
        assert frozenset(("x1", "x2")) in pairs
        rec = await s.start_search(
            features=["x1", "x2", "x3"],
            unary_operators=["exp"],
            binary_operators=["+", "-", "*", "/"],
        )
        seeded = await s.start_search(
            features=["x1", "x2", "x3"],
            unary_operators=["exp"],
            binary_operators=["+", "*"],
            guesses=["x1 + x2"],
        )
        await asyncio.gather(rec.task, seeded.task)
        return rec, seeded

    rec, seeded = asyncio.run(scenario())
    assert rec.seeded_from_shap and rec.guesses
    assert any("x1*x2" in g for g in rec.guesses)
    # The constants are fitted: 3*x1*x2 dominates, so the slope is near 3.
    product = next(g for g in rec.guesses if "*x1*x2" in g)
    slope = float(product.split("*")[0].split()[-1])
    assert 2.0 < slope < 4.0
    # The agent's own guesses win.
    assert seeded.guesses == ["x1 + x2"] and not seeded.seeded_from_shap
    assert launcher.submitted[0][1]["guesses"] == rec.guesses


def test_weak_features_flagged():
    s = _interaction_session()
    assert "noise" in s.weak_features(["x1", "x2", "noise"])
    assert "x1" not in s.weak_features(["x1", "x2", "noise"])


def test_agreement_flags_an_equation_that_misses_a_feature():
    s = _interaction_session()
    good = s.fit_custom("k*x1*x2 + exp(x3) + m", label="right form")
    wrong = s.fit_custom("k*x1*x2 + m", label="misses x3")
    flipped = s.fit_custom("k*x1*x2 - exp(x3) + m", label="wrong sign")
    good_v = {d["feature"]: d["verdict"] for d in s.shap_agreement(good)}
    assert good_v["x1"] == good_v["x2"] == good_v["x3"] == "agrees"
    assert {d["feature"]: d["verdict"] for d in s.shap_agreement(wrong)}["x3"] == "ignored"
    # A fitted 'wrong sign' term flips its constant; force the sign to test the check.
    flipped.params = {k: abs(v) for k, v in flipped.params.items()}
    assert {d["feature"]: d["verdict"] for d in s.shap_agreement(flipped)}["x3"] == "opposite"
    assert s.shap_agreement(None) == []
