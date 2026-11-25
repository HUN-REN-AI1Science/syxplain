"""
Syxplain API endpoints.

Streamlined API designed for script, notebook, and CI/CD pipeline usage.
Provides combined upload+analyze, status polling, and artifact download.
"""

import json
import logging

from fastapi import APIRouter, Depends, File, Form, Path, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from backend.api.dependencies import get_file_repository, get_run_service
from backend.core.config import get_settings
from backend.core.constants import STANDARD_ANALYSIS, RunStatus
from backend.core.exceptions import (
    ComputeUnavailableError,
    ConfigurationError,
    EntityNotFoundError,
    FileTooLargeError,
    FileValidationError,
    SyxplainException,
    TooManyActiveRunsError,
    ValidationError,
)
from backend.core.rate_limit import limiter
from backend.core.security import User, get_current_user
from backend.repositories.file_repository import FileRepository
from backend.schemas.programmatic import (
    AnalyzeParams,
    AnalyzeResponse,
    ArtifactInfo,
    CancelResponse,
    ErrorResponse,
    ModelsResponse,
    RunDigestResponse,
    RunListResponse,
    RunStatusResponse,
    RunSummary,
)
from backend.services.run_digest import run_digest_payload, run_state, run_warnings
from backend.services.run_service import RunService
from backend.services.submission_service import submit_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Syxplain API"])


# Refusals of a submission: (exception, HTTP status, error code), most specific first
_SUBMISSION_ERRORS: tuple[tuple[type[SyxplainException], int, str], ...] = (
    ((FileTooLargeError, FileValidationError), 400, "file_error"),
    (TooManyActiveRunsError, 429, "too_many_active_runs"),
    (ComputeUnavailableError, 503, "compute_unavailable"),
    (ValidationError, 400, "validation_error"),
    (ConfigurationError, 500, "configuration_error"),
)


def _api_error(
    status_code: int, error: str, message: str, details: dict | None = None
) -> JSONResponse:
    """Return a structured API error response."""
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, message=message, details=details).model_dump(),
    )


# ============================================================================
# POST /api/v1/analyze — Combined upload + analyze
# ============================================================================


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    status_code=202,
    summary="Upload a file and start analysis",
    description="""
Combined endpoint that uploads a CSV or Excel file and starts an analysis run in a single request.

Send the file as multipart form data in the `file` field, and analysis parameters as a JSON string
in the `params` field. The response includes a `run_id` along with URLs for polling status and
cancelling the run.

**`params` JSON fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `project_description` | string | Yes | Description of the project and analysis goals |
| `target_variable` | string | Yes | Name of the target column to predict |
| `features` | object | Yes | Mapping of feature column names to descriptions (e.g. `{"pH": "Soil pH"}`). Good descriptions with units matter: the LLM steps reason from them |
| `literature_text` | string | No | Your own literature on the problem as plain text. Read in addition to the web literature research; the recommended equation is then chosen among those coherent with what the literature states |
| `web_literature` | boolean | No | Web literature research, default `true`. Can be `false` only when `literature_text` is given: one of the two kinds of literature research is always used |
| `provider` | string | No | `"gemini"` (default) or `"openai_compatible"` (any OpenAI-compatible endpoint: OpenAI, OpenRouter, vLLM, LiteLLM, ...) |
| `api_key` | string | No | API key for the provider (required without server-key access) |
| `model` | string | No | Model name. Gemini: default `"gemini-3.1-pro-preview"`; OpenAI-compatible: required |
| `api_base` | string | No | OpenAI-compatible base URL (default: `"https://api.openai.com/v1"`); must be publicly reachable |
| `gemini_api_key` | string | No | Legacy alias of `api_key` for the Gemini provider |
| `gemini_model` | string | No | Legacy alias of `model` for the Gemini provider |
| `openai_api_key` | string | No | OpenAI API key for the literature search (without server-key access; omitted = no literature step, unless `api_key` is an OpenAI key on the default OpenAI endpoint) |

Accounts with server-key access (see `GET /api/v1/models`) run on the server's LLM keys:
they send no LLM fields, and any they send are ignored.

Column names that are not valid identifiers (spaces, dots, hyphens, ...) are renamed with
underscores. `target_variable` and `features` may use the names as written in the file or the
renamed ones; the response lists the renames in `renamed_columns`.

For a time series, keep the time column (and the column identifying each series, if any) in
the file. The time structure is detected from the data; the split is then chronological and
features of earlier periods may be derived.

**Example `params` value:**

```json
{
  "project_description": "Predict soil phosphorus availability",
  "target_variable": "P_availability",
  "features": {"pH": "Soil pH (H2O)", "organic_C": "Organic carbon (%)"},
  "api_key": "AIza..."
}
```

With an OpenAI-compatible endpoint instead of Gemini:

```json
{
  "project_description": "Predict soil phosphorus availability",
  "target_variable": "P_availability",
  "features": {"pH": "Soil pH (H2O)", "organic_C": "Organic carbon (%)"},
  "provider": "openai_compatible",
  "api_key": "sk-or-...",
  "api_base": "https://openrouter.ai/api/v1",
  "model": "openai/gpt-5"
}
```
""",
    responses={
        202: {
            "description": "Analysis accepted and queued for execution",
            "model": AnalyzeResponse,
        },
        400: {
            "description": "Invalid input: malformed JSON, unsupported file type, or missing required fields",
            "model": ErrorResponse,
        },
        401: {"description": "Missing or invalid credentials", "model": ErrorResponse},
        429: {
            "description": "Rate limit, or the account's limit of active analyses is reached",
            "model": ErrorResponse,
        },
        503: {"description": "The computing cluster is unreachable", "model": ErrorResponse},
    },
)
@limiter.limit("5/minute")
async def analyze(
    request: Request,  # Required for rate limiting
    file: UploadFile = File(..., description="CSV or Excel file to analyze"),
    params: str = Form(
        ...,
        description='JSON string with analysis parameters. Required fields: project_description, target_variable, features. Example: {"project_description": "...", "target_variable": "Y", "features": {"X1": "desc"}, "api_key": "AIza..."}',
    ),
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
    file_repo: FileRepository = Depends(get_file_repository),
):
    """Upload a file and start analysis in one call."""
    # Parse params JSON
    try:
        params_dict = json.loads(params)
        analyze_params = AnalyzeParams(**params_dict)
    except json.JSONDecodeError:
        return _api_error(400, "invalid_json", "Malformed JSON in params field")
    except Exception as e:
        return _api_error(400, "validation_error", str(e))

    try:
        submission = await submit_analysis(
            user=current_user,
            filename=file.filename or "upload.csv",
            file_obj=file.file,
            params=analyze_params,
            run_service=run_service,
            file_repo=file_repo,
        )
    except SyxplainException as e:
        for kinds, status_code, code in _SUBMISSION_ERRORS:
            if isinstance(e, kinds):
                return _api_error(status_code, code, e.message, e.details or None)
        raise

    run_id = submission.run_id
    return AnalyzeResponse(
        run_id=run_id,
        status=RunStatus.PENDING,
        status_url=f"/api/v1/runs/{run_id}",
        cancel_url=f"/api/v1/runs/{run_id}/cancel",
        summary_url=f"/api/v1/runs/{run_id}/summary",
        renamed_columns=submission.renamed_columns,
    )


# ============================================================================
# GET /api/v1/runs/{run_id} — Status + results
# ============================================================================


@router.get(
    "/runs/{run_id}",
    response_model=RunStatusResponse,
    summary="Get run status and results",
    description="""
Poll this endpoint to check the progress and retrieve results of an analysis run.

When the run reaches a terminal state (`completed`, `failed`, `timeout`, or `cancelled`),
polling can stop. A typical analysis takes 10 to 30 minutes; poll every 15 to 30 seconds.
While it runs, `phase` names the pipeline step.

For completed runs, `results` holds the full output: the shortlisted `equations` and the
`best_equation` with holdout and cross-validation scores, the `explanations`, and the
`discovery` record (data split, time-series features, agent report, literature and known-law
comparison). `warnings` lists steps that were skipped or failed without failing the run.
The `artifacts` list provides download URLs for generated plots and files.
`GET /api/v1/runs/{run_id}/summary` returns the same outcome in compact form.

**Status lifecycle:** `pending` -> `running` -> `completed` | `failed` | `timeout` | `cancelled`

**Fields populated on completion:** `artifacts`, `duration_seconds`, `finish_time`; `results`
is complete then (a running analysis already exposes the interim results once the equation
search has finished)
""",
    responses={
        200: {
            "description": "Current run status with results if completed",
            "model": RunStatusResponse,
        },
        404: {
            "description": "Run not found or not owned by the authenticated user",
            "model": ErrorResponse,
        },
    },
)
@limiter.limit("60/minute")
def get_run_status(
    request: Request,
    run_id: str = Path(..., description="Unique identifier of the run to query"),
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    """Get run status with inline results."""
    try:
        run = run_service.get_run_for_user(run_id, current_user.user_id)
    except EntityNotFoundError:
        return _api_error(404, "not_found", f"Run '{run_id}' not found")

    # Calculate duration
    duration_seconds = None
    if run.start_time and run.finish_time:
        duration_seconds = (run.finish_time - run.start_time).total_seconds()

    # Build artifacts list
    artifacts = []
    if run.status == RunStatus.COMPLETED and hasattr(run, "artifacts") and run.artifacts:
        for art in run.artifacts:
            artifacts.append(
                ArtifactInfo(
                    filename=art.filename,
                    media_type=art.media_type,
                    download_url=f"/api/v1/runs/{run_id}/artifacts/{art.filename}",
                )
            )

    return RunStatusResponse(
        **run_state(run),
        analysis_type=run.analysis_type or STANDARD_ANALYSIS,
        created_at=run.created_at,
        start_time=run.start_time,
        finish_time=run.finish_time,
        duration_seconds=duration_seconds,
        warnings=run_warnings(run.results),
        results=run.results or None,
        artifacts=artifacts,
    )


# ============================================================================
# GET /api/v1/runs/{run_id}/summary — Compact result summary
# ============================================================================


@router.get(
    "/runs/{run_id}/summary",
    response_model=RunDigestResponse,
    summary="Get a compact summary of the results",
    description="""
The outcome of a run without the plot data, the full model leaderboard and the agent's
activity log: the selected equation and the shortlist with their scores, how the data was
split and what the scores are measured on, the time-series features that were derived, the
agent's conclusions, the comparison with published and classic laws, the explanation, the
warnings and the LLM cost.

Suited to chat assistants and dashboards; `GET /api/v1/runs/{run_id}` has everything.
`summary` is null until results exist.
""",
    responses={
        200: {"description": "Run state and the compact summary", "model": RunDigestResponse},
        404: {
            "description": "Run not found or not owned by the authenticated user",
            "model": ErrorResponse,
        },
    },
)
@limiter.limit("60/minute")
def get_run_summary(
    request: Request,
    run_id: str = Path(..., description="Unique identifier of the run to summarize"),
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    """Compact summary of a run's results."""
    try:
        run = run_service.get_run_for_user(run_id, current_user.user_id)
    except EntityNotFoundError:
        return _api_error(404, "not_found", f"Run '{run_id}' not found")
    return run_digest_payload(run)


# ============================================================================
# GET /api/v1/runs — List runs
# ============================================================================


@router.get(
    "/runs",
    response_model=RunListResponse,
    summary="List your analysis runs",
    description="""
List your analysis runs with pagination and optional filtering.

Returns a paginated list of run summaries ordered by creation date. Use query parameters
to control pagination, sort order, and filter by status.
""",
    responses={
        200: {"description": "Paginated list of run summaries", "model": RunListResponse},
    },
)
@limiter.limit("30/minute")
def list_runs(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page (1-100)"),
    sort_order: str = Query("desc", description="Sort order by creation date: 'asc' or 'desc'"),
    status: str | None = Query(
        None, description="Filter by run status (e.g. 'completed', 'failed', 'running')"
    ),
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    """List runs for the authenticated user."""
    result = run_service.list_runs(
        user_id=current_user.user_id,
        page=page,
        page_size=page_size,
        sort_field="created_at",
        sort_order=sort_order,
        status=status,
    )

    items = [
        RunSummary(
            run_id=str(r.id),
            status=r.status,
            progress=r.progress or 0,
            analysis_type=r.analysis_type or STANDARD_ANALYSIS,
            csv_filename=r.csv_filename,
            target_variable=r.target_variable,
            created_at=r.created_at,
            start_time=r.start_time,
            finish_time=r.finish_time,
        )
        for r in result.items
    ]

    return RunListResponse(
        items=items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


# ============================================================================
# POST /api/v1/runs/{run_id}/cancel — Cancel a run
# ============================================================================


@router.post(
    "/runs/{run_id}/cancel",
    response_model=CancelResponse,
    summary="Cancel a running analysis",
    description="""
Cancel a pending or running analysis run.

This operation is idempotent -- if the run has already reached a terminal state
(`completed`, `failed`, `timeout`, `cancelled`), the request still returns success.
For runs with active Slurm jobs, the corresponding jobs will be cancelled on the cluster.
""",
    responses={
        200: {
            "description": "Run successfully cancelled or already in a terminal state",
            "model": CancelResponse,
        },
        404: {
            "description": "Run not found or not owned by the authenticated user",
            "model": ErrorResponse,
        },
    },
)
@limiter.limit("10/minute")
async def cancel_run(
    request: Request,
    run_id: str = Path(..., description="Unique identifier of the run to cancel"),
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    """Cancel a run."""
    try:
        await run_service.cancel_run(run_id, current_user.user_id)
        return CancelResponse(message="Run cancelled", run_id=run_id)
    except EntityNotFoundError:
        return _api_error(404, "not_found", f"Run '{run_id}' not found")


# ============================================================================
# GET /api/v1/runs/{run_id}/artifacts/{filename} — Download artifact
# ============================================================================


@router.get(
    "/runs/{run_id}/artifacts/{filename}",
    response_class=Response,
    summary="Download an artifact file",
    description="""
Download a generated artifact from a completed run.

Artifacts include plots (PNG), JSON outputs, and other files generated during analysis.
The list of available artifacts and their filenames is returned in the `artifacts` field
of the run status response.

**Note:** The successful response returns the raw file content with the appropriate
`Content-Type` header (e.g. `image/png`), not JSON. Error responses are returned as JSON.
""",
    responses={
        200: {
            "description": "Artifact file content (binary). Content-Type matches the artifact's media type.",
            "content": {
                "image/png": {"schema": {"type": "string", "format": "binary"}},
                "application/json": {},
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        404: {"description": "Artifact or run not found", "model": ErrorResponse},
    },
)
@limiter.limit("60/minute")
def download_artifact(
    request: Request,
    run_id: str = Path(..., description="Unique identifier of the run that produced the artifact"),
    filename: str = Path(
        ..., description="Artifact filename as listed in the run status artifacts array"
    ),
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service),
):
    """Download an artifact file from a run."""
    try:
        artifact = run_service.get_artifact(run_id, filename, current_user.user_id)
        return Response(content=artifact.content, media_type=artifact.media_type)
    except EntityNotFoundError:
        return _api_error(404, "not_found", f"Artifact '{filename}' not found")


# ============================================================================
# GET /api/v1/models — Available models
# ============================================================================


@router.get(
    "/models",
    response_model=ModelsResponse,
    summary="Which LLM your analyses run on",
    description="""
Tells whether your analyses run on the server's LLM keys (`server_keys: true`: send no LLM
fields) or need your own key.

With your own Gemini key, `models` lists the suggested `model` values (the first is the
default). With `provider: "openai_compatible"`, `model` is any model your endpoint serves.
""",
    responses={
        200: {"description": "Lists of available model identifiers", "model": ModelsResponse},
    },
)
@limiter.limit("30/minute")
def list_models(request: Request, current_user: User = Depends(get_current_user)):
    """List available models for analysis."""
    models = get_settings().llm.get_user_api_model_list()
    return ModelsResponse(
        server_keys=current_user.has_server_keys_access,
        models=models,
        gemini_models=models,
    )
