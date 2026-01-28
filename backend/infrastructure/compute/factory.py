"""
Compute backend factory.

Provides factory function for creating the Slurm compute backend.
"""
import logging
from typing import Optional

from backend.core.config import get_slurm_settings
from backend.infrastructure.compute.base import ComputeBackend, ComputeBackendError

logger = logging.getLogger(__name__)

# Cached backend instance
_backend: Optional[ComputeBackend] = None


def get_compute_backend(force_new: bool = False) -> ComputeBackend:
    """
    Get the Slurm compute backend.

    Args:
        force_new: If True, create a new instance instead of using cached

    Returns:
        SlurmComputeBackend instance

    Raises:
        ComputeBackendError: If Slurm is not configured
    """
    global _backend

    if _backend is not None and not force_new:
        return _backend

    slurm_settings = get_slurm_settings()
    if not slurm_settings.is_configured:
        raise ComputeBackendError(
            "Slurm backend not configured. Set SLURM_API_URL and SLURM_AUTH_TOKEN."
        )

    from backend.infrastructure.compute.slurm_backend import SlurmComputeBackend
    _backend = SlurmComputeBackend()
    logger.info(f"Using Slurm compute backend at {slurm_settings.api_url}")

    return _backend


def clear_backend_cache() -> None:
    """Clear the cached backend. Useful for testing."""
    global _backend
    _backend = None
