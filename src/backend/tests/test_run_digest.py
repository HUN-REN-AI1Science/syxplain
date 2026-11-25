"""The compact run summary served by /api/v1/runs/{id}/summary and the MCP result tool."""

import json
from types import SimpleNamespace

from backend.core.constants import RunStatus
from backend.services.run_digest import (
    MAX_DIGEST_EQUATIONS,
    build_run_digest,
    phase_for,
    run_digest_payload,
    run_warnings,
)


def _equation(i: int, headline: bool = False) -> dict:
    return {
        "model_id": f"S{i}",
        "equation": f"{i} * x",
        "origin": "symbolic",
        "complexity": 3,
        "holdout_r2": 0.8,
        "cv_rmse": 1.5,
        "verdict": "ok",
        "is_headline": headline,
        "scatter_data": {"actual": list(range(500)), "predicted": list(range(500))},
        "loss": 0.1,
    }


def _results(series: dict | None = None) -> dict:
    equations = [_equation(1, headline=True)] + [_equation(i) for i in range(2, 15)]
    return {
        "equations": equations,
        "best_equation": equations[0],
        "scatter_data": {"1 * x": {"actual": [1.0] * 500}},
        "explanations": {
            "equations": [
                {"model_id": "S1", "overview": "linear in x", "term_explanations": []},
                {"model_id": "S2", "overview": "other"},
            ],
            "summary": {"key_drivers": ["x"], "findings": "x drives y"},
            "recommendation": {"equation_id": 1, "rationale": ["simple"]},
        },
        "discovery": {
            "target": {"alias": "y", "column": "y"},
            "split": {"train": 96, "holdout": 23, "has_holdout": True, "missing_by_column": {}},
            "series": series,
            "n_models_total": 87,
            "leaderboard": [{"model_id": f"C{i}"} for i in range(40)],
            "activity": [{"event": "x"}] * 2000,
            "notebook": ["note"] * 100,
            "agent": {"summary": "found a linear law", "steps": 31, "insights": ["a"]},
            "literature": {
                "status": "ok",
                "laws": [{"equation": "y = k*x", "cv_r2": 0.7, "model_id": "L1"}] * 12,
            },
            "relations": {"n_known_laws": {"classic": 3}, "headline": [{"r": i} for i in range(9)]},
        },
        "warnings": [{"stage": "literature", "message": "skipped"}],
        "usage": {"total_cost_usd": 0.84, "models": {}},
        "completed_at": "2026-11-10T10:13:42",
    }


def test_digest_keeps_the_outcome_and_drops_the_bulk():
    full = _results()
    digest = build_run_digest(full)

    assert digest["headline"]["equation"] == "1 * x"
    assert digest["headline"]["holdout_r2"] == 0.8
    assert len(digest["equations"]) == MAX_DIGEST_EQUATIONS
    assert all("scatter_data" not in e for e in digest["equations"])
    assert digest["data"]["train"] == 96 and digest["data"]["holdout"] == 23
    assert digest["n_models_fitted"] == 87
    assert digest["agent"] == {"summary": "found a linear law", "insights": ["a"]}
    assert digest["literature"]["n_laws"] == 12 and len(digest["literature"]["laws"]) == 8
    assert len(digest["known_laws"]["headline_relations"]) == 5
    assert digest["explanation"]["summary"]["key_drivers"] == ["x"]
    assert digest["explanation"]["headline"]["overview"] == "linear in x"
    assert digest["warnings"] == [{"stage": "literature", "message": "skipped"}]
    assert digest["llm_cost_usd"] == 0.84
    assert "series" not in digest  # not a time series
    # An order of magnitude smaller than the stored results
    assert len(json.dumps(digest)) * 10 < len(json.dumps(full))


def test_digest_reports_the_series_feature_stage():
    series = {
        "time_column": "year",
        "group_column": None,
        "n_series": 1,
        "time_step": 1.0,
        "lag_features": [
            {
                "feature": "rain_lag1",
                "description": "rain one year earlier",
                "reason": "carry-over of soil water",
                "padded_rows": 1,
                "values": [0.0] * 300,
            }
        ],
        "padded_rows": 1,
        "feature_stage": {"status": "ok", "rationale": "water carries over", "candidates": []},
    }
    digest = build_run_digest(_results(series))
    assert digest["series"]["time_column"] == "year"
    assert digest["series"]["derived_features"] == [
        {
            "feature": "rain_lag1",
            "description": "rain one year earlier",
            "reason": "carry-over of soil water",
            "padded_rows": 1,
        }
    ]
    assert digest["series"]["feature_stage"] == {"status": "ok", "rationale": "water carries over"}


def test_digest_survives_partial_and_failed_sections():
    assert build_run_digest(None)["headline"] is None
    assert build_run_digest({})["equations"] == []

    results = _results()
    results["explanations"] = {"error": "LLM unavailable", "equations": []}
    del results["discovery"]["literature"]
    results["discovery"]["relations"] = None
    digest = build_run_digest(results)
    assert digest["explanation"] == {"error": "LLM unavailable"}
    assert "literature" not in digest and "known_laws" not in digest

    assert run_warnings({"warnings": "broken"}) == []
    assert run_warnings(None) == []


def test_phase_follows_the_progress_config():
    assert phase_for(RunStatus.PENDING, 0)["name"] == "queued"
    assert phase_for(RunStatus.RUNNING, 0)["name"] == "initialization"
    assert phase_for(RunStatus.RUNNING, 50)["name"] == "discovery_agent"
    assert phase_for(RunStatus.RUNNING, 90)["name"] == "llm_explanation"
    assert phase_for(RunStatus.COMPLETED, 100) is None
    assert phase_for(RunStatus.FAILED, 40) is None


def test_payload_has_no_summary_before_results_exist():
    run = SimpleNamespace(
        id="r1",
        status=RunStatus.RUNNING,
        progress=12,
        problem_description={"target_variable": "y"},
        error=None,
        results=None,
    )
    payload = run_digest_payload(run)
    assert payload["status"] == "running" and payload["summary"] is None
    assert payload["phase"]["name"] == "discovery_agent"
    assert payload["target_variable"] == "y"

    run.results, run.status = _results(), RunStatus.COMPLETED
    assert run_digest_payload(run)["summary"]["headline"]["model_id"] == "S1"
