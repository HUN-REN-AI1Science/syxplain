"""
Pre-flight check of the Slurm REST API, done before a run is accepted.
"""

import logging
import time

import httpx

from backend.core.config import get_slurm_settings
from backend.infrastructure.slurm.client import API_VERSION

logger = logging.getLogger(__name__)

_health_cache: dict[str, float | bool] = {"ts": 0.0, "ok": False}
_HEALTH_TTL = 30.0  # seconds


async def is_slurm_reachable() -> bool:
    """Check slurmrestd is reachable, cached for 30s to avoid per-request overhead."""
    now = time.monotonic()
    if now - _health_cache["ts"] < _HEALTH_TTL:
        return bool(_health_cache["ok"])

    try:
        settings = get_slurm_settings()
        if not settings.api_url or not settings.auth_token:
            result = False
        else:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(
                    f"{settings.api_url}/slurm/{API_VERSION}/diag",
                    headers={
                        "Authorization": f"Bearer {settings.auth_token}",
                        "Slurm-User-Name": settings.user_name,
                    },
                )
            result = response.status_code == 200
    except Exception as e:
        logger.debug(f"Slurm pre-flight check failed: {e}")
        result = False

    _health_cache["ts"] = now
    _health_cache["ok"] = result
    return result
