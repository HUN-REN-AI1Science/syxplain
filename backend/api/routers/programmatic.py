"""
Syxplain API endpoints.

Streamlined API designed for script, notebook, and CI/CD pipeline usage.
Provides combined upload+analyze, status polling, and artifact download.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, File, Form, Path, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from backend.api.dependencies import get_file_repository, get_run_service
from backend.core.config import get_settings
from backend.core.constants import RunStatus
from backend.core.exceptions import (
    ConfigurationError,
    EntityNotFoundError,
    FileTooLargeError,
    FileValidationError,
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
    RunListResponse,
    RunStatusResponse,
    RunSummary,
)
from backend.services.analysis_service import start_analysis_run
from backend.services.file_service import get_file_service
from backend.services.run_service import RunService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Syxplain API"])


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
| `features` | object | Yes | Mapping of feature column names to descriptions (e.g. `{"pH": "Soil pH"}`) |
| `provider` | string | No | `"gemini"` (default) or `"openai_compatible"` (any OpenAI-compatible endpoint: OpenAI, OpenRouter, vLLM, LiteLLM, ...) |
| `api_key` | string | No | API key for the provider (required without server-key access) |
| `model` | string | No | Model name. Gemini: default `"gemini-3.1-pro-preview"`; OpenAI-compatible: required |
| `api_base` | string | No | OpenAI-compatible base URL (default: `"https://api.openai.com/v1"`); must be publicly reachable |
| `gemini_api_key` | string | No | Legacy alias of `api_key` for the Gemini provider |
| `gemini_model` | string | No | Legacy alias of `model` for the Gemini provider |
| `openai_api_key` | string | No | OpenAI API key for the literature search (without server-key access; omitted = no literature step, unless `api_key` is an OpenAI key on the default OpenAI endpoint) |

**Example `params` value:**

```json
{
  "project_description": "Predict soil phosphorus availability",
  "target_variable": "P_availability",
  "features": {"pH": "Soil pH (H2O)", "organic_C": "Organic carbon (%)"},
  "gemini_api_key": "AIza..."
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
        401: {"description": "Missing or invalid API key", "model": ErrorResponse},
    },
)
@limiter.limit("5/minute")
async def analyze(
    request: Request,  # Required for rate limiting
    file: UploadFile = File(..., description="CSV or Excel file to analyze"),
    params: str = Form(
        ...,
        description='JSON string with analysis parameters. Required fields: project_description, target_variable, features. Example: {"project_description": "...", "target_variable": "Y", "features": {"X1": "desc"}, "gemini_api_key": "AIza..."}',
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

    # Process file upload (reuse existing FileService)
    file_service = get_file_service()
    try:
        filename = file.filename or "upload.csv"
        content, metadata = file_service.process_upload(file.file, filename)

        # Store in database
        file_repo.create_file(
            filename=filename,
            content=content,
            user_id=current_user.user_id,
            media_type=metadata.media_type,
        )
        csv_filename = metadata.filename
    except (FileTooLargeError, FileValidationError) as e:
        return _api_error(400, "file_error", e.message, e.details)
    except Exception as e:
        return _api_error(400, "file_error", f"File processing failed: {e}")

    # Validate columns exist in the file
    try:
        has_server_keys_access = current_user.has_server_keys_access
        # The user's own LLM settings; users with server-key access always run on the server keys
        user_llm = None if has_server_keys_access else analyze_params.to_user_llm()

        # Blocking (file parsing, DNS): off the event loop
        await asyncio.to_thread(
            run_service.validate_run_request,
            csv_filename=csv_filename,
            target_variable=analyze_params.target_variable,
            features=analyze_params.features,
            user_id=current_user.user_id,
            has_server_keys_access=has_server_keys_access,
            user_llm=user_llm,
        )
    except EntityNotFoundError as e:
        return _api_error(404, "not_found", e.message, e.details)
    except ValidationError as e:
        return _api_error(400, "validation_error", e.message, e.details)
    except ConfigurationError as e:
        return _api_error(500, "configuration_error", e.message)

    # Start analysis run
    problem_desc = {
        "project_description": analyze_params.project_description,
        "target_variable": analyze_params.target_variable,
        "features": analyze_params.features,
    }

    run_id = start_analysis_run(
        problem_desc=problem_desc,
        csv_filename=csv_filename,
        user_id=current_user.user_id,
        user_llm=user_llm,
    )

    logger.info(f"api/analyze: Run {run_id} started for user {current_user.user_id}")

    return AnalyzeResponse(
        run_id=run_id,
        status=RunStatus.PENDING,
        status_url=f"/api/v1/runs/{run_id}",
        cancel_url=f"/api/v1/runs/{run_id}/cancel",
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
polling can stop. For completed runs, the `results` field contains the full analysis output
including discovered equations, summary, and recommendation. The `artifacts` list provides
download URLs for generated plots and files.

**Status lifecycle:** `pending` -> `running` -> `completed` | `failed` | `timeout` | `cancelled`

**Fields populated on completion:** `results`, `artifacts`, `duration_seconds`, `finish_time`
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
    """Get run status with inline results when completed."""
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
        run_id=str(run.id),
        status=run.status,
        progress=run.progress or 0,
        analysis_type=run.analysis_type or "quick",
        created_at=run.created_at,
        start_time=run.start_time,
        finish_time=run.finish_time,
        duration_seconds=duration_seconds,
        error=run.error,
        results=run.results if run.status == RunStatus.COMPLETED else None,
        artifacts=artifacts,
    )


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
            analysis_type=r.analysis_type or "quick",
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
    summary="List available analysis models",
    description="""
Returns the available models that can be used in analysis requests.

Lists the Gemini models for the main LLM pipeline with your own Gemini key; pass one as
`model` (or the legacy `gemini_model`). With `provider: "openai_compatible"`, `model` is
any model your endpoint serves.
""",
    responses={
        200: {"description": "Lists of available model identifiers", "model": ModelsResponse},
    },
)
@limiter.limit("30/minute")
def list_models(request: Request, current_user: User = Depends(get_current_user)):
    """List available models for analysis."""
    settings = get_settings()
    return ModelsResponse(
        gemini_models=settings.llm.get_user_api_model_list(),
    )
