"""Time structure, rate-law fitting, SINDy and trajectory simulation."""

import asyncio
import json

import numpy as np
import pandas as pd
import pytest

from backend.services.discovery.expression import parse_expression
from backend.services.discovery.report import build_results, explanation_data_spec
from backend.services.discovery.session import DiscoverySession
from backend.services.discovery.sindy import LocalSindyLauncher, run_sindy
from backend.services.discovery.temporal import detect_time_structure, simulate
from backend.services.discovery.tools import build_tools


def _kinetics(n_jars=6, n_times=12, noise=0.02, seed=0, shuffle=True):
    """First-order approach to a plateau, rate proportional to temperature."""
    rng = np.random.default_rng(seed)
    rows = []
    for j in range(n_jars):
        temp = 10 + 4 * j
        k = 0.004 * temp
        t = np.linspace(0, 60, n_times)
        y = 80 - 75 * np.exp(-k * t)
        y = y * (1 + rng.normal(0, noise, n_times))
        for ti, yi in zip(t, y, strict=True):
            rows.append({"jar": f"J{j}", "time_d": ti, "temperature": temp, "P_sorbed": yi})
    df = pd.DataFrame(rows)
    return df.sample(frac=1, random_state=seed).reset_index(drop=True) if shuffle else df


def _logistic(n_series=5, n_times=25, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_series):
        y0 = 0.5 + s * 0.4
        t = np.linspace(0, 20, n_times)
        y = 10 / (1 + (10 - y0) / y0 * np.exp(-0.5 * t))
        y = y * (1 + rng.normal(0, 0.005, n_times))
        for ti, yi in zip(t, y, strict=True):
            rows.append({"plot": s, "day": ti, "biomass": yi})
    return pd.DataFrame(rows)


def _session(df, target, launchers=None):
    return DiscoverySession(
        df,
        target,
        [c for c in df.columns if c != target],
        launchers=launchers,
    )


# ------------------------------------------------------------------ detection


def test_detects_time_and_trajectory_columns():
    ts = detect_time_structure(_kinetics(), "P_sorbed")
    assert ts.time_column == "time_d"
    assert ts.group_column == "jar"
    assert ts.confidence == "strong"
    assert ts.n_trajectories == 6
    assert ts.points_min == 12


def test_static_data_has_no_time_structure():
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 10, 200)
    df = pd.DataFrame({"x": x, "z": rng.normal(size=200), "y": 3 * x + rng.normal(0, 1, 200)})
    ts = detect_time_structure(df, "y")
    assert ts.confidence == "none"


def test_single_series_with_dates_is_detected():
    t = pd.date_range("2024-01-01", periods=40, freq="D")
    y = 50 - 45 * np.exp(-0.1 * np.arange(40))
    df = pd.DataFrame({"date": t.astype(str), "uptake": y}).sample(frac=1, random_state=0)
    ts = detect_time_structure(df, "uptake")
    assert ts.time_column == "date"
    assert ts.group_column is None
    assert ts.confidence == "strong"


# ------------------------------------------------------------- dynamics data


def test_folds_and_holdout_keep_trajectories_whole():
    s = _session(_kinetics(), "P_sorbed")
    dyn = s.set_dynamics("time_d", "jar")
    assert dyn.regime == "trajectories"
    assert dyn.inputs == ["temperature"]
    held = {e.key for e in dyn.holdout_episodes}
    assert held and held.isdisjoint({e.key for e in dyn.train_episodes})
    for fold in dyn.fit_data.folds:
        inside = set(dyn.keys[fold])
        outside = set(np.delete(dyn.keys, fold))
        assert inside.isdisjoint(outside)


def test_single_series_holds_out_the_final_segment():
    t = np.linspace(0, 30, 30)
    df = pd.DataFrame({"time": t, "y": 50 - 45 * np.exp(-0.1 * t), "x": np.ones(30)})
    s = _session(df, "y")
    dyn = s.set_dynamics("time")
    assert dyn.regime == "final_segment"
    (ep,) = dyn.holdout_episodes
    assert ep.t.min() > dyn.train_episodes[0].t.max()
    assert ep.t0 == pytest.approx(dyn.train_episodes[0].t.max())


def test_unknown_columns_are_reported():
    s = _session(_kinetics(), "P_sorbed")
    with pytest.raises(ValueError, match="Unknown column"):
        s.set_dynamics("tme_d", "jar")
    with pytest.raises(ValueError, match="set_dynamics"):
        s.fit_custom("k*(a - P_sorbed)", problem="dynamic")


# ------------------------------------------------------------------- scoring


def test_fit_ode_recovers_rate_law_and_simulates():
    s = _session(_kinetics(), "P_sorbed")
    s.set_dynamics("time_d", "jar")
    m = s.fit_custom(
        "k*temperature*(a - P_sorbed)",
        {"k": 0.004, "a": 80},
        label="first order",
        problem="dynamic",
    )
    assert m.problem == "dynamic" and m.model_id.startswith("D")
    assert m.cv_r2 > 0.9
    assert m.params["a"] == pytest.approx(80, rel=0.05)
    assert m.simulation["r2"] > 0.95
    assert s.simulate_model(m, holdout=True)["r2"] > 0.95
    # Rate laws rank separately from static equations.
    assert m not in s.ranked_models()
    assert s.ranked_models("dynamic") == [m]


def test_unstable_rate_law_is_flagged_diverged():
    s = _session(_logistic(), "biomass")
    dyn = s.set_dynamics("day", "plot")
    expr = parse_expression("biomass^2", dyn.variables, parameters=())
    sim = simulate(expr, {}, dyn.state, dyn.train_episodes, fill_value=5.0)
    assert sim["n_diverged"] == sim["n_episodes"]


# --------------------------------------------------------------------- SINDy


def test_run_sindy_finds_logistic_terms():
    s = _session(_logistic(), "biomass")
    dyn = s.set_dynamics("day", "plot")
    out = run_sindy(
        {
            "X": {"biomass": dyn.fit_data.X["biomass"]},
            "dydt": dyn.fit_data.y,
            "variables": ["biomass"],
            "degree": 3,
            "extra_functions": [],
        }
    )
    two_terms = [e for e in out["equations"] if e["complexity"] == 2]
    assert two_terms
    eq = min(two_terms, key=lambda e: e["loss"])["equation"]
    assert "biomass^2" in eq
    expr = parse_expression(eq, ["biomass"], parameters=())
    grid = np.array([2.0, 5.0, 8.0])
    rate = expr.evaluate({"biomass": grid}, {})
    np.testing.assert_allclose(rate, 0.5 * grid * (1 - grid / 10), rtol=0.15)


def test_sindy_search_flows_through_the_session():
    events = []

    async def scenario():
        s = DiscoverySession(
            _kinetics(),
            "P_sorbed",
            ["temperature", "time_d"],
            launchers={"sindy": LocalSindyLauncher()},
            on_event=events.append,
        )
        s.set_dynamics("time_d", "jar")
        rec = await s.start_sindy_search(["temperature"], degree=2, rationale="rate law")
        await s.wait_any([rec.search_id], 30)
        return s, rec

    s, rec = asyncio.run(scenario())
    assert rec.search_id == "sindy_1" and rec.status == "completed", rec.error
    assert any(e["kind"] == "search_completed" for e in events)
    models = [s.models[m] for m in rec.model_ids]
    assert models and all(m.problem == "dynamic" for m in models)
    best = s.ranked_models("dynamic")[0]
    assert best.cv_r2 > 0.9
    assert best.simulation
    summary = rec.summary(s.models)
    assert summary["engine"] == "sindy" and summary["degree"] == 2


def test_tools_return_errors_as_text_and_results_include_dynamics():
    async def scenario():
        s = DiscoverySession(
            _kinetics(),
            "P_sorbed",
            ["temperature", "time_d"],
            launchers={"sindy": LocalSindyLauncher()},
        )
        tools = {t.__name__: t for t in build_tools(s)}
        early = await tools["fit_ode"]("k*(a - P_sorbed)")
        bad = await tools["set_dynamics"]("nonexistent")
        described = json.loads(await tools["describe_time_structure"]())
        ok = json.loads(await tools["set_dynamics"]("time_d", "jar"))
        fit = json.loads(
            await tools["fit_ode"](
                "k*temperature*(a - P_sorbed)", "first order", {"k": 0.004, "a": 80}
            )
        )
        started = json.loads(await tools["start_sindy_search"](["temperature"]))
        await s.wait_any(None, 30)
        board = json.loads(await tools["leaderboard"](problem="dynamic"))
        return s, early, bad, described, ok, fit, started, board

    s, early, bad, described, ok, fit, started, board = asyncio.run(scenario())
    assert early.startswith("Error") and "set_dynamics" in early
    assert bad.startswith("Error") and "Unknown column" in bad
    assert described["detected"]["time_column"] == "time_d"
    assert ok["rate"] == "dP_sorbed/dt"
    assert fit["simulation_r2"] > 0.95
    assert started["search_id"] == "sindy_1"
    assert board["models"][0]["model_id"].startswith("D")

    s.profile()
    results = build_results(
        s,
        {"summary": "x", "recommended_models": [{"model_id": fit["model_id"], "why": "ok"}]},
        None,
    )
    dynamics = results["discovery"]["dynamics"]
    assert dynamics["selection"]["headline_model_id"] is not None
    assert dynamics["equations"][0]["traces"]
    assert dynamics["equations"][0]["holdout_r2"] > 0.9
    assert all(not e["model_id"].startswith("D") for e in results["equations"])
    spec = explanation_data_spec(results)
    assert spec["discovery"]["dynamics"]["headline"]["equation"].startswith("d")


def test_vetoed_rate_laws_are_still_reported():
    s = _session(_kinetics(), "P_sorbed")
    s.set_dynamics("time_d", "jar")
    m = s.fit_custom("k*temperature", label="no saturation", problem="dynamic")
    assert m.cv_r2 <= 0
    s.profile()
    dynamics = build_results(s, {"summary": "x"}, None)["discovery"]["dynamics"]
    assert dynamics["selection"]["headline_model_id"] is None
    [card] = dynamics["equations"]
    assert card["model_id"] == m.model_id and not card["is_headline"]
    assert card["not_recommended"]
    assert card["traces"]


def test_a_measured_column_does_not_chop_a_series_into_trajectories():
    # Lake Bilancino: a regulated outflow with a few repeated values, described as measured
    # "at the release station", was taken for 66 interleaved trajectories
    rng = np.random.default_rng(0)
    n = 400
    outflow = rng.choice([0.31, 0.6, 1.2, 2.5], size=n)
    level = 250 + np.cumsum(rng.normal(0, 0.05, n)) - 0.02 * np.cumsum(outflow - outflow.mean())
    df = pd.DataFrame(
        {
            "Date": pd.date_range("2010-01-01", periods=n, freq="D").strftime("%Y-%m-%d"),
            "Flow_Rate": outflow,
            "Lake_Level": level,
        }
    )
    ts = detect_time_structure(
        df, "Lake_Level", {"Flow_Rate": "Daily outflow at the release station (m3/s)"}
    )
    assert ts.time_column == "Date" and ts.group_column is None and ts.regular


def test_consecutive_episodes_still_count_as_trajectories():
    # Batches run one after another on absolute dates: each date occurs once, but the
    # batch column switches only between episodes
    rows = []
    for batch in range(4):
        start = pd.Timestamp("2020-01-01") + pd.Timedelta(days=40 * batch)
        for day in range(30):
            rows.append(
                {
                    "batch": batch,
                    "Date": (start + pd.Timedelta(days=day)).strftime("%Y-%m-%d"),
                    "biomass": 10 / (1 + np.exp(-(day - 15) / 3)) + batch,
                }
            )
    ts = detect_time_structure(pd.DataFrame(rows), "biomass")
    assert ts.time_column == "Date" and ts.group_column == "batch"
