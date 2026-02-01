"""
Pydantic request schemas for API endpoints.

These schemas define the structure and validation rules
for incoming request data.
"""
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field, field_validator


class SortField(str, Enum):
    """Valid fields for sorting runs."""
    CREATED_AT = "created_at"
    CSV_FILENAME = "csv_filename"
    STATUS = "status"
    ANALYSIS_TYPE = "analysis_type"


class SortOrder(str, Enum):
    """Sort order direction."""
    ASC = "asc"
    DESC = "desc"


class ProblemDescription(BaseModel):
    """Describes the analysis problem configuration."""
    project_description: str = Field(
        ...,
        min_length=1,
        description="Description of the project and analysis goals"
    )
    target_variable: str = Field(
        ...,
        min_length=1,
        description="Name of the target variable to predict"
    )
    features: Dict[str, str] = Field(
        ...,
        description="Dictionary mapping feature names to their descriptions"
    )

    @field_validator("features")
    @classmethod
    def features_not_empty(cls, v: Dict[str, str]) -> Dict[str, str]:
        if not v:
            raise ValueError("At least one feature must be specified")
        return v


class UserApiKeys(BaseModel):
    """User-provided API keys (not stored)."""
    openai_api_key: str = Field(
        ...,
        min_length=1,
        description="OpenAI API key for analysis"
    )
    openai_model: str = Field(
        default="gpt-4o",
        description="OpenAI model to use"
    )


class RunRequest(BaseModel):
    """Request schema for starting an analysis run."""
    problem_description: ProblemDescription
    csv_filename: str = Field(
        ...,
        min_length=1,
        description="Name of the uploaded file to analyze"
    )
    analysis_type: str = Field(
        default="quick",
        description="Type of analysis: 'quick' or 'deep'"
    )
    deep_research_model: Optional[str] = Field(
        default=None,
        description="Model to use for deep analysis (required when analysis_type is 'deep')"
    )
    user_api_keys: Optional[UserApiKeys] = Field(
        default=None,
        description="User-provided API keys (required for users without HUN-REN access)"
    )

    @field_validator("analysis_type")
    @classmethod
    def validate_analysis_type(cls, v: str) -> str:
        if v not in ["quick", "deep"]:
            raise ValueError("analysis_type must be 'quick' or 'deep'")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "problem_description": {
                    "project_description": "Predict house prices based on features",
                    "target_variable": "price",
                    "features": {
                        "sqft": "Square footage of the house",
                        "bedrooms": "Number of bedrooms"
                    }
                },
                "csv_filename": "houses.csv",
                "analysis_type": "quick"
            }
        }


class ShareRequest(BaseModel):
    """Request schema for sharing configuration (if needed in future)."""
    pass


class ProfileDeleteRequest(BaseModel):
    """Request schema for profile deletion confirmation (if needed)."""
    confirm: bool = Field(
        default=False,
        description="Confirmation flag for deletion"
    )


class ValidateKeysRequest(BaseModel):
    """Request schema for API key validation."""
    openai_api_key: str = Field(
        ...,
        min_length=1,
        description="OpenAI API key to validate"
    )


class UpdatePermissionRequest(BaseModel):
    """Request schema for updating user permissions."""
    use_hunren_keys: bool = Field(
        ...,
        description="Whether to grant HUN-REN key access"
    )
