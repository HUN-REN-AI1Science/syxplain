"""
Pydantic request schemas for API endpoints.

These schemas define the structure and validation rules
for incoming request data.
"""

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from backend.core.constants import STANDARD_ANALYSIS


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
        ..., min_length=1, description="Description of the project and analysis goals"
    )
    target_variable: str = Field(
        ..., min_length=1, description="Name of the target variable to predict"
    )
    features: dict[str, str] = Field(
        ..., description="Dictionary mapping feature names to their descriptions"
    )

    @field_validator("features")
    @classmethod
    def features_not_empty(cls, v: dict[str, str]) -> dict[str, str]:
        if not v:
            raise ValueError("At least one feature must be specified")
        return v


class UserApiKeys(BaseModel):
    """User-provided API keys (not stored)."""

    gemini_api_key: str = Field(..., min_length=1, description="Google Gemini API key for analysis")
    gemini_model: str = Field(default="gemini-3.1-pro-preview", description="Gemini model to use")
    openai_api_key: str | None = Field(
        default=None, description="OpenAI API key for the literature search (optional)"
    )


class RunRequest(BaseModel):
    """Request schema for starting an analysis run."""

    problem_description: ProblemDescription
    csv_filename: str = Field(..., min_length=1, description="Name of the uploaded file to analyze")
    analysis_type: str = Field(
        default=STANDARD_ANALYSIS,
        description="Deprecated and ignored: there is one analysis, which always runs the full pipeline",
    )
    deep_research_model: str | None = Field(default=None, description="Deprecated and ignored")
    user_api_keys: UserApiKeys | None = Field(
        default=None,
        description="User-provided API keys (required for users without HUN-REN access)",
    )

    @field_validator("analysis_type")
    @classmethod
    def validate_analysis_type(cls, v: str) -> str:
        # Legacy 'quick'/'deep' are accepted so existing clients keep working
        return STANDARD_ANALYSIS

    class Config:
        json_schema_extra = {
            "example": {
                "problem_description": {
                    "project_description": "Predict house prices based on features",
                    "target_variable": "price",
                    "features": {
                        "sqft": "Square footage of the house",
                        "bedrooms": "Number of bedrooms",
                    },
                },
                "csv_filename": "houses.csv",
            }
        }


class ValidateKeysRequest(BaseModel):
    """Request schema for API key validation."""

    gemini_api_key: str | None = Field(
        default=None, description="Google Gemini API key to validate"
    )
    openai_api_key: str | None = Field(default=None, description="OpenAI API key to validate")


class SuggestDescriptionsRequest(BaseModel):
    """Request schema for automatic column description suggestions."""

    project_description: str = Field(
        ..., min_length=10, description="Description of the project and analysis goals"
    )
    target_variable: str | None = Field(default=None, description="Target variable name")
    columns: list[str] = Field(
        ..., min_length=1, max_length=200, description="Column names to describe"
    )
    gemini_api_key: str | None = Field(
        default=None,
        description="User-provided Gemini API key (required without HUN-REN access)",
    )
    gemini_model: str | None = Field(
        default=None,
        description="Gemini model to use with the user-provided key",
    )


class FeedbackCategory(str, Enum):
    """Category of user feedback."""

    BUG = "bug"
    FEATURE = "feature"


class FeedbackContext(BaseModel):
    """Auto-collected application context for feedback."""

    current_view: str | None = None
    workflow_step: int | None = None
    current_run_id: str | None = None
    csv_filename: str | None = None
    browser_user_agent: str | None = None
    screen_resolution: str | None = None
    timestamp: str | None = None
    app_url: str | None = None


class FeedbackRequest(BaseModel):
    """Request schema for submitting user feedback."""

    category: FeedbackCategory
    title: str = Field(
        ..., min_length=1, max_length=100, description="Short summary of the feedback"
    )
    description: str = Field(
        ..., min_length=10, max_length=2000, description="Detailed description"
    )
    context: FeedbackContext | None = None
