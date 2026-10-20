"""Coherence checks: do the noise ceiling, holdout, SHAP and published laws agree on the headline?"""

import json

import numpy as np
import pandas as pd

from backend.services.discovery.coherence import coherence_report
from backend.services.discovery.profiling import profile_shape
from backend.services.discovery.report import json_safe
from backend.services.discovery.selection import Selection
from backend.services.discovery.session import DiscoverySession
from backend.tests.test_discovery_shap import _interaction_session


def _report(s: DiscoverySession, headline, agent=None):
    s.final_scoring()
    ranked = s.ranked_models()
    threshold = headline.cv_rmse + headline.cv_se
    selection = Selection(headline, "test", tie_threshold=threshold)
    return coherence_report(s, selection, ranked, s.shap_agreement(headline), agent or {})


def _checks(report) -> dict[str, str]:
    return {c["key"]: c["status"] for c in report["checks"]}


def test_right_form_is_coherent():
    s = _interaction_session()
    good = s.fit_custom("k*x1*x2 + c*exp(x3)", label="right form")
    report = _report(s, good, {"recommended_models": [{"model_id": good.model_id}]})
    checks = _checks(report)
    for key in ("fit_vs_ceiling", "generalization", "shap", "parameters", "agent"):
        assert checks[key] == "pass", report["checks"]
    assert checks["literature"] == checks["named_laws"] == "na"
    assert report["overall"] == "pass"
    directions = {d["feature"]: d["shape"] for d in report["effect_directions"]}
    assert set(directions) == {"x1", "x2", "x3"}
    assert all("increasing" in shape for shape in directions.values())
    assert json.loads(json.dumps(json_safe(report))) == json_safe(report)


def test_missing_and_reversed_effects():
    s = _interaction_session()
    wrong = s.fit_custom("k*x1*x2 + m", label="misses x3")
    report = _report(s, wrong, {"recommended_models": [{"model_id": "C99"}]})
    checks = _checks(report)
    assert checks["shap"] == "warn" and checks["agent"] == "warn"
    assert report["overall"] in ("warn", "fail")

    flipped = s.fit_custom("k*x1*x2 - exp(x3) + m", label="wrong sign")
    flipped.params = {k: abs(v) for k, v in flipped.params.items()}
    assert _checks(_report(s, flipped))["shap"] == "fail"


def test_published_laws():
    s = _interaction_session()
    good = s.fit_custom("k*x1*x2 + c*exp(x3)", label="right form")
    tied = s.fit_custom("a*x1*x2 + b*exp(x3) + m", label="Published law 1", kind="literature")
    worse = s.fit_custom("k*x1 + m", label="Published law 2", kind="literature")

    s.known_laws = {"status": "ok", "laws": [{"model_id": tied.model_id}]}
    lit = next(c for c in _report(s, good)["checks"] if c["key"] == "literature")
    assert lit["status"] == "pass" and lit["value"] == tied.model_id

    s.known_laws = {"status": "ok", "laws": [{"model_id": worse.model_id}]}
    assert _checks(_report(s, good))["literature"] == "warn"


def test_no_signal_fails_and_shap_is_na():
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"x1": rng.normal(size=300), "x2": rng.normal(size=300)})
    df["y"] = rng.normal(size=300)
    s = DiscoverySession(df, "y", ["x1", "x2"])
    s.profile()
    m = s.fit_custom("k*x1 + m", label="line")
    checks = _checks(_report(s, m))
    assert checks["fit_vs_ceiling"] == "fail"
    assert checks["shap"] == "na"


def test_no_headline_gives_no_report():
    s = _interaction_session()
    assert coherence_report(s, Selection(None, "no_eligible_model"), [], [], {}) is None


def test_linear_effect_on_skewed_data_reads_linear():
    rng = np.random.default_rng(2)
    n = 300
    x = np.concatenate([rng.uniform(3.5, 6, n // 5), rng.uniform(6.8, 7.7, n - n // 5)])
    z = rng.uniform(0, 1, n)
    df = pd.DataFrame({"x": x, "z": z, "y": 60 * x + 10 * z + rng.normal(0, 5, n)})
    s = DiscoverySession(df, "y", ["x", "z"])
    s.profile()
    m = s.fit_custom("a*x + b*z + c", label="linear")
    shapes = {d["feature"]: d["shape"] for d in _report(s, m)["effect_directions"]}
    assert "linear increasing" in shapes["x"]


def test_shape_label_uses_slopes_on_skewed_data():
    rng = np.random.default_rng(3)
    x = rng.lognormal(0, 1, 2000)
    assert profile_shape(x, 2 * x)["shape"].startswith("roughly linear increasing")
    assert profile_shape(x, np.log(x))["shape"].startswith("saturating increasing")
