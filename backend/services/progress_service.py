"""
Progress tracking service for analysis workflow.

Tracks and persists progress of multi-step analysis runs.
This is SEPARATE from logging - it manages workflow state,
not log messages.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

import yaml

from backend.infrastructure.database.connection import get_session_factory
from backend.infrastructure.database.models import Run, RunArtifact

logger = logging.getLogger(__name__)


def _broadcast_progress_sync(
    run_id: str,
    progress: int,
    status: str,
    step_name: str | None = None,
    error: str | None = None,
    results: dict | None = None,
) -> None:
    """
    Broadcast progress update via WebSocket (sync wrapper for async broadcast).

    This is safe to call from sync code - it will schedule the broadcast
    on the event loop if one is running, or skip if not.
    """
    try:
        from backend.api.websocket.connection_manager import get_connection_manager

        manager = get_connection_manager()

        # Try to get running event loop
        try:
            loop = asyncio.get_running_loop()
            # Schedule broadcast on the running loop
            asyncio.ensure_future(
                manager.broadcast_progress(
                    run_id=run_id,
                    progress=progress,
                    status=status,
                    step_name=step_name,
                    error=error,
                    results=results,
                )
            )
        except RuntimeError:
            # No running event loop - skip broadcast
            # This happens during testing or non-async contexts
            pass
    except Exception as e:
        logger.debug(f"Could not broadcast progress: {e}")


# ============================================================================
# Progress Configuration
# ============================================================================

_progress_cache: dict[str, int] | None = None
_description_cache: dict[str, str] | None = None


def _load_progress_config() -> tuple[dict[str, int], dict[str, str]]:
    """
    Load progress phase weights and descriptions from YAML configuration.

    Returns:
        Tuple of (weights dict, descriptions dict)
    """
    config_paths = [
        Path(__file__).parent.parent / "progress_config.yaml",
        Path("backend/progress_config.yaml"),
    ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = yaml.safe_load(f)
                    phases = config.get("phases", [])
                    weights = {p["name"]: p["progress_end"] for p in phases}
                    descriptions = {
                        p["name"]: p.get("description", p.get("label", "")) for p in phases
                    }
                    return weights, descriptions
            except Exception as e:
                logger.warning(f"Failed to load progress_config.yaml: {e}")

    logger.warning("No progress_config.yaml found, using empty weights")
    return {}, {}


def get_progress_weights() -> dict[str, int]:
    """Get cached progress weights."""
    global _progress_cache, _description_cache
    if _progress_cache is None:
        _progress_cache, _description_cache = _load_progress_config()
    return _progress_cache


def get_step_description(step_name: str) -> str:
    """Get the user-friendly description for a step."""
    global _progress_cache, _description_cache
    if _description_cache is None:
        _progress_cache, _description_cache = _load_progress_config()
    return _description_cache.get(step_name, "Processing...")


def get_progress_phases():
    """Get progress phases for API response."""
    config_paths = [
        Path(__file__).parent.parent / "progress_config.yaml",
        Path("backend/progress_config.yaml"),
    ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = yaml.safe_load(f)
                    return config.get("phases", [])
            except Exception:
                pass
    return []


# ============================================================================
# Progress Tracker
# ============================================================================


class ProgressTracker:
    """
    Tracks progress for a multi-step analysis run.

    Updates progress percentage in the database as steps complete.
    Can also save artifacts (generated files) for the run.

    Usage:
        tracker = ProgressTracker(run_id="abc-123")
        tracker.update_progress("data_loading", status="Loading dataset...")
        tracker.update_progress("model_training", status="Training PySR...")
        tracker.save_artifact("results.json", json_bytes, "application/json")
    """

    def __init__(self, run_id: str):
        """
        Initialize progress tracker for a run.

        Args:
            run_id: UUID string of the run to track
        """
        self.run_id = run_id
        self.current_progress = 0
        self.step_count = 0
        self.weights = get_progress_weights()

        if not run_id:
            logger.warning(
                "ProgressTracker created without run_id - progress updates will be skipped"
            )

    def update_progress(
        self, step_name: str, status: str | None = None, details: dict[str, Any] | None = None
    ) -> None:
        """
        Update progress for a named step.

        Args:
            step_name: Name of the step (should match progress_config.yaml)
            status: Optional human-readable status message
            details: Optional dictionary of step details (logged, not stored)
        """
        if not self.run_id:
            return

        self.step_count += 1

        # Calculate progress based on weights
        if step_name in self.weights:
            progress = self.weights[step_name]
        else:
            # Unknown step: increment by 1
            progress = min(99, self.current_progress + 1)

        # Progress should only increase
        progress = max(progress, self.current_progress)
        progress = min(99, progress)  # Never hit 100 until completion
        self.current_progress = progress

        # Log the step (not the payload - security)
        if status:
            logger.info(f"[Run {self.run_id[:8]}] Step {self.step_count}: {step_name} - {status}")
        else:
            logger.info(f"[Run {self.run_id[:8]}] Step {self.step_count}: {step_name}")

        if details:
            # Log summary only, not full details
            summary = {k: type(v).__name__ for k, v in details.items()}
            logger.debug(f"  Details: {summary}")

        # Update database and broadcast via WebSocket
        self._persist_progress(progress, step_name=step_name)

    def set_progress(self, progress: int, status: str | None = None) -> None:
        """
        Explicitly set progress percentage.

        Use for fine-grained control during long operations.

        Args:
            progress: Progress percentage (0-99)
            status: Optional status message to log
        """
        if not self.run_id:
            return

        progress = min(99, max(0, progress))
        self.current_progress = progress

        if status:
            logger.info(f"[Run {self.run_id[:8]}] Progress: {progress}% - {status}")

        self._persist_progress(progress)

    def _persist_progress(self, progress: int, step_name: str | None = None) -> None:
        """Persist progress to database and broadcast via WebSocket."""
        SessionLocal = get_session_factory()
        db = SessionLocal()
        run_status = "running"
        try:
            run = db.query(Run).filter(Run.id == self.run_id).first()
            if run:
                run.progress = progress
                run_status = run.status
                db.commit()
                logger.debug(f"[Run {self.run_id[:8]}] Persisted progress: {progress}%")
        except Exception as e:
            logger.error(f"Failed to update progress for {self.run_id}: {e}")
        finally:
            db.close()

        # Broadcast to WebSocket clients
        _broadcast_progress_sync(
            run_id=self.run_id,
            progress=progress,
            status=run_status,
            step_name=step_name,
        )

    def save_artifact(self, filename: str, content: bytes, media_type: str | None = None) -> None:
        """
        Save an artifact file for the run.

        Args:
            filename: Name of the artifact file
            content: File content as bytes
            media_type: MIME type (e.g., "application/json", "image/png")
        """
        if not self.run_id:
            return

        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            artifact = RunArtifact(
                run_id=self.run_id, filename=filename, content=content, media_type=media_type
            )
            db.add(artifact)
            db.commit()
            logger.info(f"[Run {self.run_id[:8]}] Artifact saved: {filename}")
        except Exception as e:
            logger.error(f"Failed to save artifact {filename}: {e}")
        finally:
            db.close()

    # ========================================================================
    # Backward Compatibility Methods
    # ========================================================================

    def log_step(self, step_name: str, payload: Any = None) -> None:
        """
        Backward-compatible alias for update_progress.

        Args:
            step_name: Name of the step
            payload: Optional payload (logged as debug summary only)
        """
        if isinstance(payload, dict):
            status = payload.get("status")
            self.update_progress(step_name, status=status, details=payload)
        else:
            self.update_progress(step_name)

    def log_artifact(self, filename: str, content: bytes, media_type: str | None = None) -> None:
        """Backward-compatible alias for save_artifact."""
        self.save_artifact(filename, content, media_type)


# ============================================================================
# Backward Compatibility Alias
# ============================================================================

# Keep StepLogger as alias during migration
StepLogger = ProgressTracker
