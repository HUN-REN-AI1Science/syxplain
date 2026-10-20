"""The agent loop: resilience, guarded finish, live state, compaction, report coercion."""

import asyncio
import json

import dspy
from dspy.utils.dummies import DummyLM

from backend.services.discovery import agent as agent_mod
from backend.services.discovery.agent import (
    BudgetedReAct,
    parse_report,
    run_discovery_agent,
)
from backend.services.discovery.session import DiscoverySession
from backend.services.discovery.tools import build_tools
from backend.tests.test_discovery_session import GOOD_FRONT, FakeLauncher, _data

STRICT = dspy.ChatAdapter(use_json_adapter_fallback=False)


def _session(launcher=None):
    df = _data()
    return DiscoverySession(df, "yield", [c for c in df.columns if c != "yield"], launcher=launcher)


def _report(**kw):
    base = {"summary": "Mitscherlich in P scaled by pH.", "recommended_models": []}
    return {"reasoning": "r", "report_json": json.dumps(base | kw)}


def _run(session, answers, max_iters=10, lm=None):
    async def scenario():
        await session.ensure_profile()
        with dspy.settings.context(adapter=STRICT):
            return await run_discovery_agent(
                session,
                build_tools(session),
                lm or DummyLM(answers),
                {"project_description": "test"},
                max_iters=max_iters,
            )

    return asyncio.run(scenario())


FIT_P = {
    "next_thought": "Screen saturating forms on P first.",
    "next_tool_name": "fit_families",
    "next_tool_args": {"families": ["mitscherlich"], "features": ["P_added"]},
}
FINISH = {"next_thought": "Done.", "next_tool_name": "finish", "next_tool_args": {}}


def test_full_loop_with_formula_notes_and_report():
    s = _session()
    report = _run(
        s,
        [
            FIT_P,
            {
                "next_thought": "Residuals depend on pH; scale the maximum by pH.",
                "next_tool_name": "fit_formula",
                "next_tool_args": {
                    "expression": "a*(1 - exp(-c*(P_added + b)))*pH",
                    "initial_params": {"a": 10, "b": 0, "c": 0.03},
                    "label": "Mitscherlich x pH",
                },
            },
            {
                "next_thought": "Record why the plain form fails.",
                "next_tool_name": "note",
                "next_tool_args": {
                    "entries": [
                        {
                            "kind": "rejected_form",
                            "text": "Mitscherlich on P misses pH",
                            "model_ids": ["C1"],
                        },
                        {"kind": "insight", "text": "pH scales the maximum", "model_ids": ["M2"]},
                    ]
                },
            },
            FINISH,
            _report(
                recommended_models=[{"model_id": "M2", "why": "at noise level"}, {"model_id": "X9"}]
            ),
        ],
    )
    assert report["source"] == "agent" and report["ended"] == "finish" and report["steps"] == 4
    assert [r["model_id"] for r in report["recommended_models"]] == ["M2"]
    assert s.models["M2"].cv_r2 > 0.95 and s.models["C1"].verdict == "poor"
    assert [n["kind"] for n in s.notebook] == ["rejected_form", "insight"]
    assert s.steps_used == 4


def test_invalid_step_becomes_corrective_observation():
    s = _session()
    bad = {"next_thought": "oops", "next_tool_name": "fit_family", "next_tool_args": {}}
    report = _run(
        s,
        [
            FIT_P,
            bad,
            {"next_thought": "list", "next_tool_name": "leaderboard", "next_tool_args": {}},
            FINISH,
            _report(recommended_models=[{"model_id": "C1", "why": "x"}]),
        ],
    )
    assert report["source"] == "agent" and report["ended"] == "finish"
    assert report["steps"] == 4  # fit, invalid, leaderboard, finish


def test_unparseable_report_falls_back_to_session_state():
    s = _session()
    report = _run(s, [FIT_P, FINISH, {"reasoning": "r", "report_json": "not json at all {"}])
    assert report["source"] == "auto_fallback"
    assert report["recommended_models"] or not any(m.verdict != "poor" for m in s.models.values())
    assert all(r["model_id"] in s.models for r in report["recommended_models"])


def test_transient_lm_error_is_retried(monkeypatch):
    from dspy.utils.exceptions import LMRateLimitError

    monkeypatch.setattr(agent_mod, "BACKOFF_S", (0, 0, 0))

    class FlakyLM(DummyLM):
        calls = 0

        async def aforward(self, *args, **kwargs):
            FlakyLM.calls += 1
            if FlakyLM.calls == 1:
                raise LMRateLimitError("slow down")
            return await super().aforward(*args, **kwargs)

    s = _session()
    report = _run(
        s, [], lm=FlakyLM([FIT_P, FINISH, _report(recommended_models=[{"model_id": "C1"}])])
    )
    assert report["ended"] == "finish" and "C1" in s.models


def test_finish_is_refused_while_results_are_unread():
    s = _session(FakeLauncher(equations=GOOD_FRONT, delay=0.05))

    async def scenario():
        await s.ensure_profile()
        await s.start_search(["P_added", "pH"], ["exp"], ["+", "*"], enforce_budget=False)
        lm = DummyLM(
            [
                FIT_P,
                FINISH,
                {
                    "next_thought": "wait",
                    "next_tool_name": "wait_for_searches",
                    "next_tool_args": {},
                },
                {
                    "next_thought": "read",
                    "next_tool_name": "search_results",
                    "next_tool_args": {"search_id": "pysr_1"},
                },
                FINISH,
                _report(recommended_models=[{"model_id": "C1"}]),
            ]
        )
        agent = BudgetedReAct(
            agent_mod.EquationDiscoveryAgent, build_tools(s), session=s, max_iters=10
        )
        with dspy.settings.context(lm=lm, adapter=STRICT):
            pred = await agent.acall(
                project_description="{}", data_overview="{}", budget="{}", initial_searches="[]"
            )
        return pred, agent

    pred, agent = asyncio.run(scenario())
    traj = pred.trajectory
    refusal = traj["observation_1"]
    assert "pysr_1" in refusal and "wait_for_searches" in refusal
    assert agent.ended == "finish"
    assert s.searches["pysr_1"].read_at is not None
    assert any(
        "[event] pysr_1 completed" in str(v)
        for k, v in traj.items()
        if k.startswith("observation_")
    )


def test_trajectory_compaction_keeps_recent_steps_verbatim():
    s = _session()
    agent = BudgetedReAct(agent_mod.EquationDiscoveryAgent, build_tools(s), session=s, max_iters=30)
    traj = {}
    for i in range(20):
        traj[f"thought_{i}"] = "thinking " * 40
        traj[f"tool_name_{i}"] = "fit_families"
        traj[f"tool_args_{i}"] = {"families": ["linear"], "features": ["pH"]}
        # realistic size: a fit_families reply with several briefs (~2k chars)
        traj[f"observation_{i}"] = json.dumps(
            {
                "results": [
                    {"model_id": f"C{i}", "cv_r2": 0.5, "verdict": "poor", "reasons": ["x" * 400]}
                ]
                + [{"model_id": f"C{i}{j}", "reasons": ["y" * 400]} for j in range(4)]
            },
            separators=(",", ":"),
        )
    full = dspy.ReAct._format_trajectory(agent, traj)
    compact = agent._format_trajectory(traj)
    assert len(compact) <= 0.4 * len(full)
    for i in range(14, 20):
        assert traj[f"observation_{i}"] in compact
    assert "C3 cv_r2=0.5 poor" in compact


def test_parse_report_coerces_shapes():
    s = _session()
    s.profile()
    m = s.fit_family("linear", ["pH"])
    report = parse_report(
        json.dumps(
            {
                "summary": "x",
                "recommended_models": [m.model_id, {"model_id": "Z1"}],
                "insights": [{"text": "a", "evidence": m.model_id}],
                "open_questions": [{"q": 1}],
                "rejected_forms": ["power"],
            }
        ),
        s,
    )
    assert report["recommended_models"] == [{"model_id": m.model_id, "why": ""}]
    assert report["insights"] == [f"a — {m.model_id}"]
    assert report["open_questions"] == ["q: 1"]
    assert report["rejected_forms"] == [{"form": "power", "model_id": None, "reason": ""}]


def test_tools_schema_uses_enums():
    s = _session()
    tools = {t.__name__: dspy.Tool(t) for t in build_tools(s)}
    assert tools["fit_families"].args["target_transform"]["enum"] == [
        "none",
        "log",
        "log1p",
        "sqrt",
    ]
    assert "enum" in tools["start_pysr_search"].args["unary_operators"]["items"]
    assert "guess_model_ids" in tools["start_pysr_search"].args
