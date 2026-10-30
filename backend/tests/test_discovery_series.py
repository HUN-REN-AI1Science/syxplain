"""Long series: lagged features, the chronological split, memory diagnostics, templates."""

import asyncio

import numpy as np
import pandas as pd
import pytest

from backend.services.discovery.expression import (
    ExpressionError,
    compose_template,
    parse_template,
)
from backend.services.discovery.fitting import lag1_autocorrelation, time_blocks
from backend.services.discovery.series import SeriesGrid, final_segment
from backend.services.discovery.session import DiscoverySession
from backend.services.discovery.temporal import TimeStructure


class FakeLauncher:
    """Stands in for Slurm: records the input and returns canned equations."""

    def __init__(self, equations=None):
        self.equations = equations or []
        self.submitted: list[tuple[str, dict]] = []

    async def submit(self, search_id, input_data, on_job_id=None):
        self.submitted.append((search_id, input_data))
        if on_job_id:
            on_job_id(f"job-{search_id}")
        return f"job-{search_id}"

    async def wait(self, job_id):
        return True, {"status": "success", "equations": self.equations}, None

    async def cancel(self, job_id):
        pass


def _series(n=200, seed=0, memory=3.0, persistence=0.0):
    """Annual series: y depends on x now and on z two years earlier (plus AR(1) persistence)."""
    rng = np.random.default_rng(seed)
    year = np.arange(1800, 1800 + n)
    x = np.linspace(0, 10, n) + rng.normal(0, 1, n)
    z = rng.normal(0, 1, n)
    y = np.empty(n)
    for t in range(n):
        lagged = memory * z[t - 2] if t >= 2 else 0.0
        prev = persistence * y[t - 1] if t >= 1 else 0.0
        y[t] = 2 * x[t] + lagged + prev + rng.normal(0, 0.3)
    df = pd.DataFrame({"Year": year, "x": x, "z": z, "y": y})
    return df.sample(frac=1.0, random_state=seed)  # uploads are not necessarily sorted


def _session(df, launcher=None):
    return DiscoverySession(
        df,
        "y",
        [c for c in df.columns if c != "y"],
        launcher=launcher,
        descriptions={"z": "an index"},
    )


def test_grid_lag_is_missing_across_a_gap():
    df = pd.DataFrame({"Year": [2000, 2001, 2002, 2004, 2005], "v": [1.0, 2.0, 3.0, 5.0, 6.0]})
    grid = SeriesGrid.build(df, TimeStructure("Year", confidence="strong"))
    lag1 = grid.lagged(df["v"].to_numpy(float), 1)
    # 2004's previous year (2003) is missing: no value, never 2002's
    assert np.isnan(lag1[0]) and lag1[1] == 1.0 and lag1[2] == 2.0
    assert np.isnan(lag1[3]) and lag1[4] == 5.0
    mean2 = grid.lagged(df["v"].to_numpy(float), 2, mean=True)
    assert mean2[2] == 1.5 and np.isnan(mean2[3]) and np.isnan(mean2[4])


def test_time_blocks_and_final_segment_follow_each_trajectory():
    keys = np.array([0] * 10 + [1] * 10)
    held = final_segment(keys, 0.2)
    assert np.flatnonzero(held).tolist() == [8, 9, 18, 19]
    folds = time_blocks(keys, 5)
    assert folds[0].tolist() == [0, 1, 10, 11]
    assert sorted(np.concatenate(folds).tolist()) == list(range(20))


def test_lag1_autocorrelation_stays_within_trajectories():
    rng = np.random.default_rng(0)
    smooth = np.cumsum(rng.normal(size=200))
    ac, pairs = lag1_autocorrelation(smooth - smooth.mean(), np.zeros(200, dtype=int))
    assert ac > 0.8 and pairs == 199
    noise_ac, _ = lag1_autocorrelation(rng.normal(size=200), np.zeros(200, dtype=int))
    assert abs(noise_ac) < 0.2
    _, pairs = lag1_autocorrelation(rng.normal(size=200), np.repeat([0, 1], 100))
    assert pairs == 198


def test_series_gets_the_planted_lag_and_a_chronological_split():
    s = _session(_series())
    assert s.series is not None
    assert "z_l2" in s.lag_features
    assert not any(f.startswith("y_") for f in s.lag_features)  # no persistence planted
    assert all(not f.startswith("Year") for f in s.lag_features)  # time is not lagged
    # The holdout is the end of the series, the CV folds contiguous blocks
    assert s.train["Year"].max() < s.holdout["Year"].min()
    assert np.all(np.diff(s.fit_data.X["Year"]) > 0)
    assert all(np.all(np.diff(f) == 1) for f in s.fit_data.folds)
    info = s.split_info()
    assert info["order"] == "chronological"
    lag = next(d for d in s.series["lag_features"] if d["feature"] == "z_l2")
    assert lag["column"] == "z at t-2" and "an index" in lag["description"]
    assert s.descriptions["z at t-2"] == lag["description"]
    screened = {d["feature"]: d for d in s.series["screening"]["candidates"]}
    assert screened["z_l2"]["selected"] and screened["z_l2"]["gain"] > 0.5


def test_missing_memory_is_diagnosed_and_the_lag_fixes_it():
    s = _session(_series(memory=0.0, persistence=0.8))
    lag = next(d for d in s.series["lag_features"] if d["source"] == "y")
    assert "persistence" in lag["description"]
    # Year takes the trend, so x keeps its own effect and the memory shows in the residuals
    without = s.fit_custom("a0 + a1*x + a2*Year")
    assert any("correlated in time" in r for r in without.reasons)
    with_lag = s.fit_custom(f"a0 + a1*x + a2*Year + a3*{lag['feature']}")
    assert not any("correlated in time" in r for r in with_lag.reasons)
    assert with_lag.cv_r2 > without.cv_r2


def test_unordered_data_keeps_the_random_split():
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"a": rng.uniform(0, 1, 120), "b": rng.uniform(0, 1, 120)})
    df["y"] = 3 * df["a"] + rng.normal(0, 0.1, 120)
    s = DiscoverySession(df, "y", ["a", "b"])
    assert s.series is None and s.lag_features == [] and s.fit_data.series is None
    assert s.split_info()["order"] == "random"


def test_rate_law_inputs_exclude_lagged_features():
    s = _session(_series())
    dyn = s.set_dynamics("Year")
    assert "x" in dyn.inputs and not set(dyn.inputs) & set(s.lag_features)


def test_template_validation():
    features = ["CO2", "Tm", "NAO_l2"]
    assert parse_template("f(CO2, Tm) + g(NAO_l2)", features) == [
        ("f", ["CO2", "Tm"]),
        ("g", ["NAO_l2"]),
    ]
    assert parse_template("2*f(CO2) * (g(Tm) - h(NAO_l2))", features)
    for bad, message in [
        ("f(CO2, Tm)", "passed to no subexpression"),
        ("f(CO2) + g(Tm) + NAO_l2", "only use"),
        ("f(CO2, Tm) + g(PDSI)", "not search features"),
        ("cos(CO2) + g(Tm, NAO_l2)", "cannot name"),
        ("f(CO2) + f(Tm, NAO_l2)", "different numbers"),
        ("CO2 + Tm", "calls no subexpression"),
    ]:
        with pytest.raises(ExpressionError, match=message):
            parse_template(bad, features)


def test_compose_template_substitutes_each_call():
    out = compose_template(
        "f(CO2, Tm) + f(Tm, CO2) * g(NAO_l2)",
        "f = (#2 * 1.5) - #1; g = cos(#1 + -0.5)",
    )
    assert out == "((Tm * 1.5) - CO2) + ((CO2 * 1.5) - Tm) * (cos(NAO_l2 + -0.5))"
    with pytest.raises(ExpressionError):
        compose_template("f(CO2) + g(Tm)", "f = #1")
    with pytest.raises(ExpressionError):
        compose_template("f(CO2)", "CO2 * 2")


def test_templated_search_sends_the_template_and_scores_composed_equations():
    launcher = FakeLauncher(
        equations=[
            {"equation": "f = #1 * 2.0; g = #1 * 3.0", "loss": 0.1, "complexity": 7},
            {"equation": "f = #1 * 2.1; g = 0.5", "loss": 1.0, "complexity": 5},
        ]
    )
    s = _session(_series(), launcher)

    async def go():
        record = await s.start_search(
            ["x", "z_l2"],
            [],
            ["+", "*"],
            guesses=["2*x"],
            template="f(x) + g(z_l2)",
        )
        await record.task
        return record

    record = asyncio.run(go())
    _, sent = launcher.submitted[0]
    assert sent["config"]["template"] == "f(x) + g(z_l2)" and sent["guesses"] == []
    assert record.rejected_guesses[0]["guess"] == "2*x"
    assert record.summary(s.models)["template"] == "f(x) + g(z_l2)"
    models = [s.models[m] for m in record.model_ids]
    assert {m.expression for m in models} == {"(x * 2.0) + (z_l2 * 3.0)", "(x * 2.1) + (0.5)"}
    assert models[0].diagnostics["template_parts"] == "f = #1 * 2.0; g = #1 * 3.0"
    assert max(m.cv_r2 for m in models) > 0.9
