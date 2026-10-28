"""Orchestrator (run controller): the full discovery phase sequence with a fake Slurm backend."""

import asyncio
import json

import dspy
import numpy as np
import pandas as pd
import pytest
from dspy.utils.dummies import DummyLM

from backend.core.config import clear_settings_cache
from backend.core.constants import RunStatus
from backend.infrastructure.slurm import JobState, SlurmTask, TaskResult
from backend.services import llm_service
from backend.services.discovery.session import DiscoverySession
from backend.services.orchestrator_service import AnalysisContext, AnalysisOrchestrator

STRICT = dspy.ChatAdapter(use_json_adapter_fallback=False)


class FakeBackend:
    name = "fake"

    def __init__(self, delay=0.01):
        self.inputs: dict[str, dict] = {}
        self.cancelled: list[str] = []
        self.delay = delay

    async def submit_task(self, task):
        self.inputs[task.key] = task.input_data
        return SlurmTask(
            job_id=task.key, slurm_job_id="1", task_type=task.task_type, run_id=task.run_id
        )

    async def wait_for_completion(self, job_id, **kwargs):
        await asyncio.sleep(self.delay)
        return TaskResult(job_id=job_id, state=JobState.COMPLETED)

    async def get_task_result(self, job_id):
        feats = self.inputs[job_id]["predictor_columns"]
        return {
            "status": "success",
            "equations": [
                {"equation": f"2.0 * {feats[0]} + 1.0", "complexity": 5, "loss": 1.0},
                {
                    "equation": f"5.1 * {feats[0]} / (2.1 + {feats[0]})",
                    "complexity": 7,
                    "loss": 0.01,
                },
            ],
        }

    async def cancel_task(self, job_id):
        self.cancelled.append(job_id)


class StubProgress:
    run_id = "run-1"
    current_progress = 0

    def __init__(self):
        self.steps: list[str] = []

    async def update_progress_async(self, step_name, status=None, details=None):
        self.steps.append(step_name)

    async def set_progress_async(self, progress, step_name=None):
        self.current_progress = progress

    def set_progress(self, progress, status=None):
        self.current_progress = progress


@pytest.fixture
def orchestrator(monkeypatch):
    monkeypatch.setenv("DISCOVERY_WALL_CLOCK_MIN", "5")
    monkeypatch.setenv("DISCOVERY_REVIEW_STEPS", "0")
    clear_settings_cache()
    o = AnalysisOrchestrator(backend=FakeBackend())
    monkeypatch.setattr(o, "_is_run_terminal", lambda run_id: None)
    monkeypatch.setattr(o, "_store_slurm_job_ids", lambda run_id, ids: None)
    # No real web search in tests; the literature tests switch it on with a fake lookup
    monkeypatch.setattr(o, "_wants_literature", lambda ctx: False)
    yield o
    clear_settings_cache()


def _context(**kw):
    rng = np.random.default_rng(0)
    x = rng.uniform(1, 10, 300)
    z = rng.uniform(0, 1, 300)
    df = pd.DataFrame(
        {"dose [mg]": x, "z": z, "response": 5 * x / (2 + x) + rng.normal(0, 0.1, 300)}
    )
    return AnalysisContext(
        run_id="run-1",
        user_id="u",
        problem_description={
            "project_description": "dose response",
            "target_variable": "response",
            "features": {"dose [mg]": "administered dose", "z": "nuisance"},
        },
        data=df,
        target_column="response",
        predictor_columns=["dose [mg]", "z"],
        **kw,
    )


PYSR_CONFIG = {"unary_operators": ["exp", "bogus"], "binary_operators": ["+", "*"], "maxsize": 15}
FINISH = {"next_thought": "Done.", "next_tool_name": "finish", "next_tool_args": {}}


def _step(thought, tool, **args):
    return {"next_thought": thought, "next_tool_name": tool, "next_tool_args": args}


def test_discovery_with_agent(orchestrator, monkeypatch):
    lm = DummyLM(
        [
            _step(
                "Saturating; try MM.",
                "fit_families",
                families=["michaelis_menten", "linear"],
                features=["dose"],
            ),
            _step(
                "Target PySR on dose.",
                "start_pysr_search",
                features=["dose"],
                unary_operators=[],
                binary_operators=["+", "*", "/"],
                guesses=["5*dose/(2 + dose)"],
            ),
            _step("Nothing else to fit.", "wait_for_searches"),
            _step("Read baseline.", "search_results", search_id="pysr_1"),
            _step("Read targeted.", "search_results", search_id="pysr_2"),
            FINISH,
            {
                "reasoning": "r",
                "report_json": json.dumps(
                    {"summary": "MM fits", "recommended_models": [{"model_id": "C3", "why": "law"}]}
                ),
            },
        ]
    )
    monkeypatch.setattr(orchestrator, "_discovery_lm", lambda ctx, name: lm)
    progress = StubProgress()

    async def run():
        with dspy.settings.context(adapter=STRICT):
            return await orchestrator._run_discovery(_context(), PYSR_CONFIG, progress)

    results = asyncio.run(run())
    backend = orchestrator.backend
    assert set(backend.inputs) == {"pysr_1", "pysr_2"}
    assert backend.inputs["pysr_1"]["config"]["unary_operators"] == ["exp"]  # unknown op dropped
    assert backend.inputs["pysr_2"]["guesses"] == ["5*dose/(2 + dose)"]
    assert progress.steps[-4:] == [
        "compute_submission",
        "discovery_agent",
        "discovery_wrapup",
        "final_scoring",
    ]
    d = results["discovery"]
    assert d["agent"]["summary"] == "MM fits" and d["agent"]["error"] is None
    assert d["agent"]["stale"] is False and set(d["agent"]["reviewed_searches"]) == {
        "pysr_1",
        "pysr_2",
    }
    assert {s["status"] for s in d["searches"]} == {"completed"}
    assert d["aliases"]["dose"] == "dose [mg]"
    assert d["selection"]["headline_model_id"] is not None
    assert results["best_equation"]["is_headline"]
    assert results["warnings"] == []
    json.dumps(results, allow_nan=False)


def test_agent_crash_falls_back(orchestrator, monkeypatch):
    def broken_lm(ctx, name):
        raise RuntimeError("model not found")

    monkeypatch.setattr(orchestrator, "_discovery_lm", broken_lm)
    results = asyncio.run(orchestrator._run_discovery(_context(), PYSR_CONFIG, StubProgress()))
    d = results["discovery"]
    assert "model not found" in d["agent"]["error"]
    assert d["agent"]["source"] == "auto_fallback"
    assert [s["search_id"] for s in d["searches"]] == ["pysr_1"]
    assert any(e["kind"] == "classic" for e in d["leaderboard"])  # auto-screen ran
    assert results["equations"] and results["best_equation"]
    assert results["warnings"][0]["stage"] == "agent"


def test_failure_after_launch_cancels_searches(orchestrator, monkeypatch):
    orchestrator._backend = FakeBackend(delay=30)

    async def boom(self, timeout_s=240):
        raise RuntimeError("profiling exploded")

    monkeypatch.setattr(DiscoverySession, "ensure_profile", boom)
    with pytest.raises(RuntimeError, match="exploded"):
        asyncio.run(orchestrator._run_discovery(_context(), PYSR_CONFIG, StubProgress()))
    assert orchestrator.backend.cancelled == ["pysr_1"]


@pytest.mark.parametrize("user_key", [None, "user-gemini-key"])
def test_explanation_failure_still_completes(orchestrator, monkeypatch, user_key):
    monkeypatch.setenv("DISCOVERY_AGENT_ENABLED", "false")
    clear_settings_cache()
    statuses = []

    def update(run_id, status, results=None, error=None):
        statuses.append((status, results, error))
        return True

    monkeypatch.setattr(orchestrator, "_update_run_status", update)
    monkeypatch.setattr(orchestrator, "_store_results", lambda run_id, results: None)
    monkeypatch.setattr(orchestrator, "_save_artifacts", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator, "_generate_feature_visualizations", lambda ctx: [])

    async def config(*a, **k):
        return PYSR_CONFIG

    monkeypatch.setattr(orchestrator, "_generate_pysr_config", config)

    def explode(**kwargs):
        raise RuntimeError("explainer down")

    monkeypatch.setattr(llm_service, "generate_equation_explanation", explode)
    ctx = _context(user_api_key=user_key, progress=StubProgress())
    results = asyncio.run(orchestrator.run_analysis(ctx))

    assert statuses[-1][0] == RunStatus.COMPLETED
    assert results["discovery"] and results["equations"]
    assert results["warnings"][-1]["stage"] == "explanation"
    assert "explainer down" in results["warnings"][-1]["message"]
    assert results["explanations"]["error"]


def test_compile_joins_narration_by_model_id(orchestrator):
    equations = [
        {
            "equation": "(-62.03) + 75.08*(1 - exp(-0.08171*P))",
            "model_id": "C3",
            "origin": "classic: Mitscherlich",
            "holdout_r2": 0.9,
            "scatter_data": {"measured": [1.0], "predicted": [1.1]},
            "is_headline": True,
        },
        {
            "equation": "a*P",
            "model_id": "S12",
            "origin": "symbolic",
            "holdout_r2": 0.5,
            "is_headline": False,
        },
        {
            "equation": "P^2",
            "model_id": "M4",
            "origin": "custom: sq",
            "holdout_r2": 0.1,
            "is_headline": False,
        },
    ]
    explanations = {
        "equations": [
            {"id": 1, "equation": "-62.03 + 75.08*(1-exp(-0.08171*P))", "overview": "law"},
            {"id": 2, "model_id": "S12", "equation": "something else", "overview": "sym"},
        ],
        "summary": {},
        "recommendation": {"equation_id": None, "rationale": []},
    }
    discovery = {"equations": equations, "discovery": {"literature": {"x": float("nan")}}}
    final = orchestrator._compile_final_results(_context(), discovery, explanations, [])
    cards = final["explanations"]["equations"]
    assert [c["model_id"] for c in cards] == ["C3", "S12", "M4"]
    assert cards[0]["scatter_data"] and cards[0]["equation"] == equations[0]["equation"]
    assert cards[1]["origin"] == "symbolic" and cards[2]["overview"] == ""
    assert final["explanations"]["recommendation"]["equation_id"] == 1
    assert final["discovery"]["literature"]["x"] is None
    json.dumps(final, allow_nan=False)


def test_literature_called_once_with_target(orchestrator, monkeypatch):
    monkeypatch.setattr(orchestrator, "_wants_literature", lambda ctx: True)
    monkeypatch.setenv("DISCOVERY_AGENT_ENABLED", "false")
    clear_settings_cache()
    calls, deep_contexts = [], []

    def research(features_dict, model_name=None, user_api_key=None):
        calls.append(features_dict)
        return {"equations": [{"equation": "response = a*dose/(b + dose)", "citations": ["c"]}]}

    def explain(**kwargs):
        deep_contexts.append(kwargs["literature_context"])
        return {"equations": [], "summary": {}, "recommendation": {}}

    monkeypatch.setattr(llm_service, "find_literature_laws", research)
    monkeypatch.setattr(llm_service, "generate_equation_explanation", explain)
    ctx = _context()

    async def run():
        progress = StubProgress()
        results = await orchestrator._run_discovery(ctx, PYSR_CONFIG, progress)
        warnings = results.pop("warnings")
        explanations = await orchestrator._narrate(ctx, results, progress, warnings)
        return results, explanations, warnings

    results, _explanations, warnings = asyncio.run(run())
    assert len(calls) == 1
    assert calls[0]["response"].startswith("TARGET variable")
    law = results["discovery"]["literature"]["laws"][0]
    assert law["model_id"].startswith("L") and law["cv_r2"] > 0.9
    assert deep_contexts[0]["equations"][0]["model_id"] == law["model_id"]
    assert not warnings


def test_no_laws_found_warns_and_explains_plainly(orchestrator, monkeypatch):
    monkeypatch.setattr(orchestrator, "_wants_literature", lambda ctx: True)
    monkeypatch.setenv("DISCOVERY_AGENT_ENABLED", "false")
    clear_settings_cache()
    deep_contexts = []
    monkeypatch.setattr(
        llm_service,
        "find_literature_laws",
        lambda **k: {"equations": [], "_parse_error": "x"},
    )
    monkeypatch.setattr(
        llm_service,
        "generate_equation_explanation",
        lambda **k: deep_contexts.append(k["literature_context"]) or {"equations": []},
    )
    ctx = _context()

    async def run():
        progress = StubProgress()
        results = await orchestrator._run_discovery(ctx, PYSR_CONFIG, progress)
        warnings = results.pop("warnings")
        await orchestrator._narrate(ctx, results, progress, warnings)
        return results, warnings

    results, warnings = asyncio.run(run())
    assert results["discovery"]["literature"]["status"] == "empty"
    assert warnings[0]["stage"] == "literature"
    assert deep_contexts == [None]
