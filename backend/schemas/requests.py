"""
Pydantic request schemas for API endpoints.

These schemas define the structure and validation rules
for incoming request data.
"""

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.utils.user_llm import (
    LLMProvider,
    UserLLM,
    normalize_api_base,
    resolve_literature_key,
)


class SortField(str, Enum):
    """Valid fields for sorting runs."""

    CREATED_AT = "created_at"
    CSV_FILENAME = "csv_filename"
    STATUS = "status"


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


class UserLLMFields(BaseModel):
    """
    The main LLM of a user who brings their own key: Google Gemini or any
    OpenAI-compatible endpoint. The keys are never stored.

    `gemini_api_key` / `gemini_model` are the legacy field names (the programmatic API
    and older clients send them); they fill `api_key` / `model`.
    """

    provider: LLMProvider = Field(
        default="gemini", description="LLM provider: 'gemini' or 'openai_compatible'"
    )
    api_key: str | None = Field(default=None, description="API key for the chosen provider")
    model: str | None = Field(
        default=None,
        description="Model name (a Gemini model, or any model the OpenAI-compatible endpoint serves)",
    )
    api_base: str | None = Field(
        default=None,
        description="Base URL of the OpenAI-compatible endpoint (default: https://api.openai.com/v1)",
    )
    gemini_api_key: str | None = Field(
        default=None, description="Legacy alias of api_key for the Gemini provider"
    )
    gemini_model: str | None = Field(
        default=None, description="Legacy alias of model for the Gemini provider"
    )
    openai_api_key: str | None = Field(
        default=None,
        description=(
            "OpenAI API key for the literature search (optional; the main key is used "
            "when it is an OpenAI key on the default OpenAI endpoint)"
        ),
    )

    @model_validator(mode="after")
    def _normalize_llm_fields(self):
        self.api_key = (self.api_key or self.gemini_api_key or "").strip() or None
        self.model = (self.model or self.gemini_model or "").strip() or None
        if self.provider == "gemini":
            # Gemini is reached through its own SDK route; a base URL means nothing there
            self.api_base = None
        else:
            self.api_base = normalize_api_base(self.api_base)
            if self.api_key and not self.model:
                raise ValueError("model is required for an OpenAI-compatible endpoint")
        return self

    def to_user_llm(self) -> UserLLM:
        """The settings to pass down to the run, with the literature key resolved."""
        return UserLLM(
            api_key=self.api_key,
            model=self.model,
            api_base=self.api_base,
            openai_key=resolve_literature_key(self.api_key, self.api_base, self.openai_api_key),
        )


class UserApiKeys(UserLLMFields):
    """User-provided API keys (not stored)."""

    @model_validator(mode="after")
    def _require_api_key(self):
        if not self.api_key:
            raise ValueError("api_key is required")
        return self


class RunRequest(BaseModel):
    """Request schema for starting an analysis run."""

    problem_description: ProblemDescription
    csv_filename: str = Field(..., min_length=1, description="Name of the uploaded file to analyze")
    user_api_keys: UserApiKeys | None = Field(
        default=None,
        description="User-provided API keys (required for users without HUN-REN access)",
    )

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


class ValidateKeysRequest(UserLLMFields):
    """
    Request schema for API key validation: the main LLM settings (Gemini or an
    OpenAI-compatible endpoint) and/or the separate literature-search OpenAI key.
    """


class SuggestDescriptionsRequest(UserLLMFields):
    """Request schema for automatic column description suggestions."""

    project_description: str = Field(
        ..., min_length=10, description="Description of the project and analysis goals"
    )
    target_variable: str | None = Field(default=None, description="Target variable name")
    columns: list[str] = Field(
        ..., min_length=1, max_length=200, description="Column names to describe"
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
