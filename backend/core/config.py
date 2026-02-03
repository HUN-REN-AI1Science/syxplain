"""
Centralized configuration management.

Provides type-safe access to all environment variables with validation
and sensible defaults. Groups related settings for better organization.

Note: Uses standard dataclasses instead of pydantic-settings to avoid
additional dependencies. Environment variables are loaded at module import.
"""

import os
from dataclasses import dataclass, field


@dataclass
class DatabaseSettings:
    """Database connection settings."""

    url: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL", "postgresql://syxplain:syxplain@localhost:5432/syxplain"
        )
    )
    pool_size: int = field(default_factory=lambda: int(os.environ.get("DB_POOL_SIZE", "40")))
    max_overflow: int = field(default_factory=lambda: int(os.environ.get("DB_MAX_OVERFLOW", "5")))
    pool_timeout: int = field(default_factory=lambda: int(os.environ.get("DB_POOL_TIMEOUT", "30")))
    pool_recycle: int = field(default_factory=lambda: int(os.environ.get("DB_POOL_RECYCLE", "300")))


@dataclass
class AuthSettings:
    """Authentication settings for Supabase integration."""

    supabase_jwt_secret: str = field(
        default_factory=lambda: os.environ.get("SUPABASE_JWT_SECRET", "")
    )
    supabase_url: str = field(default_factory=lambda: os.environ.get("SUPABASE_URL", ""))
    supabase_service_role_key: str = field(
        default_factory=lambda: os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    )


@dataclass
class LLMSettings:
    """LLM API settings for OpenAI-compatible endpoints."""

    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    openai_api_base: str | None = field(default_factory=lambda: os.environ.get("OPENAI_API_BASE"))
    openai_model_name: str = field(
        default_factory=lambda: os.environ.get("OPENAI_MODEL_NAME", "gpt-4o")
    )

    # Deep research settings
    deep_research_api_key: str = field(
        default_factory=lambda: os.environ.get("DEEP_RESEARCH_API_KEY", "")
    )
    deep_research_api_base: str | None = field(
        default_factory=lambda: os.environ.get("DEEP_RESEARCH_API_BASE")
    )
    deep_research_models: str = field(
        default_factory=lambda: os.environ.get("DEEP_RESEARCH_MODEL", "")
    )

    # User-provided key model options (comma-separated)
    user_api_models: str = field(
        default_factory=lambda: os.environ.get("USER_API_MODELS", "gpt-5.2-thinking,gpt-4o")
    )

    def get_deep_research_model_list(self) -> list[str]:
        """Parse comma-separated model list."""
        if not self.deep_research_models:
            return []
        return [m.strip() for m in self.deep_research_models.split(",") if m.strip()]

    def get_user_api_model_list(self) -> list[str]:
        """Parse comma-separated user API model list."""
        if not self.user_api_models:
            return ["gpt-5.2-thinking", "gpt-4o"]
        return [m.strip() for m in self.user_api_models.split(",") if m.strip()]


@dataclass
class CORSSettings:
    """CORS configuration settings."""

    origins: str = field(default_factory=lambda: os.environ.get("CORS_ORIGINS", "*"))

    def get_allowed_origins(self) -> list[str]:
        """Parse allowed origins from environment variable."""
        if self.origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.origins.split(",")]


@dataclass
class AnalysisSettings:
    """Analysis workflow settings."""

    timeout_hours: float = field(
        default_factory=lambda: float(os.environ.get("ANALYSIS_TIMEOUT_HOURS", "24"))
    )
    max_file_size_mb: int = field(
        default_factory=lambda: int(os.environ.get("MAX_FILE_SIZE_MB", "50"))
    )

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@dataclass
class SHAPSettings:
    """SHAP analysis settings."""

    subsample_fraction: float = field(
        default_factory=lambda: float(os.environ.get("SHAP_SUBSAMPLE_FRACTION", "0.1"))
    )
    subsample_min: int = field(
        default_factory=lambda: int(os.environ.get("SHAP_SUBSAMPLE_MIN", "1000"))
    )
    subsample_max: int = field(
        default_factory=lambda: int(os.environ.get("SHAP_SUBSAMPLE_MAX", "5000"))
    )


@dataclass
class LangfuseSettings:
    """Langfuse tracing settings."""

    public_key: str = field(default_factory=lambda: os.environ.get("LANGFUSE_PUBLIC_KEY", ""))
    secret_key: str = field(default_factory=lambda: os.environ.get("LANGFUSE_SECRET_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
    )
    enabled: bool = field(
        default_factory=lambda: os.environ.get("LANGFUSE_ENABLED", "true").lower() == "true"
    )


@dataclass
class SlurmSettings:
    """
    Slurm cluster settings for slurmrestd API integration.

    Resource allocation can be configured via environment variables.
    """

    api_url: str = field(default_factory=lambda: os.environ.get("SLURM_API_URL", ""))
    auth_token: str = field(default_factory=lambda: os.environ.get("SLURM_AUTH_TOKEN", ""))
    user_name: str = field(default_factory=lambda: os.environ.get("SLURM_USER_NAME", "slurm"))
    partition: str = field(default_factory=lambda: os.environ.get("SLURM_PARTITION", "compute"))
    staging_dir: str = field(
        default_factory=lambda: os.environ.get("SLURM_STAGING_DIR", "/tmp/syxplain")
    )

    # Resource allocation
    cpus: int = field(default_factory=lambda: int(os.environ.get("SLURM_CPUS", "4")))
    memory: str = field(default_factory=lambda: os.environ.get("SLURM_MEMORY", "8G"))
    time_limit: str = field(default_factory=lambda: os.environ.get("SLURM_TIME_LIMIT", "04:00:00"))

    @property
    def is_configured(self) -> bool:
        """Check if Slurm is properly configured."""
        return bool(self.api_url and self.auth_token)


@dataclass
class ComputeSettings:
    """Compute backend settings."""

    worker_callback_url: str = field(
        default_factory=lambda: os.environ.get("WORKER_CALLBACK_URL", "")
    )
    worker_callback_token: str = field(
        default_factory=lambda: os.environ.get("WORKER_CALLBACK_TOKEN", "")
    )
    job_poll_interval: int = field(
        default_factory=lambda: int(os.environ.get("JOB_POLL_INTERVAL", "10"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.environ.get("COMPUTE_MAX_RETRIES", "3"))
    )


@dataclass
class AdminSettings:
    """Admin access settings."""

    admin_emails: str = field(default_factory=lambda: os.environ.get("ADMIN_EMAILS", ""))

    def get_admin_email_list(self) -> list[str]:
        """Parse comma-separated admin email list."""
        if not self.admin_emails:
            return []
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    def is_admin(self, email: str) -> bool:
        """Check if an email is in the admin list."""
        return email.lower() in self.get_admin_email_list()


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
    langfuse: LangfuseSettings = field(default_factory=LangfuseSettings)
    slurm: SlurmSettings = field(default_factory=SlurmSettings)
    compute: ComputeSettings = field(default_factory=ComputeSettings)
    admin: AdminSettings = field(default_factory=AdminSettings)


# Cached settings instance
_settings: Settings | None = None


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


def get_auth_settings() -> AuthSettings:
    """Get auth settings for dependency injection."""
    return get_settings().auth


def get_slurm_settings() -> SlurmSettings:
    """Get Slurm settings for dependency injection."""
    return get_settings().slurm


def get_compute_settings() -> ComputeSettings:
    """Get compute backend settings for dependency injection."""
    return get_settings().compute


def get_admin_settings() -> AdminSettings:
    """Get admin settings for dependency injection."""
    return get_settings().admin
