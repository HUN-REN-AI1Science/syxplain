"""Regressions found in the final verification pass of the discovery branch."""

import asyncio
import json
from types import SimpleNamespace

import dspy
import numpy as np
import pandas as pd
import pytest

from backend.services.discovery import agent as agent_mod
from backend.services.discovery import fitting
from backend.services.discovery.agent import BudgetedReAct
from backend.services.discovery.expression import ExpressionError, parse_expression
from backend.services.discovery.report import merge_explanations
from backend.services.discovery.session import DiscoverySession
from backend.services.discovery.tools import build_tools
from backend.tests.test_discovery_session import FakeLauncher, _session


def _categorical_session():
    rng = np.random.default_rng(3)
    n = 200
    soil = rng.integers(1, 6, n).astype(float)
    x = rng.uniform(0, 10, n)
    y = 2 * soil + x + rng.normal(0, 0.5, n)
    df = pd.DataFrame({"soil_code": soil, "x": x, "y": y})
    return DiscoverySession(df, "y", ["soil_code", "x"])


def test_pysr_paths_refuse_categorical_codes_as_magnitudes():
    s = _categorical_session()
    assert s.kinds["soil_code"] == "categorical"
    with pytest.raises(ExpressionError, match="level"):
        s.evaluate_symbolic("2.1*soil_code + 0.9*x", "pysr_1")
    with pytest.raises(ValueError, match="categor"):
        s._validate_search(["soil_code", "x"], [], ["+"], None, None)
    s._validate_search(["x"], [], ["+"], None, None)


def test_failed_fold_refit_counts_as_undefined_not_in_sample(monkeypatch):
    s = _session()
    real = fitting._least_squares
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        # full-data multi-starts succeed; every per-fold refit fails
        return real(*args, **kwargs) if calls["n"] <= 3 else None

    monkeypatch.setattr(fitting, "_least_squares", flaky)
    m = s.fit_custom("a + b*pH", label="flaky")
    assert m.n_undefined > 0
    assert m.cv_r2 is None or m.cv_r2 < m.train_r2 - 0.1


def test_log1p_reports_domain_error():
    rng = np.random.default_rng(1)
    x = rng.uniform(0, 5, 120)
    df = pd.DataFrame({"x": x, "y": x - 4 + rng.normal(0, 0.1, 120)})
    s = DiscoverySession(df, "y", ["x"])
    m = s.fit_family("linear", ["x"], target_transform="log1p")
    assert m.error and "above -1" in m.error


def test_constant_target_profile_is_strict_json():
    df = pd.DataFrame({"x": np.arange(60.0), "y": np.full(60, 3.0)})
    s = DiscoverySession(df, "y", ["x"])
    json.dumps(s.profile()["features"], allow_nan=False)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("a*exp + x", "is a function"),
        ("9" * 400 + "*x", "out of range"),
        ("1e999*x", "out of range"),
    ],
)
def test_parser_gives_clear_errors(source, message):
    with pytest.raises(ExpressionError, match=message):
        parse_expression(source, ["x"])


def test_merge_drops_unmatched_and_duplicate_cards():
    equations = [
        {"model_id": "C1", "equation": "a*x", "is_headline": True},
        {"model_id": "S2", "equation": "x^2", "is_headline": False},
    ]
    explanations = {
        "equations": [
            {"id": 1, "model_id": "C1", "overview": "ok"},
            {"id": 2, "model_id": "S9", "equation": "made up", "loss": 0.001},
            {"id": 3, "model_id": "C1", "loss": 5},
            {"id": 4, "model_id": ["S2"], "equation": "nothing"},
        ],
        "recommendation": {"equation_id": 2, "rationale": []},
    }
    out, matched = merge_explanations(explanations, equations)
    assert matched == 1
    assert [c["model_id"] for c in out["equations"]] == ["C1", "S2"]
    rec = out["recommendation"]
    assert rec["equation_id"] == 1 and rec["agrees_with_headline"] is True


def test_compaction_counts_steps_after_dspy_truncation():
    s = _session()
    agent = BudgetedReAct(agent_mod.EquationDiscoveryAgent, build_tools(s), session=s, max_iters=30)
    traj = {}
    for i in range(10, 30):  # DSPy dropped steps 0-9
        traj[f"thought_{i}"] = "thinking " * 40
        traj[f"tool_name_{i}"] = "describe_data"
        traj[f"tool_args_{i}"] = {}
        traj[f"observation_{i}"] = json.dumps({"step": i, "pad": "z" * 1500})
    compact = agent._format_trajectory(traj)
    assert len(compact) < 0.5 * len(dspy.ReAct._format_trajectory(agent, traj))
    assert traj["observation_24"] in compact and traj["observation_23"] not in compact


def test_cancel_before_job_id_is_known_still_cancels_the_job():
    class LateIdLauncher(FakeLauncher):
        async def submit(self, search_id, input_data, on_job_id=None):
            await asyncio.sleep(0.2)  # slurmrestd accepted the job; the reply is slow
            return f"job-{search_id}"

    launcher = LateIdLauncher()

    async def scenario():
        s = _session(launcher)
        rec = await s.start_search(["pH"], [], ["+"], enforce_budget=False)
        await asyncio.sleep(0.05)
        await s.cancel_search(rec.search_id)
        await asyncio.sleep(0.3)
        return rec

    rec = asyncio.run(scenario())
    assert rec.status == "cancelled" and launcher.cancelled == ["job-pysr_1"]


def test_late_callback_does_not_touch_a_finished_run():
    from backend.api.routers.progress import _store_task_result

    run = SimpleNamespace(id="abcdef12-0000", status="completed", results={"equations": []})
    assert _store_task_result(run, "pysr_2", {"equations": [1, 2]}) is False
    assert run.results == {"equations": []}
    run.status = "running"
    assert _store_task_result(run, "pysr_2", {"equations": [1]}) is True
    assert run.results["tasks"]["pysr_2"] == {"equations": [1]}
