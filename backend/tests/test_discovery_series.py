"""Long series: the feature stage, the chronological split, memory diagnostics, templates."""

import asyncio
import json

import dspy
import numpy as np
import pandas as pd
import pytest
from dspy.utils.dummies import DummyLM

from backend.services.discovery.expression import (
    ExpressionError,
    compose_template,
    parse_template,
)
from backend.services.discovery.feature_stage import run_series_feature_stage
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


STRICT = dspy.ChatAdapter(use_json_adapter_fallback=False)

LAG_SPECS = [
    {"source": "z", "kind": "lag", "steps": 1},
    {"source": "z", "kind": "lag", "steps": 2},
    {"source": "x", "kind": "lag", "steps": 1},
    {"source": "y", "kind": "lag", "steps": 1},
    {"source": "z", "kind": "period", "period": "block", "block_steps": 3, "stat": "mean",
     "offset": 1},
]  # fmt: skip


def _stage_lm(specs, selected):
    """Scripted LLM: one proposal, then one selection."""
    selection = {"selected": [{"feature": f, "reason": "test"} for f in selected], "rationale": "t"}
    return DummyLM([{"specs_json": json.dumps(specs)}, {"selection_json": json.dumps(selection)}])


def _staged(df, specs=LAG_SPECS, selected=("z_l2",), launcher=None, lm=None):
    """A series session after the feature stage with a scripted LLM."""
    s = _session(df, launcher)
    with dspy.settings.context(adapter=STRICT):
        asyncio.run(
            run_series_feature_stage(
                s, lambda: lm or _stage_lm(specs, selected), {"project_description": "t"}
            )
        )
    return s


def test_grid_lag_is_missing_across_a_gap():
    df = pd.DataFrame({"Year": [2000, 2001, 2002, 2004, 2005], "v": [1.0, 2.0, 3.0, 5.0, 6.0]})
    grid = SeriesGrid.build(df, TimeStructure("Year", confidence="strong"))
    lag1 = grid.lagged(df["v"].to_numpy(float), 1)
    # 2004's previous year (2003) is missing: no value, never 2002's
    assert np.isnan(lag1[0]) and lag1[1] == 1.0 and lag1[2] == 2.0
    assert np.isnan(lag1[3]) and lag1[4] == 5.0


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


def test_series_session_is_chronological_before_the_feature_stage():
    s = _session(_series())
    assert s.series is not None and s.lag_features == []
    assert s.series["feature_stage"]["status"] == "not_run"
    assert s.n_rows == 200  # nothing dropped
    assert s.train["Year"].max() < s.holdout["Year"].min()
    assert np.all(np.diff(s.fit_data.X["Year"]) > 0)
    assert all(np.all(np.diff(f) == 1) for f in s.fit_data.folds)
    assert s.split_info()["order"] == "chronological"


def test_feature_stage_adds_the_selected_lag_and_keeps_every_row():
    s = _staged(_series())
    assert s.lag_features == ["z_l2"]
    assert s.series["feature_stage"]["status"] == "done"
    assert s.n_rows == 200 and len(s.train) + len(s.holdout) == 200  # padded, not dropped
    assert s.series["padded_rows"] == 2  # the first two years have no z two years earlier
    assert s.series["rows_without_history"] == 0  # a predictor's lag keeps every row
    # The holdout is still the end of the series, the CV folds contiguous blocks
    assert s.train["Year"].max() < s.holdout["Year"].min()
    assert "z_l2" in s.fit_data.X and "z_l2" in s.holdout
    lag = s.series["lag_features"][0]
    assert lag["column"] == "z at t-2" and "an index" in lag["description"]
    assert lag["reason"] == "test" and lag["padded_rows"] == 2
    assert s.descriptions["z at t-2"] == lag["description"]
    # The evidence shows the planted lag as the strongest candidate
    gains = {d["feature"]: d["gain"] for d in s.series["evidence"]["candidates"]}
    assert gains["z_l2"] > 0.5 and gains["z_l2"] == max(g for g in gains.values() if g is not None)
    # The edge-padded cells take the first available value of z
    ordered = s._frame
    assert ordered["z_l2"].iloc[0] == ordered["z_l2"].iloc[2] == ordered["z"].iloc[0]
    # The residual memory goes with the planted lag
    ac = s.series["residual_autocorrelation"]
    assert ac["with_selected"] is not None


def test_feature_stage_rejects_target_leakage_and_unknown_sources():
    specs = [
        {"source": "y", "kind": "period", "period": "block", "block_steps": 4, "stat": "mean"},
        {"source": "Year", "kind": "lag", "steps": 1},
        {"source": "nope", "kind": "lag", "steps": 1},
        {"source": "z", "kind": "lag", "steps": 2},
        {"source": "z", "kind": "lag", "steps": 50},  # far beyond the padding limit
        {"source": "z", "kind": "wiggle"},
    ]
    s = _staged(_series(), specs=specs, selected=("z_l2", "made_up"))
    reasons = " | ".join(r["reason"] for r in s.series["rejected"])
    assert "contains the current target value" in reasons
    assert "unknown source 'Year'" in reasons and "unknown source 'nope'" in reasons
    assert "padded rows" in reasons and "kind" in reasons
    assert s.lag_features == ["z_l2"]
    assert s.series["feature_stage"]["ignored_selection"] == ["made_up"]


def test_feature_stage_failure_keeps_the_current_features():
    lm = DummyLM([{"specs_json": "not json at all"}] * 2)
    s = _staged(_series(), lm=lm)
    assert s.series["feature_stage"]["status"] == "failed"
    assert s.lag_features == [] and s.features == ["Year", "x", "z"]
    assert any("feature stage failed" in n["text"] for n in s.notebook)


def test_feature_stage_asks_again_after_malformed_json():
    selection = {"selected": [{"feature": "z_l2", "reason": "test"}], "rationale": "t"}
    lm = DummyLM(
        [
            {"specs_json": "not json at all"},
            {"specs_json": json.dumps(LAG_SPECS)},
            {"selection_json": json.dumps(selection)},
        ]
    )
    s = _staged(_series(), lm=lm)
    assert s.series["feature_stage"]["status"] == "done"
    assert s.lag_features == ["z_l2"]


def test_missing_memory_is_diagnosed_and_the_lag_fixes_it():
    s = _staged(_series(memory=0.0, persistence=0.8), selected=("y_l1",))
    lag = s.series["lag_features"][0]
    assert lag["source"] == "y" and "persistence" in lag["description"]
    # The first year has no previous target: back-filling would copy its own target into
    # y_l1, so that row leaves the data instead of being padded
    assert s.series["rows_without_history"] == 1 and s.n_rows == 199
    assert len(s.train) + len(s.holdout) == 199 and len(s.holdout) == 40  # same holdout
    assert s.series["padded_rows"] == 0
    first = s.train.iloc[0]
    assert first["y_l1"] != first["y"] and s.train["Year"].min() == 1801
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
    s = _staged(_series())
    assert s.lag_features
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
    s = _staged(_series(), launcher=launcher)

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


def test_agent_sees_cross_validated_scoring_and_the_rmse_tie_rule():
    s = _session(_series())
    overview = s.overview()
    assert "metric_basis" not in overview["rows"]
    assert "contiguous time blocks" in overview["scoring"]
    assert "within one cv_se" in overview["scoring"]
    s.fit_custom("a0 + a1*x")
    assert "cv_rmse" in s.leaderboard(top=1)[0]
