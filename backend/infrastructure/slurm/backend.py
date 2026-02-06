"""
Slurm compute backend.

Executes compute tasks on a Slurm cluster via slurmrestd API.
"""

import logging
import uuid
from datetime import datetime
from collections.abc import Callable
from typing import Any

from backend.core.config import get_slurm_settings
from backend.infrastructure.database.connection import get_db_session
from backend.infrastructure.database.models import Run
from backend.infrastructure.slurm.client import (
    SlurmClient,
    SlurmClientError,
    SlurmJobNotFoundError,
)
from backend.infrastructure.slurm.models import (
    JobState,
    SlurmJobSubmission,
    SlurmTask,
    TaskInput,
    TaskResult,
)
from backend.utils.security_utils import (
    shell_escape,
    validate_slurm_identifier,
    validate_url,
)

logger = logging.getLogger(__name__)


class SlurmBackendError(Exception):
    """Error in Slurm backend operations."""

    pass


class JobNotFoundError(SlurmBackendError):
    """Job not found in backend."""

    pass


class JobNotCompletedError(SlurmBackendError):
    """Job has not completed successfully."""

    pass


class SlurmBackend:
    """
    Slurm compute backend using slurmrestd API.

    Submits tasks as Slurm jobs and monitors job status through the REST API.
    """

    def __init__(self, client: SlurmClient | None = None):
        self._client = client
        self._tasks: dict[str, dict[str, Any]] = {}

    @property
    def name(self) -> str:
        return "slurm"

    async def _get_client(self) -> SlurmClient:
        """Get or create Slurm client."""
        if self._client is None:
            self._client = SlurmClient()
        return self._client

    def _generate_worker_script(self, task: TaskInput, output_path: str) -> str:
        """Generate the Slurm job script for executing a task."""
        slurm_settings = get_slurm_settings()

        # Validate identifiers to prevent injection
        validate_slurm_identifier(task.task_type, "task_type")
        validate_slurm_identifier(task.run_id, "run_id")

        # Build environment variables
        env_vars = []
        if task.callback_url:
            validate_url(task.callback_url, "callback_url")
            env_vars.append(f"export CALLBACK_URL={shell_escape(task.callback_url)}")
        if task.callback_token:
            env_vars.append(f"export CALLBACK_TOKEN={shell_escape(task.callback_token)}")

        env_section = "\n".join(env_vars) if env_vars else "# No callback configured"
        escaped_output_path = shell_escape(output_path)

        # Use Singularity container if configured
        if slurm_settings.container_path:
            escaped_container = shell_escape(slurm_settings.container_path)
            worker_command = f"""# Run worker in Singularity container
singularity run \\
    --writable-tmpfs \\
    --bind /storage:/storage \\
    --cleanenv \\
    --env CALLBACK_URL="$CALLBACK_URL" \\
    --env CALLBACK_TOKEN="$CALLBACK_TOKEN" \\
    --env JULIA_DEPOT_PATH="/tmp/.julia:/opt/julia-depot" \\
    {escaped_container} \\
    --task-type {task.task_type} \\
    --run-id {task.run_id} \\
    --output {escaped_output_path}"""
        else:
            worker_command = f"""# Activate conda environment if available
if command -v conda &> /dev/null; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate syxplain_worker 2>/dev/null || true
fi

python -m slurm_worker \\
    --task-type {task.task_type} \\
    --run-id {task.run_id} \\
    --output {escaped_output_path}"""

        output_dir = "/".join(output_path.split("/")[:-1])

        return f"""#!/bin/bash
#SBATCH --job-name=syxplain-{task.task_type}-{task.run_id[:8]}
#SBATCH --output=/tmp/syxplain_%j.stdout
#SBATCH --error=/tmp/syxplain_%j.stderr

# Environment setup
{env_section}

# Create output directory
mkdir -p {output_dir}

{worker_command}

exit $?
"""

    async def submit_task(self, task: TaskInput) -> SlurmTask:
        """Submit task to Slurm cluster."""
        client = await self._get_client()
        slurm_settings = get_slurm_settings()

        job_uuid = str(uuid.uuid4())
        logger.info(f"Submitting {task.task_type} task to Slurm for run {task.run_id}")

        # Store input data in Run record for worker to fetch via HTTP
        with get_db_session() as db:
            run = db.query(Run).filter(Run.id == task.run_id).first()
            if run:
                input_store = dict(run.input_data) if run.input_data else {}
                input_store[task.task_type] = task.input_data
                run.input_data = input_store
                db.commit()

        try:
            output_path = f"/tmp/syxplain_{job_uuid}/output.json"
            script = self._generate_worker_script(task, output_path)

            submission = SlurmJobSubmission(
                script=script,
                name=f"syxplain-{task.task_type}-{task.run_id[:8]}",
                partition=slurm_settings.partition,
                cpus=slurm_settings.cpus,
                memory=slurm_settings.memory,
                time_limit=slurm_settings.time_limit,
                working_directory=slurm_settings.staging_dir,
            )

            slurm_job_id = await client.submit_job(submission)

            self._tasks[job_uuid] = {
                "slurm_job_id": slurm_job_id,
                "task": task,
                "output_path": output_path,
                "submitted_at": datetime.utcnow(),
            }

            logger.info(f"Slurm job {slurm_job_id} submitted for task {job_uuid}")

            return SlurmTask(
                job_id=job_uuid,
                slurm_job_id=slurm_job_id,
                task_type=task.task_type,
                run_id=task.run_id,
                state=JobState.PENDING,
                metadata={"slurm_job_id": slurm_job_id},
            )

        except SlurmClientError as e:
            raise SlurmBackendError(f"Failed to submit task to Slurm: {e}") from e

    async def get_task_status(self, job_id: str) -> TaskResult:
        """Get status of a Slurm job."""
        if job_id not in self._tasks:
            raise JobNotFoundError(f"Job {job_id} not found")

        task_data = self._tasks[job_id]
        slurm_job_id = task_data["slurm_job_id"]
        client = await self._get_client()

        try:
            slurm_status = await client.get_job_status(slurm_job_id)

            progress = 0
            if slurm_status.state == JobState.RUNNING:
                progress = 50
            elif slurm_status.state == JobState.COMPLETED:
                progress = 100

            return TaskResult(
                job_id=job_id,
                state=slurm_status.state,
                progress=progress,
                message=slurm_status.reason,
                error=slurm_status.reason if slurm_status.state == JobState.FAILED else None,
                started_at=slurm_status.start_time,
                completed_at=slurm_status.end_time,
            )

        except SlurmJobNotFoundError:
            raise JobNotFoundError(f"Slurm job {slurm_job_id} not found")
        except SlurmClientError as e:
            raise SlurmBackendError(f"Failed to get job status: {e}") from e

    async def get_task_result(self, job_id: str) -> dict[str, Any]:
        """Get results of a completed Slurm job."""
        if job_id not in self._tasks:
            raise JobNotFoundError(f"Job {job_id} not found")

        status = await self.get_task_status(job_id)
        if status.state != JobState.COMPLETED:
            raise JobNotCompletedError(f"Job {job_id} is in state {status.state.value}")

        task_data = self._tasks[job_id]
        task = task_data["task"]

        # Results are stored in Run record via worker callback
        with get_db_session() as db:
            run = db.query(Run).filter(Run.id == task.run_id).first()
            if run and run.results:
                logger.info(f"Retrieved results for job {job_id} from database")
                return run.results

        raise SlurmBackendError(f"Results not found for job {job_id}")

    async def cancel_task(self, job_id: str) -> bool:
        """Cancel a Slurm job."""
        if job_id not in self._tasks:
            raise JobNotFoundError(f"Job {job_id} not found")

        task_data = self._tasks[job_id]
        slurm_job_id = task_data["slurm_job_id"]
        client = await self._get_client()

        try:
            return await client.cancel_job(slurm_job_id)
        except SlurmClientError as e:
            raise SlurmBackendError(f"Failed to cancel job: {e}") from e

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 10.0,
        timeout: float | None = None,
        on_state_change: Callable | None = None,
    ) -> TaskResult:
        """Wait for Slurm job to complete."""
        if job_id not in self._tasks:
            raise JobNotFoundError(f"Job {job_id} not found")

        task_data = self._tasks[job_id]
        slurm_job_id = task_data["slurm_job_id"]
        client = await self._get_client()

        try:
            slurm_status = await client.wait_for_completion(
                slurm_job_id,
                poll_interval=int(poll_interval),
                timeout=timeout,
                on_state_change=on_state_change,
            )

            return TaskResult(
                job_id=job_id,
                state=slurm_status.state,
                progress=100 if slurm_status.state == JobState.COMPLETED else 0,
                message=slurm_status.reason,
                error=slurm_status.reason if slurm_status.state == JobState.FAILED else None,
                started_at=slurm_status.start_time,
                completed_at=slurm_status.end_time,
            )

        except SlurmClientError as e:
            raise SlurmBackendError(f"Error waiting for job: {e}") from e

    async def close(self) -> None:
        """Close the Slurm client connection."""
        if self._client:
            await self._client.close()
            self._client = None


# =============================================================================
# Factory / Singleton
# =============================================================================

_backend: SlurmBackend | None = None


def get_slurm_backend(force_new: bool = False) -> SlurmBackend:
    """
    Get the Slurm compute backend.

    Args:
        force_new: If True, create a new instance instead of using cached

    Returns:
        SlurmBackend instance

    Raises:
        SlurmBackendError: If Slurm is not configured
    """
    global _backend

    if _backend is not None and not force_new:
        return _backend

    slurm_settings = get_slurm_settings()
    if not slurm_settings.is_configured:
        raise SlurmBackendError(
            "Slurm backend not configured. Set SLURM_API_URL and SLURM_AUTH_TOKEN."
        )

    _backend = SlurmBackend()
    logger.info(f"Using Slurm compute backend at {slurm_settings.api_url}")

    return _backend


def clear_backend_cache() -> None:
    """Clear the cached backend. Useful for testing."""
    global _backend
    _backend = None
