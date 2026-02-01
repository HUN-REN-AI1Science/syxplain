"""
Slurm compute backend implementation.

Executes compute tasks on a Slurm cluster via slurmrestd API.
"""
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from backend.core.config import get_slurm_settings, get_compute_settings
from backend.utils.security_utils import (
    shell_escape,
    validate_slurm_identifier,
    validate_url,
)
from backend.infrastructure.compute.base import (
    ComputeBackend,
    ComputeBackendError,
    ComputeJob,
    ComputeTaskInput,
    JobNotCompletedError,
    JobNotFoundError,
    TaskState,
    TaskStatus,
)
from backend.infrastructure.slurm.client import (
    SlurmClient,
    SlurmClientError,
    SlurmJobNotFoundError,
)
from backend.infrastructure.slurm.models import (
    JobState,
    SlurmJobSubmission,
)

logger = logging.getLogger(__name__)

# Map Slurm job states to TaskState
_STATE_MAP = {
    JobState.PENDING: TaskState.PENDING,
    JobState.RUNNING: TaskState.RUNNING,
    JobState.COMPLETED: TaskState.COMPLETED,
    JobState.FAILED: TaskState.FAILED,
    JobState.CANCELLED: TaskState.CANCELLED,
    JobState.TIMEOUT: TaskState.TIMEOUT,
    JobState.NODE_FAIL: TaskState.FAILED,
    JobState.PREEMPTED: TaskState.CANCELLED,
    JobState.BOOT_FAIL: TaskState.FAILED,
    JobState.DEADLINE: TaskState.TIMEOUT,
    JobState.OUT_OF_MEMORY: TaskState.FAILED,
    JobState.UNKNOWN: TaskState.PENDING,
}


class SlurmComputeBackend(ComputeBackend):
    """
    Slurm compute backend using slurmrestd API.

    Submits tasks as Slurm jobs, stages input/output files, and monitors
    job status through the Slurm REST API.
    """

    def __init__(self, client: Optional[SlurmClient] = None):
        """
        Initialize Slurm backend.

        Args:
            client: Optional SlurmClient instance (creates new one if not provided)
        """
        self._client = client
        self._jobs: Dict[str, Dict[str, Any]] = {}

    @property
    def name(self) -> str:
        return "slurm"

    async def _get_client(self) -> SlurmClient:
        """Get or create Slurm client."""
        if self._client is None:
            self._client = SlurmClient()
        return self._client

    def _generate_worker_script(
        self,
        task: ComputeTaskInput,
        input_path: str,
        output_path: str,
    ) -> str:
        """
        Generate the Slurm job script for executing a task.

        Args:
            task: Task specification
            input_path: Path to input JSON file on Slurm
            output_path: Path for output JSON file

        Returns:
            Bash script content

        Raises:
            ValueError: If task contains invalid identifiers or URLs
        """
        compute_settings = get_compute_settings()

        # Validate identifiers to prevent injection (raises ValueError if invalid)
        validate_slurm_identifier(task.task_type, "task_type")
        validate_slurm_identifier(task.run_id, "run_id")

        # Build environment variables for the worker with proper escaping
        env_vars = []
        if task.callback_url:
            # Validate URL scheme before escaping
            validate_url(task.callback_url, "callback_url")
            escaped_url = shell_escape(task.callback_url)
            env_vars.append(f'export CALLBACK_URL={escaped_url}')
        if task.callback_token:
            escaped_token = shell_escape(task.callback_token)
            env_vars.append(f'export CALLBACK_TOKEN={escaped_token}')

        env_section = "\n".join(env_vars) if env_vars else "# No callback configured"

        # Escape paths for safe interpolation
        escaped_input_path = shell_escape(input_path)
        escaped_output_path = shell_escape(output_path)

        script = f"""#!/bin/bash
#SBATCH --job-name=syxplain-{task.task_type}-{task.run_id[:8]}
#SBATCH --output={output_path}.stdout
#SBATCH --error={output_path}.stderr

# Environment setup
{env_section}

# Activate conda environment if available
if command -v conda &> /dev/null; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate syxplain_worker 2>/dev/null || true
fi

# Run the worker script
python -m syxplain_worker \\
    --task-type {task.task_type} \\
    --run-id {task.run_id} \\
    --input {escaped_input_path} \\
    --output {escaped_output_path}

# Exit with worker's exit code
exit $?
"""
        return script

    async def submit_task(self, task: ComputeTaskInput) -> ComputeJob:
        """Submit task to Slurm cluster."""
        client = await self._get_client()
        slurm_settings = get_slurm_settings()
        compute_settings = get_compute_settings()

        # Generate unique job identifier
        job_uuid = str(uuid.uuid4())
        staging_dir = f"{slurm_settings.staging_dir}/{job_uuid}"

        logger.info(
            f"Submitting {task.task_type} task to Slurm for run {task.run_id}"
        )

        try:
            # Serialize and upload input data
            input_json = json.dumps(task.input_data).encode("utf-8")
            input_path = await client.upload_file(
                job_id=job_uuid,
                filename="input.json",
                content=input_json,
            )

            output_path = f"{staging_dir}/output.json"

            # Generate job script
            script = self._generate_worker_script(task, input_path, output_path)

            # Create submission - use partition defaults configured in Slurm
            submission = SlurmJobSubmission(
                script=script,
                name=f"syxplain-{task.task_type}-{task.run_id[:8]}",
                partition=slurm_settings.partition,
                working_directory=staging_dir,
            )

            # Submit to Slurm
            slurm_job_id = await client.submit_job(submission)

            # Track job
            self._jobs[job_uuid] = {
                "slurm_job_id": slurm_job_id,
                "task": task,
                "staging_dir": staging_dir,
                "input_path": input_path,
                "output_path": output_path,
                "submitted_at": datetime.utcnow(),
            }

            logger.info(
                f"Slurm job {slurm_job_id} submitted for task {job_uuid}"
            )

            return ComputeJob(
                job_id=job_uuid,
                task_type=task.task_type,
                run_id=task.run_id,
                backend=self.name,
                status=TaskStatus(
                    job_id=job_uuid,
                    state=TaskState.PENDING,
                    progress=0,
                ),
                metadata={"slurm_job_id": slurm_job_id},
            )

        except SlurmClientError as e:
            raise ComputeBackendError(f"Failed to submit task to Slurm: {e}") from e

    async def get_task_status(self, job_id: str) -> TaskStatus:
        """Get status of a Slurm job."""
        if job_id not in self._jobs:
            raise JobNotFoundError(f"Job {job_id} not found")

        job_data = self._jobs[job_id]
        slurm_job_id = job_data["slurm_job_id"]

        client = await self._get_client()

        try:
            slurm_status = await client.get_job_status(slurm_job_id)
            task_state = _STATE_MAP.get(slurm_status.state, TaskState.PENDING)

            # Estimate progress based on state
            progress = 0
            if task_state == TaskState.RUNNING:
                progress = 50  # Running but no finer granularity
            elif task_state == TaskState.COMPLETED:
                progress = 100

            return TaskStatus(
                job_id=job_id,
                state=task_state,
                progress=progress,
                message=slurm_status.reason,
                error=slurm_status.reason if task_state == TaskState.FAILED else None,
                started_at=slurm_status.start_time,
                completed_at=slurm_status.end_time,
            )

        except SlurmJobNotFoundError:
            raise JobNotFoundError(f"Slurm job {slurm_job_id} not found")
        except SlurmClientError as e:
            raise ComputeBackendError(f"Failed to get job status: {e}") from e

    async def get_task_result(self, job_id: str) -> Dict[str, Any]:
        """Get results of a completed Slurm job."""
        if job_id not in self._jobs:
            raise JobNotFoundError(f"Job {job_id} not found")

        # First check status
        status = await self.get_task_status(job_id)
        if status.state != TaskState.COMPLETED:
            raise JobNotCompletedError(
                f"Job {job_id} is in state {status.state.value}"
            )

        job_data = self._jobs[job_id]
        output_path = job_data["output_path"]

        client = await self._get_client()

        try:
            # Download output file
            output_bytes = await client.download_file(output_path)
            result = json.loads(output_bytes.decode("utf-8"))

            logger.info(f"Retrieved results for job {job_id}")
            return result

        except SlurmClientError as e:
            raise ComputeBackendError(f"Failed to retrieve results: {e}") from e

    async def cancel_task(self, job_id: str) -> bool:
        """Cancel a Slurm job."""
        if job_id not in self._jobs:
            raise JobNotFoundError(f"Job {job_id} not found")

        job_data = self._jobs[job_id]
        slurm_job_id = job_data["slurm_job_id"]

        client = await self._get_client()

        try:
            return await client.cancel_job(slurm_job_id)
        except SlurmClientError as e:
            raise ComputeBackendError(f"Failed to cancel job: {e}") from e

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 10.0,
        timeout: Optional[float] = None,
    ) -> TaskStatus:
        """Wait for Slurm job to complete."""
        if job_id not in self._jobs:
            raise JobNotFoundError(f"Job {job_id} not found")

        job_data = self._jobs[job_id]
        slurm_job_id = job_data["slurm_job_id"]

        client = await self._get_client()

        try:
            # Use Slurm client's wait_for_completion
            slurm_status = await client.wait_for_completion(
                slurm_job_id,
                poll_interval=int(poll_interval),
                timeout=timeout,
            )

            task_state = _STATE_MAP.get(slurm_status.state, TaskState.PENDING)

            return TaskStatus(
                job_id=job_id,
                state=task_state,
                progress=100 if task_state == TaskState.COMPLETED else 0,
                message=slurm_status.reason,
                error=slurm_status.reason if task_state == TaskState.FAILED else None,
                started_at=slurm_status.start_time,
                completed_at=slurm_status.end_time,
            )

        except SlurmClientError as e:
            raise ComputeBackendError(f"Error waiting for job: {e}") from e

    async def close(self) -> None:
        """Close the Slurm client connection."""
        if self._client:
            await self._client.close()
            self._client = None
