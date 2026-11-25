import numpy as np
import pandas as pd
import pytest

from backend.services.discovery.session import DiscoverySession


def _session(df: pd.DataFrame, target: str = "y") -> DiscoverySession:
    predictors = [c for c in df.columns if c != target]
    s = DiscoverySession(df, target, predictors)
    s.profile()
    return s


def test_mitscherlich_ranks_first_and_recovers_parameters():
    rng = np.random.default_rng(0)
    P = rng.uniform(0, 200, 600)
    y = 80 * (1 - np.exp(-0.02 * (P + 15))) + rng.normal(0, 2, P.size)
    s = _session(pd.DataFrame({"P": P, "y": y}))

    results = [
        s.fit_family(f, ["P"])
        for f in ("linear", "logarithmic", "michaelis_menten", "mitscherlich")
    ]
    best = max(results, key=lambda m: m.cv_r2)
    assert best.name == "mitscherlich"
    assert best.verdict == "good"
    assert best.params["a"] == pytest.approx(80, rel=0.05)
    assert best.params["c"] == pytest.approx(0.02, rel=0.15)
    assert any("noise ceiling" in r for r in best.reasons)

    linear = next(m for m in results if m.name == "linear")
    assert any("wrong curve shape along P" in r for r in linear.reasons)


def test_langmuir_fit():
    rng = np.random.default_rng(1)
    C = rng.uniform(0.1, 50, 400)
    y = 300 * C / (4 + C) + rng.normal(0, 5, C.size)
    s = _session(pd.DataFrame({"C": C, "y": y}))
    m = s.fit_family("michaelis_menten", ["C"])
    assert m.params["a"] == pytest.approx(300, rel=0.05)
    assert m.params["b"] == pytest.approx(4, rel=0.2)
    assert m.cv_r2 > 0.95


def test_missing_variable_is_named_in_reasons():
    rng = np.random.default_rng(2)
    P = rng.uniform(0, 150, 500)
    pH = rng.uniform(4, 8, 500)
    y = 60 * (1 - np.exp(-0.03 * (P + 10))) * (pH / 6) + rng.normal(0, 1.5, P.size)
    s = _session(pd.DataFrame({"P": P, "pH": pH, "y": y}))

    m = s.fit_family("mitscherlich", ["P"])
    assert m.verdict == "poor"
    assert "pH" in m.diagnostics["missing_variables"]
    assert any(r.startswith("missing variable pH") for r in m.reasons)

    both = s.fit_custom("a*(1 - exp(-c*(P + b)))*pH", {"a": 10, "b": 0, "c": 0.03})
    assert both.cv_r2 > 0.95
    assert both.verdict == "good"


def test_heteroscedastic_data_suggests_log_transform():
    rng = np.random.default_rng(3)
    x = rng.uniform(1, 10, 500)
    y = 2 * x**1.5 * np.exp(rng.normal(0, 0.3, x.size))
    s = _session(pd.DataFrame({"x": x, "y": y}))
    m = s.fit_family("power", ["x"])
    assert any("target_transform='log'" in r for r in m.reasons)
    logged = s.fit_family("power", ["x"], target_transform="log")
    assert logged.fitted_expression.startswith("exp(")
    assert logged.cv_r2 is not None


def test_domain_requirements_are_reported():
    rng = np.random.default_rng(4)
    x = rng.uniform(-5, 5, 200)
    s = _session(pd.DataFrame({"x": x, "y": x + rng.normal(0, 1, 200)}))
    m = s.fit_family("power", ["x"])
    assert m.verdict == "failed"
    assert "positive" in m.error


def test_pure_noise_has_low_ceiling():
    rng = np.random.default_rng(5)
    df = pd.DataFrame(
        {"a": rng.normal(size=400), "b": rng.normal(size=400), "y": rng.normal(size=400)}
    )
    s = _session(df)
    assert s.ceiling_r2 < 0.1
    shape = s.shape(s.alias_of["a"])
    assert "flat" in shape["shape"] or "noisy" in shape["shape"]


def test_symbolic_equation_is_rescored():
    rng = np.random.default_rng(6)
    x = rng.uniform(0, 5, 300)
    y = 3.0 * np.sqrt(x) + 1 + rng.normal(0, 0.1, x.size)
    s = _session(pd.DataFrame({"x": x, "y": y}))
    m = s.evaluate_symbolic("2.9*sqrt(x) + 1.1", "pysr_1")
    assert m.kind == "symbolic"
    assert m.cv_r2 > 0.98
    assert m.params  # constants were refit


def test_aliases_and_holdout_split():
    rng = np.random.default_rng(7)
    df = pd.DataFrame(
        {"Soil pH [-]": rng.uniform(4, 8, 100), "Yield (t/ha)": rng.uniform(1, 9, 100)}
    )
    df.loc[3, "Soil pH [-]"] = np.nan
    s = DiscoverySession(df, "Yield (t/ha)", ["Soil pH [-]"])
    assert s.features == ["Soil_pH"]
    assert s.target_alias == "Yield"
    assert s.n_rows == 99
    assert len(s.holdout) == 20 and len(s.train) == 79


def test_shap_finds_interaction_and_partial_shape():
    rng = np.random.default_rng(8)
    n = 600
    a = rng.uniform(1, 5, n)
    b = rng.uniform(1, 5, n)
    sat = rng.uniform(0, 10, n)
    junk = rng.normal(size=n)
    y = a * b + 6 * (1 - np.exp(-0.6 * sat)) + rng.normal(0, 0.2, n)
    s = _session(pd.DataFrame({"u": a, "v": b, "sat": sat, "junk": junk, "y": y}))

    shap = s.profile()["shap"]
    assert shap["available"] and shap["reliable"]
    top_pair = shap["interactions"][0]
    assert {top_pair["a"], top_pair["b"]} == {"u", "v"}
    assert all("junk" not in (p["a"], p["b"]) for p in shap["interactions"])
    assert shap["importance"][-1]["feature"] == "junk"
    assert shap["partial_effects"]["junk"].startswith("negligible")
    assert shap["partial_effects"]["sat"].startswith("saturating increasing")
    assert s.shape("sat")["partial_effect"]["shape"].startswith("saturating increasing")


def test_shap_and_verdicts_on_pure_noise():
    """No signal: ceiling below 0.05, SHAP unreliable, verdict no_signal, never 'looks like noise'."""
    rng = np.random.default_rng(11)
    df = pd.DataFrame(
        {f"x{i}": rng.uniform(1, 5, 100) for i in range(3)} | {"y": rng.normal(size=100)}
    )
    s = _session(df)
    assert s.fit_data.has_signal is False
    assert s.profile()["shap"]["reliable"] is False
    assert s.profile()["shap"]["interactions"] == []
    m = s.fit_family("linear", ["x0"])
    assert m.verdict == "no_signal"
    assert not any("looks like noise" in r for r in m.reasons)


def test_smooth_law_can_exceed_the_benchmark():
    rng = np.random.default_rng(12)
    P = rng.uniform(0, 100, 120)
    pH = rng.uniform(4.5, 8, 120)
    y = 50 * P / (10 + P) * np.exp(-((pH - 6.5) ** 2) / 2) + rng.normal(0, 0.5, 120)
    s = _session(pd.DataFrame({"P": P, "pH": pH, "y": y}))
    m = s.fit_custom("a*P/(b + P)*exp(-(pH - c)^2/(2*d^2))", {"a": 40, "b": 5, "c": 6, "d": 1})
    assert m.cv_r2 > s.ceiling_r2
    assert any("exceeds the nonparametric benchmark" in r for r in m.reasons)
    assert not any("matches the noise ceiling" in r for r in m.reasons)


def test_ill_conditioned_fit_is_never_good():
    rng = np.random.default_rng(13)
    x = rng.uniform(1, 2, 200)
    y = 3 * x + rng.normal(0, 0.05, 200)
    s = _session(pd.DataFrame({"x": x, "y": y}))
    m = s.fit_custom("a*x + b*x + c", {"a": 1, "b": 2, "c": 0})  # a and b are not separable
    assert m.ill_conditioned or m.diagnostics["weak_parameters"]
    assert m.verdict != "good"


def test_zero_coefficient_is_not_called_unidentifiable():
    rng = np.random.default_rng(14)
    x = rng.uniform(0, 10, 200)
    y = 2 * x + rng.normal(0, 1, 200)  # true intercept 0
    s = _session(pd.DataFrame({"x": x, "y": y}))
    m = s.fit_family("linear", ["x"])
    if m.diagnostics["nonsignificant_parameters"]:
        assert "a" in m.diagnostics["nonsignificant_parameters"]
    assert not any("does not pin down" in r for r in m.reasons)


def test_missing_variable_flag_is_rare_on_noise_features():
    hits = 0
    for seed in range(40):
        rng = np.random.default_rng(seed)
        df = pd.DataFrame({f"n{i}": rng.normal(size=33) for i in range(6)})
        df["x1"] = rng.uniform(0, 10, 33)
        df["y"] = 2 * df["x1"] + rng.normal(0, 1, 33)
        s = DiscoverySession(df, "y", [*(f"n{i}" for i in range(6)), "x1"])
        s.fit_data.ceiling_r2, s.fit_data.ceiling_sd = 0.95, 0.02
        m = s.fit_family("linear", ["x1"])
        hits += bool(m.diagnostics["missing_variables"])
    assert hits <= 4  # <= 10% of seeds


def test_undefined_predictions_count_as_errors():
    rng = np.random.default_rng(15)
    x = rng.uniform(1.2, 5, 60)
    x[:3] = [0.5, 0.7, 0.9]
    y = np.log(np.clip(x - 1, 1e-3, None)) + rng.normal(0, 0.05, 60)
    s = _session(pd.DataFrame({"x": x, "y": y}))
    m = s.fit_custom("a*log(x - b)", {"a": 1, "b": 1}, label="shifted log")
    assert m.n_undefined >= 1
    assert any("undefined on" in r for r in m.reasons)
