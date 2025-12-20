"""
Centralized configuration management.

Provides type-safe access to all environment variables with validation
and sensible defaults. Groups related settings for better organization.

Note: Uses standard dataclasses instead of pydantic-settings to avoid
additional dependencies. Environment variables are loaded at module import.
"""
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional


@dataclass
class DatabaseSettings:
    """Database connection settings."""
    url: str = field(default_factory=lambda: os.environ.get(
        "DATABASE_URL",
        "postgresql://syxplain:syxplain@localhost:5432/syxplain"
    ))
    pool_size: int = field(default_factory=lambda: int(os.environ.get("DB_POOL_SIZE", "40")))
    max_overflow: int = field(default_factory=lambda: int(os.environ.get("DB_MAX_OVERFLOW", "5")))
    pool_timeout: int = field(default_factory=lambda: int(os.environ.get("DB_POOL_TIMEOUT", "30")))
    pool_recycle: int = field(default_factory=lambda: int(os.environ.get("DB_POOL_RECYCLE", "300")))


@dataclass
class AuthSettings:
    """Authentication settings for Supabase integration."""
    supabase_jwt_secret: str = field(default_factory=lambda: os.environ.get("SUPABASE_JWT_SECRET", ""))
    supabase_url: str = field(default_factory=lambda: os.environ.get("SUPABASE_URL", ""))
    supabase_service_role_key: str = field(default_factory=lambda: os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))


@dataclass
class LLMSettings:
    """LLM API settings for OpenAI-compatible endpoints."""
    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    openai_api_base: Optional[str] = field(default_factory=lambda: os.environ.get("OPENAI_API_BASE"))
    openai_model_name: str = field(default_factory=lambda: os.environ.get("OPENAI_MODEL_NAME", "gpt-4o"))

    # Deep research settings
    deep_research_api_key: str = field(default_factory=lambda: os.environ.get("DEEP_RESEARCH_API_KEY", ""))
    deep_research_api_base: Optional[str] = field(default_factory=lambda: os.environ.get("DEEP_RESEARCH_API_BASE"))
    deep_research_models: str = field(default_factory=lambda: os.environ.get("DEEP_RESEARCH_MODEL", ""))

    def get_deep_research_model_list(self) -> List[str]:
        """Parse comma-separated model list."""
        if not self.deep_research_models:
            return []
        return [m.strip() for m in self.deep_research_models.split(",") if m.strip()]


@dataclass
class CORSSettings:
    """CORS configuration settings."""
    origins: str = field(default_factory=lambda: os.environ.get("CORS_ORIGINS", "*"))

    def get_allowed_origins(self) -> List[str]:
        """Parse allowed origins from environment variable."""
        if self.origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.origins.split(",")]


@dataclass
class AnalysisSettings:
    """Analysis workflow settings."""
    timeout_hours: float = field(default_factory=lambda: float(os.environ.get("ANALYSIS_TIMEOUT_HOURS", "24")))
    max_file_size_mb: int = field(default_factory=lambda: int(os.environ.get("MAX_FILE_SIZE_MB", "50")))

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@dataclass
class SHAPSettings:
    """SHAP analysis settings."""
    subsample_fraction: float = field(default_factory=lambda: float(os.environ.get("SHAP_SUBSAMPLE_FRACTION", "0.1")))
    subsample_min: int = field(default_factory=lambda: int(os.environ.get("SHAP_SUBSAMPLE_MIN", "1000")))
    subsample_max: int = field(default_factory=lambda: int(os.environ.get("SHAP_SUBSAMPLE_MAX", "5000")))


@dataclass
class Settings:
    """
    Main settings class that aggregates all configuration groups.

    Usage:
        from backend.core.config import get_settings
        settings = get_settings()
        print(settings.database.url)
    """
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    auth: AuthSettings = field(default_factory=AuthSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    cors: CORSSettings = field(default_factory=CORSSettings)
    analysis: AnalysisSettings = field(default_factory=AnalysisSettings)
    shap: SHAPSettings = field(default_factory=SHAPSettings)


# Cached settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses module-level caching to ensure settings are only loaded once,
    improving performance and maintaining consistency.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def clear_settings_cache() -> None:
    """Clear the settings cache. Useful for testing."""
    global _settings
    _settings = None


# Convenience function for accessing settings in dependency injection
def get_database_settings() -> DatabaseSettings:
    """Get database settings for dependency injection."""
    return get_settings().database


def get_auth_settings() -> AuthSettings:
    """Get auth settings for dependency injection."""
    return get_settings().auth


def get_llm_settings() -> LLMSettings:
    """Get LLM settings for dependency injection."""
    return get_settings().llm
