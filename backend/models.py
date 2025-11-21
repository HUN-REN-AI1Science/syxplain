from pydantic import BaseModel
from typing import Dict, List, Optional, Any

class ProblemDescription(BaseModel):
    project_description: str
    target_variable: str
    features: Dict[str, str]

class RunRequest(BaseModel):
    problem_description: ProblemDescription
    csv_filename: str

class RunResponse(BaseModel):
    run_id: str
    status: str
    message: str

class RunStatus(BaseModel):
    run_id: str
    status: str
    logs: List[str]
    results: Optional[Dict[str, Any]] = None

class RunSummary(BaseModel):
    id: str
    status: str
    created_at: Any # Pydantic handles datetime serialization
    csv_filename: str
    target_variable: Optional[str] = None
