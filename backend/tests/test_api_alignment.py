"""The programmatic API follows the pipeline: submission, column names, limits, schemas."""

import asyncio
import io
from unittest.mock import MagicMock
from uuid import UUID

import pandas as pd
import pytest

from backend.core.config import get_settings
from backend.core.exceptions import (
    ComputeUnavailableError,
    FileValidationError,
    TooManyActiveRunsError,
)
from backend.core.security import User
from backend.schemas.programmatic import (
    AnalyzeParams,
    AnalyzeResponse,
    ModelsResponse,
    RunStatusResponse,
    RunSummary,
)
from backend.services import submission_service
from backend.services.file_service import FileService
from backend.services.run_service import RunService
from backend.services.submission_service import resolve_column_names, submit_analysis

USER_ID = "00000000-0000-0000-0000-000000000001"
CSV = b"soil pH,organic C (%),yield\n6.1,2.0,3.1\n5.4,1.2,2.2\n7.0,3.3,4.0\n"


def _server_user() -> User:
    return User(USER_ID, "a@b.hu", [get_settings().auth.server_keys_role])


def _params(**overrides) -> AnalyzeParams:
    base = {
        "project_description": "yield from soil",
        "target_variable": "yield",
        "features": {"soil pH": "pH in water", "organic C (%)": "organic carbon"},
    }
    return AnalyzeParams(**(base | overrides))


@pytest.fixture
def submission_env(monkeypatch):
    """A run service on mocked repositories, with server keys configured and Slurm up."""
    run_repo, file_repo = MagicMock(), MagicMock()
    run_repo.count_active_for_user.return_value = 0
    service = RunService(run_repo, file_repo, MagicMock())
    monkeypatch.setattr(service.settings.llm, "openai_api_key", "sk-server")
    started = {}

    def fake_start(**kwargs):
        started.update(kwargs)
        return "run-1"

    async def reachable():
        return True

    monkeypatch.setattr(submission_service, "start_analysis_run", fake_start)
    monkeypatch.setattr(submission_service, "is_slurm_reachable", reachable)
    return service, file_repo, run_repo, started


def _submit(service, file_repo, params, user=None, content=CSV, filename="soil.csv"):
    return asyncio.run(
        submit_analysis(
            user=user or _server_user(),
            filename=filename,
            file_obj=io.BytesIO(content),
            params=params,
            run_service=service,
            file_repo=file_repo,
        )
    )


# ---------------------------------------------------------------------------
# Column names
# ---------------------------------------------------------------------------


def test_upload_reports_renamed_columns():
    _, metadata, _ = FileService().process_upload(io.BytesIO(CSV), "soil.csv")
    assert metadata.columns == ["soil_pH", "organic_C", "yield"]
    assert metadata.renamed_columns == {"soil pH": "soil_pH", "organic C (%)": "organic_C"}

    _, clean, _ = FileService().process_upload(io.BytesIO(b"a,b\n1,2\n"), "clean.csv")
    assert clean.renamed_columns == {}


def test_original_and_sanitized_names_both_resolve():
    renamed = {"soil pH": "soil_pH"}
    assert resolve_column_names("soil pH", {"soil pH": "d", "clay": "c"}, renamed) == (
        "soil_pH",
        {"soil_pH": "d", "clay": "c"},
    )
    assert resolve_column_names("soil_pH", {"soil_pH": "d"}, renamed) == (
        "soil_pH",
        {"soil_pH": "d"},
    )


def test_excel_upload_with_renamed_columns_is_stored_as_csv():
    buffer = io.BytesIO()
    pd.DataFrame({"soil pH": [6.1, 5.4], "yield": [3.1, 2.2]}).to_excel(buffer, index=False)
    service = FileService()
    content, metadata, df = service.process_upload(io.BytesIO(buffer.getvalue()), "soil.xlsx")
    assert metadata.renamed_columns == {"soil pH": "soil_pH"}
    assert metadata.filename == "soil.csv" and metadata.media_type == "text/csv"
    assert list(df.columns) == ["soil_pH", "yield"]
    stored = service.parse_dataframe(content, metadata.filename)
    assert list(stored.columns) == ["soil_pH", "yield"]

    # A workbook that needs no renaming stays an Excel file
    clean = io.BytesIO()
    pd.DataFrame({"pH": [6.1], "y": [3.1]}).to_excel(clean, index=False)
    _, kept, _ = service.process_upload(io.BytesIO(clean.getvalue()), "clean.xlsx")
    assert kept.filename == "clean.xlsx"


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------


def test_submission_accepts_names_as_written_in_the_file(submission_env):
    service, file_repo, _, started = submission_env
    submission = _submit(service, file_repo, _params())

    assert submission.run_id == "run-1" and submission.row_count == 3
    assert submission.renamed_columns == {"soil pH": "soil_pH", "organic C (%)": "organic_C"}
    assert started["problem_desc"]["target_variable"] == "yield"
    assert started["problem_desc"]["features"] == {
        "soil_pH": "pH in water",
        "organic_C": "organic carbon",
    }
    assert started["user_llm"] is None  # server keys
    file_repo.create_file.assert_called_once()
    # The run reads the file stored for it, not the latest of that name
    assert started["file_id"] == str(file_repo.create_file.return_value.id)


def test_server_key_accounts_never_use_a_supplied_llm_key(submission_env):
    service, file_repo, _, started = submission_env
    _submit(service, file_repo, _params(api_key="AIza-user", model="gemini-2.5-pro"))
    assert started["user_llm"] is None

    _submit(service, file_repo, _params(api_key="AIza-user"), user=User(USER_ID, "a@b.hu", []))
    assert started["user_llm"].api_key == "AIza-user"


def test_rejected_submission_stores_nothing(submission_env, monkeypatch):
    service, file_repo, run_repo, started = submission_env

    with pytest.raises(FileValidationError, match="does not exist"):
        _submit(service, file_repo, _params(target_variable="missing"))

    run_repo.count_active_for_user.return_value = 3
    with pytest.raises(TooManyActiveRunsError):
        _submit(service, file_repo, _params())
    run_repo.count_active_for_user.return_value = 0

    async def unreachable():
        return False

    monkeypatch.setattr(submission_service, "is_slurm_reachable", unreachable)
    with pytest.raises(ComputeUnavailableError):
        _submit(service, file_repo, _params())

    file_repo.create_file.assert_not_called()
    assert started == {}


def test_active_run_limit_can_be_disabled(submission_env, monkeypatch):
    service, _, run_repo, _ = submission_env
    run_repo.count_active_for_user.return_value = 50
    monkeypatch.setattr(service.settings.analysis, "max_active_runs_per_user", 0)
    service.check_active_run_limit(USER_ID)
    monkeypatch.setattr(service.settings.analysis, "max_active_runs_per_user", 50)
    with pytest.raises(TooManyActiveRunsError) as e:
        service.check_active_run_limit(USER_ID)
    assert e.value.status_code == 429 and e.value.details == {"active_runs": 50, "limit": 50}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


def test_responses_describe_the_single_analysis_mode():
    assert RunStatusResponse(run_id="r", status="running", progress=5).analysis_type == "standard"
    summary = RunSummary(run_id="r", status="running", progress=5, csv_filename="a.csv")
    assert summary.analysis_type == "standard"
    response = AnalyzeResponse(run_id="r", status_url="s", cancel_url="c", summary_url="u")
    assert response.renamed_columns == {}


def test_models_response_tells_whether_a_key_is_needed():
    response = ModelsResponse(server_keys=True, models=["m"], gemini_models=["m"])
    assert response.model_dump() == {"server_keys": True, "models": ["m"], "gemini_models": ["m"]}


def test_documented_examples_use_current_fields():
    example = AnalyzeParams.model_json_schema()["example"]
    assert "gemini_api_key" not in example and example["provider"] == "gemini"
    assert AnalyzeParams(**example).api_key == "AIza..."

    status = str(RunStatusResponse.model_json_schema()["examples"])
    assert "pareto_front" not in status and "shap_summary.png" in status
    # The explanation summary is nested under results.explanations
    completed = RunStatusResponse.model_json_schema()["examples"][1]["results"]
    assert "summary" not in completed and "summary" in completed["explanations"]


def test_run_lists_do_not_load_the_stored_results(monkeypatch):
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.orm import Query, Session

    from backend.repositories.run_repository import RunRepository

    selected = []

    def all_rows(query):
        selected.append(str(query.statement.compile(dialect=postgresql.dialect())))
        return []

    monkeypatch.setattr(Query, "count", lambda query: 0)
    monkeypatch.setattr(Query, "all", all_rows)
    RunRepository(Session()).get_user_runs(UUID(USER_ID))

    (sql,) = selected
    columns = sql.split(" FROM ")[0]
    assert "runs.status" in columns and "runs.results" not in columns
