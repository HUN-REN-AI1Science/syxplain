from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import os
import logging
import io
from typing import List
from sqlalchemy.orm import Session

from backend.models import ProblemDescription, RunRequest, RunResponse, RunSummary
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

    # Validate CSV content
    try:
        import pandas as pd
        # Try to parse the content as CSV
        df = pd.read_csv(io.BytesIO(content))
        columns = df.columns.tolist()
        if df.empty and len(columns) == 0:
             raise ValueError("Empty CSV file")
        logger.info(f"File {file.filename} validated successfully. Columns: {columns}")
    except Exception as e:
        logger.error(f"Invalid CSV file {file.filename}: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid CSV file: {str(e)}")

    # Store in DB with user_id
    db_file = DbFile(
        filename=file.filename,
        content=content,
        media_type=file.content_type,
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

@app.get("/api/runs", response_model=List[RunSummary])
def list_runs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Only return runs belonging to the current user
    runs = db.query(DbRun).filter(
        DbRun.user_id == current_user.user_id
    ).order_by(DbRun.created_at.desc()).all()

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
            progress=run.progress or 0
        ))
    return summary_list

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
        "results": run.results
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
