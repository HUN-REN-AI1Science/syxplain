"""The MCP endpoint: access control and the analysis tools."""

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from slowapi.middleware import SlowAPIMiddleware
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from backend.api.mcp import server as mcp_server
from backend.core.config import get_settings
from backend.core.constants import RunStatus
from backend.core.exceptions import EntityNotFoundError, FileValidationError
from backend.core.security import User
from backend.services.submission_service import Submission

USER_ID = "00000000-0000-0000-0000-000000000003"
HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}
RUN = SimpleNamespace(
    id="run-1",
    status=RunStatus.COMPLETED,
    progress=100,
    problem_description={"target_variable": "y"},
    created_at=datetime(2026, 11, 10, 10, 0),
    finish_time=datetime(2026, 11, 10, 10, 14),
    error=None,
    results={
        "best_equation": {"model_id": "S1", "equation": "2 * x", "holdout_r2": 0.9},
        "equations": [{"model_id": "S1", "equation": "2 * x", "scatter_data": {"a": [1] * 99}}],
        "warnings": [],
    },
)


class FakeRunService:
    def __init__(self):
        self.cancelled = []
        self.file_repo = object()

    def get_run_for_user(self, run_id, user_id):
        if run_id != "run-1" or user_id != USER_ID:
            raise EntityNotFoundError("Run", run_id)
        return RUN

    def list_runs(self, user_id, page, page_size):
        return SimpleNamespace(total=1, items=[RUN][:page_size])

    async def cancel_run(self, run_id, user_id):
        self.get_run_for_user(run_id, user_id)
        self.cancelled.append(run_id)


@pytest.fixture
def mcp(monkeypatch):
    """A client of the MCP app; `mcp.user` is who the credentials resolve to (None = 401)."""
    state = SimpleNamespace(
        user=User(USER_ID, "service-account-adp", [get_settings().auth.server_keys_role]),
        runs=FakeRunService(),
        submitted=[],
        credentials=None,
    )

    def authenticate(api_key, bearer):
        state.credentials = (api_key, bearer)
        if state.user is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return state.user

    @contextmanager
    def run_service():
        yield state.runs

    async def submit(**kwargs):
        state.submitted.append(kwargs)
        return Submission(run_id="run-2", row_count=3, renamed_columns={"a b": "a_b"})

    monkeypatch.setattr(mcp_server, "authenticate_credentials", authenticate)
    monkeypatch.setattr(mcp_server, "_run_service", run_service)
    monkeypatch.setattr(mcp_server, "submit_analysis", submit)
    mcp_server.limiter.reset()

    server, asgi = mcp_server.build_mcp()
    app = Starlette(
        routes=[Route(mcp_server.MCP_PATH, endpoint=asgi)],
        lifespan=lambda app: server.session_manager.run(),
    )
    # The backend's middleware around the endpoint (the rate limiter inspects it)
    app.state.limiter = mcp_server.limiter
    app.add_middleware(SlowAPIMiddleware)
    with TestClient(app) as client:

        def rpc(method, params=None, headers=None):
            body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
            sent = HEADERS | ({"X-API-Key": "syxp_test"} if headers is None else headers)
            return client.post(mcp_server.MCP_PATH, json=body, headers=sent)

        def call(name, arguments):
            response = rpc("tools/call", {"name": name, "arguments": arguments})
            assert response.status_code == 200
            return response.json()["result"]

        state.rpc, state.call = rpc, call
        yield state


ANALYSIS = {
    "csv_text": "a b,y\n1,2\n2,4\n3,6\n",
    "project_description": "y from a b",
    "target_variable": "y",
    "features": {"a b": "the predictor"},
}


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------


def test_requests_without_valid_credentials_are_refused(mcp):
    mcp.user = None
    response = mcp.rpc("tools/list", headers={})
    assert response.status_code == 401 and response.json()["error"] == "unauthorized"
    assert mcp.credentials == (None, None)


def test_accounts_without_server_keys_are_refused(mcp):
    mcp.user = User(USER_ID, "a@b.hu", [])
    response = mcp.rpc("tools/list")
    assert response.status_code == 403 and "server-key" in response.json()["message"]


def test_both_credential_headers_reach_authentication(mcp):
    assert mcp.rpc("tools/list").status_code == 200
    assert mcp.credentials == ("syxp_test", None)
    assert mcp.rpc("tools/list", headers={"Authorization": "Bearer eyJ.a.b"}).status_code == 200
    assert mcp.credentials == (None, "eyJ.a.b")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def test_tools_take_no_llm_settings(mcp):
    tools = {t["name"]: t for t in mcp.rpc("tools/list").json()["result"]["tools"]}
    assert set(tools) == {
        "start_analysis",
        "get_analysis_status",
        "get_analysis_results",
        "list_analyses",
        "cancel_analysis",
    }
    start = tools["start_analysis"]["inputSchema"]
    assert set(start["properties"]) == {
        "csv_text",
        "project_description",
        "target_variable",
        "features",
        "dataset_name",
        "literature_text",
    }
    assert set(start["required"]) == {
        "csv_text",
        "project_description",
        "target_variable",
        "features",
    }


def test_start_analysis_submits_the_inline_csv(mcp):
    result = mcp.call("start_analysis", ANALYSIS | {"dataset_name": "Soil trial / 2026"})
    assert not result.get("isError")
    assert result["structuredContent"]["run_id"] == "run-2"
    assert result["structuredContent"]["renamed_columns"] == {"a b": "a_b"}

    (sent,) = mcp.submitted
    assert sent["user"] is mcp.user
    assert sent["filename"] == "Soil_trial___2026.csv"
    assert sent["file_obj"].read() == ANALYSIS["csv_text"].encode()
    params = sent["params"]
    assert params.target_variable == "y" and params.features == {"a b": "the predictor"}
    assert params.api_key is None


def test_start_analysis_refuses_large_tables(mcp, monkeypatch):
    monkeypatch.setattr(get_settings().analysis, "mcp_max_csv_kb", 1)
    result = mcp.call("start_analysis", ANALYSIS | {"csv_text": "a b,y\n" + "1,2\n" * 400})
    assert result["isError"] and "larger than 1 kB" in result["content"][0]["text"]
    assert mcp.submitted == []


def test_refusals_reach_the_model_as_readable_errors(mcp, monkeypatch):
    async def reject(**kwargs):
        raise FileValidationError(message="Target variable 'y' does not exist in the uploaded file")

    monkeypatch.setattr(mcp_server, "submit_analysis", reject)
    result = mcp.call("start_analysis", ANALYSIS)
    assert result["isError"] and "does not exist" in result["content"][0]["text"]


def test_status_and_results_of_a_run(mcp):
    status = mcp.call("get_analysis_status", {"run_id": "run-1"})["structuredContent"]
    assert status["status"] == "completed" and status["progress"] == 100
    assert status["phase"] is None and status["finish_time"] == "2026-11-10T10:14:00"

    results = mcp.call("get_analysis_results", {"run_id": "run-1"})["structuredContent"]
    assert results["summary"]["headline"] == {
        "model_id": "S1",
        "equation": "2 * x",
        "holdout_r2": 0.9,
    }
    assert "scatter_data" not in results["summary"]["equations"][0]

    listing = mcp.call("list_analyses", {})["structuredContent"]
    assert listing["total"] == 1 and listing["analyses"][0]["run_id"] == "run-1"


def test_unknown_runs_and_cancellation(mcp):
    missing = mcp.call("get_analysis_status", {"run_id": "nope"})
    assert missing["isError"] and "No analysis" in missing["content"][0]["text"]

    assert not mcp.call("cancel_analysis", {"run_id": "run-1"}).get("isError")
    assert mcp.runs.cancelled == ["run-1"]
    assert mcp.call("cancel_analysis", {"run_id": "nope"})["isError"]
