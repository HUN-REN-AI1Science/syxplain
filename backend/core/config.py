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
    """Authentication settings for Keycloak integration."""

    keycloak_url: str = field(
        default_factory=lambda: os.environ.get("KEYCLOAK_URL", "http://localhost:8080/keycloak")
    )
    keycloak_realm: str = field(
        default_factory=lambda: os.environ.get("KEYCLOAK_REALM", "syxplain")
    )
    keycloak_client_id: str = field(
        default_factory=lambda: os.environ.get("KEYCLOAK_CLIENT_ID", "syxplain-frontend")
    )
    keycloak_admin_username: str = field(
        default_factory=lambda: os.environ.get("KEYCLOAK_ADMIN_USERNAME", "admin")
    )
    keycloak_admin_password: str = field(
        default_factory=lambda: os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")
    )
    keycloak_issuer: str = field(default_factory=lambda: os.environ.get("KEYCLOAK_ISSUER", ""))

    @property
    def jwks_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}/protocol/openid-connect/certs"

    @property
    def admin_api_url(self) -> str:
        return f"{self.keycloak_url}/admin/realms/{self.keycloak_realm}"

    @property
    def token_url(self) -> str:
        return f"{self.keycloak_url}/realms/master/protocol/openid-connect/token"


@dataclass
class LLMSettings:
    """LLM API settings for OpenAI-compatible endpoints."""

    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    openai_api_base: str | None = field(default_factory=lambda: os.environ.get("OPENAI_API_BASE"))
    openai_model_name: str = field(
        default_factory=lambda: os.environ.get("OPENAI_MODEL_NAME", "gpt-4o")
    )

    # Small/cheap models for lightweight tasks (e.g. column description suggestions)
    small_model_name: str = field(
        default_factory=lambda: os.environ.get("SMALL_MODEL_NAME", "gpt-5-mini")
    )
    small_user_model_name: str = field(
        default_factory=lambda: os.environ.get("SMALL_USER_MODEL_NAME", "gemini-2.5-flash")
    )

    # User-provided key model options (comma-separated)
    user_api_models: str = field(
        default_factory=lambda: os.environ.get(
            "USER_API_MODELS", "gemini-3.1-pro-preview,gemini-3-pro-preview,gemini-2.5-pro"
        )
    )

    def get_user_api_model_list(self) -> list[str]:
        """Parse comma-separated user API model list."""
        if not self.user_api_models:
            return ["gemini-3.1-pro-preview", "gemini-3-pro-preview", "gemini-2.5-pro"]
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


def _budget_value(name: str, default: float) -> float:
    """
    One budget ceiling. Values in the former "quick,deep" form (still in older .env
    files) use their last part, the deep value that is now the single budget.
    """
    raw = os.environ.get(name, "")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    try:
        return float(parts[-1]) if parts else default
    except ValueError:
        return default


@dataclass
class DiscoverySettings:
    """
    Budget of the agentic equation-discovery loop (ceilings: the agent stops when it is done).
    """

    enabled: bool = field(
        default_factory=lambda: os.environ.get("DISCOVERY_AGENT_ENABLED", "true").lower() == "true"
    )
    # Model for the agent (server keys); empty = OPENAI_MODEL_NAME
    model_name: str = field(default_factory=lambda: os.environ.get("DISCOVERY_AGENT_MODEL", ""))
    max_iters: float = field(default_factory=lambda: _budget_value("DISCOVERY_MAX_ITERS", 40))
    max_pysr_runs: float = field(
        default_factory=lambda: _budget_value("DISCOVERY_MAX_PYSR_RUNS", 6)
    )
    wall_clock_minutes: float = field(
        default_factory=lambda: _budget_value("DISCOVERY_WALL_CLOCK_MIN", 150)
    )
    max_concurrent_pysr: int = field(
        default_factory=lambda: int(os.environ.get("DISCOVERY_MAX_CONCURRENT_PYSR", "2"))
    )
    pysr_timeout_s: int = field(
        default_factory=lambda: int(os.environ.get("DISCOVERY_PYSR_TIMEOUT_S", "1800"))
    )
    # Show the SHAP plots to the agent as images (text SHAP is always given)
    shap_images: bool = field(
        default_factory=lambda: os.environ.get("DISCOVERY_SHAP_IMAGES", "true").lower() == "true"
    )
    # Read-only review steps for searches that finish after the agent stopped (0 = off)
    review_steps: int = field(
        default_factory=lambda: int(os.environ.get("DISCOVERY_REVIEW_STEPS", "5"))
    )
    # How long to wait for a first PySR result when none has completed
    first_result_timeout_s: int = field(
        default_factory=lambda: int(os.environ.get("DISCOVERY_FIRST_RESULT_TIMEOUT_S", "3600"))
    )
    # Drop a predictor whose missing values alone remove more than this share of rows
    sparse_column_threshold: float = field(
        default_factory=lambda: float(os.environ.get("DISCOVERY_SPARSE_COLUMN_THRESHOLD", "0.2"))
    )
    max_categorical_levels: int = field(
        default_factory=lambda: int(os.environ.get("DISCOVERY_MAX_CATEGORICAL_LEVELS", "10"))
    )

    def limits(self) -> dict[str, float]:
        return {
            "max_iters": int(self.max_iters),
            "max_pysr_runs": int(self.max_pysr_runs),
            "wall_clock_s": float(self.wall_clock_minutes) * 60,
            "max_concurrent_pysr": self.max_concurrent_pysr,
            "pysr_timeout_s": self.pysr_timeout_s,
            # Safety net for runaway tool use; the agent is budgeted in steps.
            "max_tool_calls": int(self.max_iters) * 2,
        }


@dataclass
class SlurmSettings:
    """
    Slurm cluster settings for slurmrestd API integration.

    Resource allocation can be configured via environment variables.
    """

    api_url: str = field(default_factory=lambda: os.environ.get("SLURM_API_URL", ""))
    auth_token: str = field(default_factory=lambda: os.environ.get("SLURM_AUTH_TOKEN", ""))
    user_name: str = field(default_factory=lambda: os.environ.get("SLURM_USER_NAME", "slurm"))
    partition: str = field(
        default_factory=lambda: os.environ.get("SLURM_PARTITION", "cpu_m2.2xlarge")
    )
    staging_dir: str = field(
        default_factory=lambda: os.environ.get("SLURM_STAGING_DIR", "/tmp/syxplain")
    )

    # Resource allocation
    cpus: int = field(default_factory=lambda: int(os.environ.get("SLURM_CPUS", "4")))
    memory: str = field(default_factory=lambda: os.environ.get("SLURM_MEMORY", "7941M"))
    time_limit: str = field(default_factory=lambda: os.environ.get("SLURM_TIME_LIMIT", "04:00:00"))

    # Singularity container path (if set, uses container instead of conda)
    container_path: str = field(default_factory=lambda: os.environ.get("SLURM_CONTAINER_PATH", ""))

    # Retry interval for quota/QOS errors (seconds)
    retry_interval: int = field(
        default_factory=lambda: int(os.environ.get("SLURM_RETRY_INTERVAL", "60"))
    )

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
class GitHubSettings:
    """GitHub integration settings for feedback system."""

    token: str = field(default_factory=lambda: os.environ.get("GITHUB_FEEDBACK_TOKEN", ""))
    repo_owner: str = field(
        default_factory=lambda: os.environ.get("GITHUB_FEEDBACK_REPO_OWNER", "")
    )
    repo_name: str = field(default_factory=lambda: os.environ.get("GITHUB_FEEDBACK_REPO_NAME", ""))

    @property
    def is_configured(self) -> bool:
        """Check if GitHub feedback is properly configured."""
        return bool(self.token and self.repo_owner and self.repo_name)


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
    discovery: DiscoverySettings = field(default_factory=DiscoverySettings)
    slurm: SlurmSettings = field(default_factory=SlurmSettings)
    compute: ComputeSettings = field(default_factory=ComputeSettings)
    github: GitHubSettings = field(default_factory=GitHubSettings)


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


def get_discovery_settings() -> DiscoverySettings:
    """Get discovery-agent settings for dependency injection."""
    return get_settings().discovery


def get_github_settings() -> GitHubSettings:
    """Get GitHub settings for dependency injection."""
    return get_settings().github
