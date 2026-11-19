"""
MCP server: lets a chat assistant (LibreChat, Claude, ...) run Syxplain analyses.

Served over streamable HTTP at /mcp from the backend process. Callers authenticate
with a Syxplain API key or a Keycloak access token and must have server-key access:
every analysis started here runs on the server's LLM keys, and the tools take no
LLM settings.

An analysis takes minutes, so the tools never wait for it: one starts the run, the
others report its state and results.
"""

import asyncio
import io
import logging
from contextlib import contextmanager
from typing import Annotated, Any

from fastapi import HTTPException
from limits import parse as parse_limit
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.api.dependencies import build_run_service
from backend.core.config import get_settings
from backend.core.exceptions import EntityNotFoundError, SyxplainException, ValidationError
from backend.core.rate_limit import limiter
from backend.core.security import User, authenticate_credentials
from backend.infrastructure.database.connection import get_db_session
from backend.schemas.programmatic import AnalyzeParams
from backend.services.run_digest import run_digest_payload, run_state
from backend.services.run_service import RunService
from backend.services.submission_service import submit_analysis

logger = logging.getLogger(__name__)

MCP_PATH = "/mcp"
_USER_STATE_KEY = "syxplain_user"

# Analyses started per account (requests in general are limited per credential by the
# application's rate limiter, before authentication)
_START_LIMIT = parse_limit("5/minute")

INSTRUCTIONS = """\
Syxplain discovers interpretable equations in tabular scientific data: symbolic \
regression steered by an AI agent, scored on held-out data, compared with published \
laws and explained in the terms of the user's domain.

How to use it:
1. Call start_analysis with the data as CSV text (header row first), the target \
column, and a description of every predictor column, with units. The descriptions and \
the project description are what the analysis reasons from, so ask the user for them \
instead of guessing. Leave identifier columns out of `features`. For a time series, \
keep the time column in the CSV (and the column naming each series, if there are \
several); it is detected from the data.
2. An analysis typically takes 10 to 30 minutes. Tell the user, then check with \
get_analysis_status when they ask or after a few minutes. Do not poll in a tight loop.
3. When the status is "completed", call get_analysis_results and report the headline \
equation, its holdout and cross-validation scores, the explanation and any warnings. \
Scores are measured on rows the equation was not fitted to.

Only small tables fit in a tool call. For larger files the user can upload the data in \
the Syxplain web application.\
"""


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def _bearer_token(headers: Headers) -> str | None:
    authorization = headers.get("authorization") or ""
    if authorization[:7].lower() == "bearer ":
        return authorization[7:].strip() or None
    return None


async def _reject(
    scope: Scope,
    receive: Receive,
    send: Send,
    status: int,
    error: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> None:
    response = JSONResponse(
        {"error": error, "message": message}, status_code=status, headers=headers
    )
    await response(scope, receive, send)


class McpAccess:
    """
    ASGI wrapper of the MCP app: authenticates the caller and requires server-key
    access. The user is stored in the request state for the tools.
    """

    # The rate-limit middleware (slowapi) names the endpoint of every route. Served as
    # a Route, not a Mount: a mount would redirect POST /mcp to /mcp/.
    __name__ = "mcp_endpoint"

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        try:
            # Blocking (database or JWKS lookup): off the event loop
            user = await asyncio.to_thread(
                authenticate_credentials, headers.get("x-api-key"), _bearer_token(headers)
            )
        except HTTPException as e:
            await _reject(
                scope, receive, send, e.status_code, "unauthorized", str(e.detail), e.headers
            )
            return

        if not user.has_server_keys_access:
            await _reject(
                scope,
                receive,
                send,
                403,
                "forbidden",
                "This account has no server-key access, which the MCP endpoint requires.",
            )
            return

        scope.setdefault("state", {})[_USER_STATE_KEY] = user
        await self.app(scope, receive, send)


def _current_user(ctx: Context) -> User:
    request = ctx.request_context.request
    user = getattr(getattr(request, "state", None), _USER_STATE_KEY, None)
    if user is None:
        raise ToolError("Not authenticated.")
    return user


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


@contextmanager
def _run_service():
    """A RunService on its own database session."""
    with get_db_session() as db:
        yield build_run_service(db)


def _get_run(run_service: RunService, run_id: str, user: User):
    try:
        return run_service.get_run_for_user(run_id, user.user_id)
    except (EntityNotFoundError, ValidationError):  # unknown id, or not a UUID
        raise ToolError(f"No analysis with run_id '{run_id}' for this account.")


def _status_payload(run) -> dict[str, Any]:
    return run_state(run) | {
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finish_time": run.finish_time.isoformat() if run.finish_time else None,
    }


def _run_payload(run_id: str, user: User, build) -> dict[str, Any]:
    with _run_service() as run_service:
        return build(_get_run(run_service, run_id, user))


def _list_payload(user: User, limit: int) -> dict[str, Any]:
    with _run_service() as run_service:
        page = run_service.list_runs(user_id=user.user_id, page=1, page_size=limit)
        return {"total": page.total, "analyses": [_status_payload(r) for r in page.items]}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def start_analysis(
    csv_text: Annotated[
        str,
        Field(description="The dataset as CSV text: a header row, then one row per observation."),
    ],
    project_description: Annotated[
        str,
        Field(
            description="What the data is, how it was collected and what the user wants to "
            "learn. The analysis reasons from this text."
        ),
    ],
    target_variable: Annotated[str, Field(description="Name of the column to explain.")],
    features: Annotated[
        dict[str, str],
        Field(
            description="Predictor columns to use: column name -> what it measures, with its "
            'unit. Example: {"pH": "Soil pH measured in water", "clay": "Clay fraction (%)"}'
        ),
    ],
    ctx: Context,
    dataset_name: Annotated[
        str, Field(description="Short name for the dataset, shown in the run list.")
    ] = "dataset",
    literature_text: Annotated[
        str | None,
        Field(
            description="Optional: the user's own literature on the problem (papers, notes) "
            "as plain text. It replaces the web literature search, and the recommended "
            "equation is then chosen among those coherent with what the text states. "
            "Pass only text the user supplied."
        ),
    ] = None,
) -> dict[str, Any]:
    """Start an equation-discovery analysis of a small table passed as CSV text.

    Returns at once with a run_id; the analysis itself typically takes 10 to 30
    minutes. Follow it with get_analysis_status and read the outcome with
    get_analysis_results.
    """
    user = _current_user(ctx)
    max_kb = get_settings().analysis.mcp_max_csv_kb
    data = csv_text.encode("utf-8")
    if len(data) > max_kb * 1024:
        raise ToolError(
            f"The CSV is larger than {max_kb} kB, the limit for data passed in a tool call. "
            "The user can upload larger files in the Syxplain web application."
        )
    # Counted once a run is accepted: a refused call (unknown column, run limit) must
    # not use up the quota of an account that a whole chat platform may share
    if not limiter.limiter.test(_START_LIMIT, "mcp-start", user.user_id):
        raise ToolError("Too many analyses started in the last minute. Try again shortly.")

    try:
        params = AnalyzeParams(
            project_description=project_description,
            target_variable=target_variable,
            features=features,
            literature_text=literature_text or None,
        )
    except ValueError as e:
        raise ToolError(f"Invalid parameters: {e}")

    stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in dataset_name).strip("_")
    filename = f"{stem[:80] or 'dataset'}.csv"
    try:
        with _run_service() as run_service:
            submission = await submit_analysis(
                user=user,
                filename=filename,
                file_obj=io.BytesIO(data),
                params=params,
                run_service=run_service,
                file_repo=run_service.file_repo,
            )
    except SyxplainException as e:
        # Anticipated refusals (unknown column, unparsable CSV, cluster down, run limit)
        raise ToolError(e.message)
    limiter.limiter.hit(_START_LIMIT, "mcp-start", user.user_id)

    # A chat platform can name the person behind the shared account (docs/mcp.md)
    end_user = (ctx.headers or {}).get("x-end-user", "")[:120]
    logger.info(
        f"mcp: run {submission.run_id} started for {user.email or user.user_id}"
        + (f" (end user: {end_user!r})" if end_user else "")
    )
    return {
        "run_id": submission.run_id,
        "status": "pending",
        "rows": submission.row_count,
        "renamed_columns": submission.renamed_columns,
        "expected_duration": "typically 10 to 30 minutes",
        "next_step": "Check progress with get_analysis_status; when the status is "
        "'completed', call get_analysis_results.",
    }


async def get_analysis_status(
    run_id: Annotated[str, Field(description="The run_id returned by start_analysis.")],
    ctx: Context,
) -> dict[str, Any]:
    """State of an analysis: status (pending, running, completed, failed, timeout,
    cancelled), progress in percent and the pipeline phase it is in."""
    user = _current_user(ctx)
    return await asyncio.to_thread(_run_payload, run_id, user, _status_payload)


async def get_analysis_results(
    run_id: Annotated[str, Field(description="The run_id returned by start_analysis.")],
    ctx: Context,
) -> dict[str, Any]:
    """Results of an analysis in compact form: the headline equation and the shortlist
    with holdout and cross-validation scores, how the data was split, derived
    time-series features, the agent's conclusions, the comparison with published laws,
    the explanation, warnings and LLM cost.

    `summary` is null until results exist (the status is then still pending or running,
    or the run failed: see `error`).
    """
    user = _current_user(ctx)
    return await asyncio.to_thread(_run_payload, run_id, user, run_digest_payload)


async def list_analyses(
    ctx: Context,
    limit: Annotated[int, Field(ge=1, le=50, description="How many to return.")] = 10,
) -> dict[str, Any]:
    """The most recent analyses of this account, newest first."""
    user = _current_user(ctx)
    return await asyncio.to_thread(_list_payload, user, limit)


async def cancel_analysis(
    run_id: Annotated[str, Field(description="The run_id of the analysis to stop.")],
    ctx: Context,
) -> dict[str, Any]:
    """Stop a pending or running analysis. Has no effect on one that already finished."""
    user = _current_user(ctx)
    with _run_service() as run_service:
        try:
            await run_service.cancel_run(run_id, user.user_id)
        except (EntityNotFoundError, ValidationError):  # unknown id, or not a UUID
            raise ToolError(f"No analysis with run_id '{run_id}' for this account.")
    return {"run_id": run_id, "message": "Analysis cancelled (or already finished)."}


TOOLS = (start_analysis, get_analysis_status, get_analysis_results, list_analyses, cancel_analysis)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def build_mcp() -> tuple[MCPServer, ASGIApp]:
    """
    A new MCP server and its access-controlled ASGI app. The caller serves the app at
    MCP_PATH and runs ``server.session_manager.run()`` for the application's lifetime
    (once per server instance, hence a factory).
    """
    server = MCPServer(name="Syxplain", instructions=INSTRUCTIONS)
    # One line per stateless request ("Terminating session") is noise in the backend log
    logging.getLogger("mcp.server.streamable_http").setLevel(logging.WARNING)
    for tool in TOOLS:
        server.tool()(tool)
    app = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        # Plain request/response: no sessions to keep, no stream for nginx to hold open
        json_response=True,
        stateless_http=True,
        # Host/Origin checks defend browser-reachable local servers; here every request
        # carries an explicit credential and the public host is set by the reverse proxy
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    return server, McpAccess(app)
