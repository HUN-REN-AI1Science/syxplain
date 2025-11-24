from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import shutil
import os
import json
import logging
import io
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from backend.models import ProblemDescription, RunRequest, RunResponse, RunSummary
from backend.service import start_run
from backend.database import init_db, get_db, File as DbFile, Run as DbRun, RunArtifact
from backend.auth import get_current_user, User

# Configure logging
from logger import configure_logging

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev, restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()

@app.post("/api/upload")
def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    logger.info(f"User {current_user.user_id} uploading file: {file.filename}")

    content = file.file.read()

    # Store in DB with user_id
    db_file = DbFile(
        filename=file.filename,
        content=content,
        media_type=file.content_type,
        user_id=current_user.user_id
    )
    db.add(db_file)
    db.commit()

    # Try to parse columns to help frontend
    try:
        import pandas as pd
        df = pd.read_csv(io.BytesIO(content))
        columns = df.columns.tolist()
        logger.info(f"File {file.filename} uploaded successfully. Columns: {columns}")
        return {"filename": file.filename, "columns": columns}
    except Exception as e:
        logger.error(f"Error processing file {file.filename}: {e}")
        return {"filename": file.filename, "error": str(e)}

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

    # Verify file exists in DB and belongs to user
    db_file = db.query(DbFile).filter(
        DbFile.filename == request.csv_filename,
        DbFile.user_id == current_user.user_id
    ).order_by(DbFile.created_at.desc()).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    run_id = start_run(
        request.problem_description.dict(),
        request.csv_filename,
        api_key,
        api_base,
        model_name,
        user_id=current_user.user_id
    )
    logger.info(f"Analysis started with Run ID: {run_id}")
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
            target_variable=target
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
        "error": run.error,
        "results": run.results
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
