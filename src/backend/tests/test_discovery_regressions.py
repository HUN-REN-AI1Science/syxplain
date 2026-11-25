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
from backend.utils.user_llm import UserLLM


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


def test_all_categorical_run_skips_pysr_and_keeps_classic_models(monkeypatch):
    from backend.core.config import clear_settings_cache
    from backend.services.orchestrator_service import AnalysisContext, AnalysisOrchestrator
    from backend.tests.test_discovery_orchestrator import PYSR_CONFIG, FakeBackend, StubProgress

    monkeypatch.setenv("DISCOVERY_WALL_CLOCK_MIN", "5")
    monkeypatch.setenv("DISCOVERY_REVIEW_STEPS", "0")
    monkeypatch.setenv("DISCOVERY_AGENT_ENABLED", "false")
    clear_settings_cache()
    try:
        orch = AnalysisOrchestrator(backend=FakeBackend())
        monkeypatch.setattr(orch, "_is_run_terminal", lambda run_id: None)
        monkeypatch.setattr(orch, "_store_slurm_job_ids", lambda run_id, ids: None)
        monkeypatch.setattr(orch, "_wants_literature", lambda ctx: False)
        rng = np.random.default_rng(0)
        soil = rng.integers(1, 5, 300).astype(float)
        df = pd.DataFrame({"soil_code": soil, "y": 3 * (soil == 2) + rng.normal(0, 0.2, 300)})
        context = AnalysisContext(
            run_id="run-cat",
            user_id="u",
            problem_description={
                "project_description": "soil classes",
                "target_variable": "y",
                "features": {"soil_code": "soil class code"},
            },
            data=df,
            target_column="y",
            predictor_columns=["soil_code"],
        )
        results = asyncio.run(orch._run_discovery(context, PYSR_CONFIG, StubProgress()))
    finally:
        clear_settings_cache()
    assert orch.backend.inputs == {}
    d = results["discovery"]
    assert d["searches"] == []
    assert any(n["kind"] == "data_issue" and "categorical" in n["text"] for n in d["notebook"])
    stages = [w["stage"] for w in results["warnings"]]
    assert "symbolic_regression" in stages
    # The level-means baseline is a reference fitted after exploration, not a discovery.
    assert "selection" in stages
    assert d["selection"]["headline_is_reference"] is True


def test_one_analysis_mode_and_who_gets_the_literature_search(monkeypatch):
    from backend.core.config import clear_settings_cache
    from backend.schemas.requests import RunRequest
    from backend.services.orchestrator_service import AnalysisContext, AnalysisOrchestrator
    from backend.tests.test_discovery_orchestrator import FakeBackend

    req = RunRequest(
        problem_description={
            "project_description": "p",
            "target_variable": "y",
            "features": {"x": "x"},
        },
        csv_filename="a.csv",
        analysis_type="deep",  # legacy clients keep working
        deep_research_model="o4-mini-deep-research",
    )
    assert "analysis_type" not in req.model_dump()  # accepted and ignored

    monkeypatch.setenv("OPENAI_API_KEY", "server-key")
    clear_settings_cache()
    try:
        orch = AnalysisOrchestrator(backend=FakeBackend())
        base = {
            "run_id": "r",
            "user_id": "u",
            "problem_description": {},
            "data": pd.DataFrame(),
            "target_column": "y",
            "predictor_columns": [],
        }
        assert orch._wants_literature(AnalysisContext(**base))  # server keys
        assert not orch._wants_literature(
            AnalysisContext(**base, user_llm=UserLLM(api_key="gemini"))
        )
        assert orch._wants_literature(
            AnalysisContext(**base, user_llm=UserLLM(api_key="gemini", openai_key="openai"))
        )
    finally:
        clear_settings_cache()


def test_run_usage_is_priced_per_model_with_cache_and_web_searches(monkeypatch):
    from backend.infrastructure.monitoring.llm_costs import WEB_SEARCHES_KEY, summarize

    with dspy.track_usage() as usage:
        tracker = dspy.settings.usage_tracker
        tracker.add_usage(
            "openai/gpt-6.1-sol",
            {
                "prompt_tokens": 1_000_000,
                "completion_tokens": 100_000,
                "prompt_tokens_details": {"cached_tokens": 400_000},
                "completion_tokens_details": {"reasoning_tokens": 60_000},
            },
        )
        # Responses API usage shape, plus the searches of that call
        tracker.add_usage("openai/gpt-6.1-sol", {"input_tokens": 10_000, "output_tokens": 1_000})
        tracker.add_usage("openai/gpt-6.1-sol", {WEB_SEARCHES_KEY: 7})
        tracker.add_usage("openai/gpt-5.5-2026-04-23", {"prompt_tokens": 1_000_000})
        tracker.add_usage("gemini/gemini-3.1-pro-preview", {"prompt_tokens": 5})
    s = summarize(usage)
    sol = s["models"]["openai/gpt-6.1-sol"]
    assert sol["calls"] == 2 and sol["web_search_calls"] == 7
    assert sol["input_tokens"] == 1_010_000 and sol["cached_input_tokens"] == 400_000
    assert sol["reasoning_tokens"] == 60_000
    # 610k uncached * $2 + 400k cached * $0.10 + 101k out * $10, per 1M; 7 searches * $0.01
    assert sol["cost_usd"] == pytest.approx(1.22 + 0.04 + 1.01 + 0.07)
    assert s["models"]["openai/gpt-5.5-2026-04-23"]["cost_usd"] == pytest.approx(5.0)
    assert s["unpriced_models"] == ["gemini/gemini-3.1-pro-preview"]
    assert s["total_cost_usd"] == pytest.approx(sol["cost_usd"] + 5.0)

    monkeypatch.setenv("LLM_PRICES_JSON", '{"gemini-3.1-pro-preview": [2, 0.2, 12]}')
    assert summarize(usage)["unpriced_models"] == []


def test_stored_activity_keeps_the_whole_run_and_every_result_event():
    from backend.services.discovery.report import MAX_STORED_EVENTS, stored_activity

    short = [{"kind": "thought", "text": str(i)} for i in range(300)]
    assert stored_activity(short) == short  # no longer only the last 200
    events = [
        {"kind": "fit" if i % 10 == 0 else "thought", "text": str(i)}
        for i in range(MAX_STORED_EVENTS + 500)
    ]
    kept = stored_activity(events)
    assert len(kept) == MAX_STORED_EVENTS
    assert sum(e["kind"] == "fit" for e in kept) == sum(e["kind"] == "fit" for e in events)
    assert kept[-1] == events[-1]  # the newest narration stays


def test_citation_titles_reach_the_explanation_cards():
    from backend.services.discovery.report import attach_citation_titles

    literature = {
        "laws": [
            {
                "citations": ["https://doi.org/10.1/a", "https://doi.org/10.1/b"],
                "citation_titles": ["Light response of photosynthesis", ""],
            }
        ]
    }
    explanations = {
        "equations": [
            {"citations": ["https://doi.org/10.1/b", "https://doi.org/10.1/a"]},
            {"citations": []},
        ]
    }
    out = attach_citation_titles(explanations, literature)
    assert out["equations"][0]["citation_titles"] == ["", "Light response of photosynthesis"]
    assert "citation_titles" not in out["equations"][1]
    assert attach_citation_titles({"error": "x"}, None) == {"error": "x"}  # old runs untouched
