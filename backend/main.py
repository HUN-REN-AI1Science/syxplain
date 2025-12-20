from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import os
import logging
import io
import secrets
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Query

from backend.models import RunRequest, RunResponse, RunSummary, PaginatedRunsResponse
import asyncio
from backend.service import start_run, cleanup_processes, check_timed_out_runs
from backend.database import init_db, get_db, File as DbFile, Run as DbRun, RunArtifact
from backend.auth import get_current_user, User

# Configure logging
from logger import configure_logging, get_cached_progress_config

# Filter out /api/runs/ polling logs from uvicorn access logger
class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("GET /api/runs/") == -1

# Configure root logger with rolling file handler
configure_logging()
logger = logging.getLogger(__name__)

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

app = FastAPI(title="Syxplain API")

# CORS
# Configure allowed origins from environment variable
# For development: CORS_ORIGINS="*"
# For production: CORS_ORIGINS="https://yourdomain.com,https://www.yourdomain.com"
cors_origins = os.environ.get("CORS_ORIGINS", "*")
allowed_origins = [origin.strip() for origin in cors_origins.split(",")] if cors_origins != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    init_db()

    # Start background task for process cleanup and timeout checking
    async def periodic_cleanup():
        while True:
            try:
                cleanup_processes()
                check_timed_out_runs()
            except Exception as e:
                logger.error(f"Error in process cleanup task: {e}")
            await asyncio.sleep(60)  # Check every minute

    asyncio.create_task(periodic_cleanup())

@app.post("/api/upload")
def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    logger.info(f"User {current_user.user_id} uploading file: {file.filename}")

    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    CHUNK_SIZE = 1024 * 1024  # 1 MB

    # Validate file extension
    filename_lower = file.filename.lower() if file.filename else ""
    if not (filename_lower.endswith('.csv') or filename_lower.endswith('.xlsx') or filename_lower.endswith('.xls')):
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload a CSV or Excel (.xlsx, .xls) file.")

    content = bytearray()
    while True:
        chunk = file.file.read(CHUNK_SIZE)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Maximum size is 50MB.")

    # Convert to immutable bytes
    content = bytes(content)

    # Detect file type and validate content
    try:
        import pandas as pd

        is_excel = filename_lower.endswith('.xlsx') or filename_lower.endswith('.xls')

        if is_excel:
            # Parse Excel file
            try:
                # Use openpyxl for .xlsx files
                engine = 'openpyxl' if filename_lower.endswith('.xlsx') else 'xlrd'
                df = pd.read_excel(io.BytesIO(content), engine=engine)
            except Exception as excel_err:
                logger.error(f"Failed to parse Excel file {file.filename}: {excel_err}")
                raise HTTPException(status_code=400, detail=f"Invalid Excel file: Could not parse the file. Please ensure it's a valid Excel workbook.")
        else:
            # Parse CSV file
            df = pd.read_csv(io.BytesIO(content))

        columns = df.columns.tolist()
        if df.empty and len(columns) == 0:
            raise ValueError("Empty file - no data found")
        if len(columns) == 0:
            raise ValueError("No columns detected in the file")

        logger.info(f"File {file.filename} validated successfully. Columns: {columns}")

    except HTTPException:
        raise
    except Exception as e:
        file_type = "Excel" if is_excel else "CSV"
        logger.error(f"Invalid {file_type} file {file.filename}: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid {file_type} file: {str(e)}")

    # Determine appropriate media type
    if filename_lower.endswith('.xlsx'):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif filename_lower.endswith('.xls'):
        media_type = "application/vnd.ms-excel"
    else:
        media_type = "text/csv"

    # Store in DB with user_id
    db_file = DbFile(
        filename=file.filename,
        content=content,
        media_type=media_type,
        user_id=current_user.user_id
    )
    db.add(db_file)
    db.commit()

    # Identify numeric columns and count NaN values
    column_types = {}
    nan_counts = {}
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            column_types[col] = "numeric"
        else:
            column_types[col] = "object"
        nan_counts[col] = int(df[col].isna().sum())

    return {"filename": file.filename, "columns": columns, "column_types": column_types, "nan_counts": nan_counts}

@app.get("/api/progress-config")
def get_progress_config():
    """Returns progress phase configuration for frontend progress bar."""
    phases, _ = get_cached_progress_config()
    return {"phases": phases}

@app.get("/api/config/deep-research-models")
def get_deep_research_models():
    """Returns available deep research models from environment configuration."""
    models_env = os.environ.get("DEEP_RESEARCH_MODEL", "")
    if not models_env:
        return {"models": []}

    # Parse comma-separated model list
    models = [m.strip() for m in models_env.split(",") if m.strip()]
    return {"models": models}

@app.get("/api/profile")
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Returns user profile data."""
    # Count user's runs and files
    total_runs = db.query(DbRun).filter(DbRun.user_id == current_user.user_id).count()
    total_files = db.query(DbFile).filter(DbFile.user_id == current_user.user_id).count()

    # Get earliest created_at from runs or files
    earliest_run = db.query(DbRun).filter(DbRun.user_id == current_user.user_id).order_by(DbRun.created_at.asc()).first()
    earliest_file = db.query(DbFile).filter(DbFile.user_id == current_user.user_id).order_by(DbFile.created_at.asc()).first()

    created_at = None
    if earliest_run and earliest_file:
        created_at = min(earliest_run.created_at, earliest_file.created_at).isoformat()
    elif earliest_run:
        created_at = earliest_run.created_at.isoformat()
    elif earliest_file:
        created_at = earliest_file.created_at.isoformat()

    return {
        "email": current_user.email,
        "created_at": created_at,
        "total_runs": total_runs,
        "total_files": total_files
    }

@app.delete("/api/profile")
async def delete_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    GDPR-compliant account deletion.
    Removes all user data from the database and deletes the user from Supabase.
    """
    from backend.auth import delete_supabase_user

    user_id = current_user.user_id
    logger.info(f"Starting GDPR account deletion for user: {user_id}")

    try:
        # Delete all runs (cascades to run_steps and run_artifacts due to relationship config)
        runs_deleted = db.query(DbRun).filter(DbRun.user_id == user_id).delete()
        logger.info(f"Deleted {runs_deleted} runs for user {user_id}")

        # Delete all files
        files_deleted = db.query(DbFile).filter(DbFile.user_id == user_id).delete()
        logger.info(f"Deleted {files_deleted} files for user {user_id}")

        db.commit()
        logger.info(f"Database cleanup completed for user {user_id}")

        # Delete user from Supabase Auth
        await delete_supabase_user(user_id)
        logger.info(f"Supabase user deleted: {user_id}")

        return {"message": "Account deleted successfully"}

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete account for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete account: {str(e)}")

@app.post("/api/run", response_model=RunResponse)
def run_analysis(
    request: RunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    logger.info(f"User {current_user.user_id} requesting run for file: {request.csv_filename}")
    api_key = os.environ.get("OPENAI_API_KEY")
    api_base = os.environ.get("OPENAI_API_BASE")
    model_name = os.environ.get("OPENAI_MODEL_NAME")

    if not api_key:
        logger.error("OPENAI_API_KEY not set on server")
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set on server")

    # Validate analysis_type
    if request.analysis_type not in ["quick", "deep"]:
        raise HTTPException(status_code=400, detail="Invalid analysis_type. Must be 'quick' or 'deep'.")

    # Deep analysis specific validation
    if request.analysis_type == "deep":
        # Validate DEEP_RESEARCH_API_KEY is configured
        deep_api_key = os.environ.get("DEEP_RESEARCH_API_KEY")
        if not deep_api_key:
            logger.error("Deep analysis requested but DEEP_RESEARCH_API_KEY not configured")
            raise HTTPException(status_code=500, detail="Deep analysis is not configured on this server. DEEP_RESEARCH_API_KEY is missing.")

        # Validate model selection
        if not request.deep_research_model:
            raise HTTPException(status_code=400, detail="deep_research_model is required for deep analysis.")

        # Validate model is in allowed list
        models_env = os.environ.get("DEEP_RESEARCH_MODEL", "")
        allowed_models = [m.strip() for m in models_env.split(",") if m.strip()]
        if request.deep_research_model not in allowed_models:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid deep_research_model '{request.deep_research_model}'. Allowed models: {', '.join(allowed_models)}"
            )

    # Verify file exists in DB and belongs to user
    db_file = db.query(DbFile).filter(
        DbFile.filename == request.csv_filename,
        DbFile.user_id == current_user.user_id
    ).order_by(DbFile.created_at.desc()).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    # Validate problem description fields against actual file columns
    import pandas as pd
    df = pd.read_csv(io.BytesIO(db_file.content))
    file_columns = df.columns.tolist()

    # Validate target variable exists in file
    target_var = request.problem_description.target_variable
    if target_var not in file_columns:
        raise HTTPException(
            status_code=400,
            detail=f"Target variable '{target_var}' does not exist in the uploaded file. Available columns: {', '.join(file_columns)}"
        )

    # Validate all features exist in file
    invalid_features = [f for f in request.problem_description.features.keys() if f not in file_columns]
    if invalid_features:
        raise HTTPException(
            status_code=400,
            detail=f"Features do not exist in file: {', '.join(invalid_features)}"
        )

    run_id = start_run(
        request.problem_description.dict(),
        request.csv_filename,
        api_key,
        api_base,
        model_name,
        user_id=current_user.user_id,
        analysis_type=request.analysis_type,
        deep_research_model=request.deep_research_model
    )
    logger.info(f"Analysis started with Run ID: {run_id} (analysis_type={request.analysis_type}, model={request.deep_research_model})")
    return RunResponse(run_id=run_id, status="pending", message="Analysis started")

@app.get("/api/runs", response_model=PaginatedRunsResponse)
def list_runs(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    sort_field: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    status: Optional[str] = Query(None, description="Filter by status"),
    analysis_type: Optional[str] = Query(None, description="Filter by analysis type"),
    search: Optional[str] = Query(None, description="Search in filename and target variable"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Start with base query for current user
    query = db.query(DbRun).filter(DbRun.user_id == current_user.user_id)

    # Apply filters
    if status:
        query = query.filter(DbRun.status == status)
    if analysis_type:
        query = query.filter(DbRun.analysis_type == analysis_type)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                DbRun.csv_filename.ilike(search_pattern),
                DbRun.problem_description["target_variable"].astext.ilike(search_pattern)
            )
        )

    # Get total count before pagination
    total = query.count()

    # Apply sorting
    valid_sort_fields = {
        "created_at": DbRun.created_at,
        "csv_filename": DbRun.csv_filename,
        "status": DbRun.status,
        "analysis_type": DbRun.analysis_type,
        "target_variable": DbRun.problem_description["target_variable"].astext
    }
    sort_column = valid_sort_fields.get(sort_field, DbRun.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # Apply pagination
    offset = (page - 1) * page_size
    runs = query.offset(offset).limit(page_size).all()

    # Build response
    summary_list = []
    for run in runs:
        target = None
        if run.problem_description and isinstance(run.problem_description, dict):
            target = run.problem_description.get("target_variable")

        summary_list.append(RunSummary(
            id=str(run.id),
            status=run.status,
            created_at=run.created_at,
            csv_filename=run.csv_filename,
            target_variable=target,
            progress=run.progress or 0,
            analysis_type=run.analysis_type or "quick"
        ))

    total_pages = (total + page_size - 1) // page_size  # Ceiling division

    return PaginatedRunsResponse(
        items=summary_list,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

@app.get("/api/runs/shared")
def get_shared_runs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all runs shared by the current user."""
    runs = db.query(DbRun).filter(
        DbRun.user_id == current_user.user_id,
        DbRun.public_share_token.isnot(None)
    ).order_by(DbRun.created_at.desc()).all()

    result = []
    for run in runs:
        target = None
        if run.problem_description and isinstance(run.problem_description, dict):
            target = run.problem_description.get("target_variable")

        result.append({
            "id": str(run.id),
            "target_variable": target,
            "csv_filename": run.csv_filename,
            "analysis_type": run.analysis_type or "quick",
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "share_token": run.public_share_token,
            "share_url": f"/share/{run.public_share_token}"
        })

    return {"items": result}

@app.get("/api/runs/{run_id}")
def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    run = db.query(DbRun).filter(
        DbRun.id == run_id,
        DbRun.user_id == current_user.user_id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "status": run.status,
        "progress": run.progress or 0,
        "error": run.error,
        "results": run.results,
        "public_share_token": run.public_share_token
    }

@app.get("/api/runs/{run_id}/details")
def get_run_details(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive run details including CSV metadata for the Run Settings Panel."""
    import pandas as pd

    run = db.query(DbRun).filter(
        DbRun.id == run_id,
        DbRun.user_id == current_user.user_id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get the associated CSV file
    db_file = db.query(DbFile).filter(
        DbFile.filename == run.csv_filename,
        DbFile.user_id == current_user.user_id
    ).order_by(DbFile.created_at.desc()).first()

    csv_metadata = None
    if db_file:
        try:
            # Detect file type and use appropriate reader
            filename_lower = db_file.filename.lower()
            if filename_lower.endswith('.xlsx') or filename_lower.endswith('.xls'):
                engine = 'openpyxl' if filename_lower.endswith('.xlsx') else 'xlrd'
                df = pd.read_excel(io.BytesIO(db_file.content), engine=engine)
            else:
                df = pd.read_csv(io.BytesIO(db_file.content))
            csv_metadata = {
                "filename": db_file.filename,
                "size_bytes": len(db_file.content),
                "row_count": len(df),
                "column_count": len(df.columns),
                "columns": df.columns.tolist()
            }
        except Exception as e:
            logger.warning(f"Failed to parse CSV for run {run_id}: {e}")
            csv_metadata = {
                "filename": db_file.filename,
                "size_bytes": len(db_file.content),
                "row_count": None,
                "column_count": None,
                "columns": []
            }

    return {
        "id": str(run.id),
        "status": run.status,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "problem_description": run.problem_description,
        "csv_filename": run.csv_filename,
        "csv_metadata": csv_metadata,
        "analysis_type": run.analysis_type or "quick",
        "error": run.error
    }


@app.get("/api/runs/{run_id}/download/{filename}")
def download_file(
    run_id: str,
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # First verify run belongs to user
    run = db.query(DbRun).filter(
        DbRun.id == run_id,
        DbRun.user_id == current_user.user_id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Then get artifact
    artifact = db.query(RunArtifact).filter(
        RunArtifact.run_id == run_id,
        RunArtifact.filename == filename
    ).first()
    if not artifact:
        raise HTTPException(status_code=404, detail="File not found")

    return Response(content=artifact.content, media_type=artifact.media_type)

@app.get("/api/runs/{run_id}/download-csv")
def download_csv(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download the original CSV file associated with a run."""
    # Verify run belongs to user
    run = db.query(DbRun).filter(
        DbRun.id == run_id,
        DbRun.user_id == current_user.user_id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get the CSV file
    db_file = db.query(DbFile).filter(
        DbFile.filename == run.csv_filename,
        DbFile.user_id == current_user.user_id
    ).order_by(DbFile.created_at.desc()).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="CSV file not found")

    return Response(
        content=db_file.content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={db_file.filename}"}
    )

# ============================================================================
# Sharing Endpoints (Authenticated)
# ============================================================================

@app.post("/api/runs/{run_id}/share")
def create_share_link(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate a public share link for a run."""
    run = db.query(DbRun).filter(
        DbRun.id == run_id,
        DbRun.user_id == current_user.user_id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # If already shared, return existing token
    if run.public_share_token:
        return {
            "share_token": run.public_share_token,
            "share_url": f"/share/{run.public_share_token}"
        }

    # Generate new token (32 characters, URL-safe)
    token = secrets.token_urlsafe(24)
    run.public_share_token = token
    db.commit()

    logger.info(f"User {current_user.user_id} created share link for run {run_id}")

    return {
        "share_token": token,
        "share_url": f"/share/{token}"
    }

@app.delete("/api/runs/{run_id}/share")
def revoke_share_link(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Revoke a public share link for a run."""
    run = db.query(DbRun).filter(
        DbRun.id == run_id,
        DbRun.user_id == current_user.user_id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    run.public_share_token = None
    db.commit()

    logger.info(f"User {current_user.user_id} revoked share link for run {run_id}")

    return {"message": "Share link revoked"}

# ============================================================================
# Public Endpoints (No Authentication)
# ============================================================================

@app.get("/api/public/{share_token}")
def get_public_run(
    share_token: str,
    db: Session = Depends(get_db)
):
    """Get public run results by share token (no auth required)."""
    run = db.query(DbRun).filter(
        DbRun.public_share_token == share_token
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Shared run not found")

    return {
        "status": run.status,
        "progress": run.progress or 0,
        "results": run.results,
        "share_token": run.public_share_token
    }

@app.get("/api/public/{share_token}/details")
def get_public_run_details(
    share_token: str,
    db: Session = Depends(get_db)
):
    """Get public run details by share token (no auth required)."""
    import pandas as pd

    run = db.query(DbRun).filter(
        DbRun.public_share_token == share_token
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Shared run not found")

    # Get the associated CSV file (need to find by filename and user_id)
    db_file = db.query(DbFile).filter(
        DbFile.filename == run.csv_filename,
        DbFile.user_id == run.user_id
    ).order_by(DbFile.created_at.desc()).first()

    csv_metadata = None
    if db_file:
        try:
            # Detect file type and use appropriate reader
            filename_lower = db_file.filename.lower()
            if filename_lower.endswith('.xlsx') or filename_lower.endswith('.xls'):
                engine = 'openpyxl' if filename_lower.endswith('.xlsx') else 'xlrd'
                df = pd.read_excel(io.BytesIO(db_file.content), engine=engine)
            else:
                df = pd.read_csv(io.BytesIO(db_file.content))
            csv_metadata = {
                "filename": db_file.filename,
                "size_bytes": len(db_file.content),
                "row_count": len(df),
                "column_count": len(df.columns),
                "columns": df.columns.tolist()
            }
        except Exception as e:
            logger.warning(f"Failed to parse CSV for public run: {e}")
            csv_metadata = {
                "filename": db_file.filename,
                "size_bytes": len(db_file.content),
                "row_count": None,
                "column_count": None,
                "columns": []
            }

    return {
        "id": str(run.id),
        "status": run.status,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "problem_description": run.problem_description,
        "csv_filename": run.csv_filename,
        "csv_metadata": csv_metadata,
        "analysis_type": run.analysis_type or "quick",
        "error": run.error
    }

@app.get("/api/public/{share_token}/download-csv")
def download_public_csv(
    share_token: str,
    db: Session = Depends(get_db)
):
    """Download the CSV file for a public run (no auth required)."""
    run = db.query(DbRun).filter(
        DbRun.public_share_token == share_token
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Shared run not found")

    # Get the CSV file using run's user_id
    db_file = db.query(DbFile).filter(
        DbFile.filename == run.csv_filename,
        DbFile.user_id == run.user_id
    ).order_by(DbFile.created_at.desc()).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="CSV file not found")

    return Response(
        content=db_file.content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={db_file.filename}"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
