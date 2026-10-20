"""
Mock slurmrestd server for local development.

Impersonates the slurmrestd REST API (v0.0.41) so the backend can submit
and monitor jobs without a real Slurm cluster.

- PySR tasks: faked (avoids needing Julia/PySR installed). The mock fetches
  the task input from the backend and returns least-squares equations over the
  requested features, so agent-launched searches get plausible results.
- Other task types: launched as real ``python -m slurm_worker`` subprocesses

Usage:
    python dev/mock_slurmrestd.py --port 6820
"""

import argparse
import atexit
import logging
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

import requests as http_requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [mock-slurm] %(levelname)s %(message)s",
)
logger = logging.getLogger("mock_slurmrestd")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class MockJobState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class MockJob:
    job_id: int
    process: subprocess.Popen | None = None
    state: MockJobState = MockJobState.PENDING
    submit_time: int = 0
    start_time: int = 0
    end_time: int = 0
    exit_code: int = 0
    script: str = ""
    env: dict[str, str] = field(default_factory=dict)
    task_type: str = ""
    task_key: str = ""
    run_id: str = ""
    output_path: str = ""


# ---------------------------------------------------------------------------
# Thread-safe job store
# ---------------------------------------------------------------------------


class JobStore:
    def __init__(self):
        self._jobs: dict[int, MockJob] = {}
        self._lock = threading.Lock()
        self._next_id = 1000

    def create(self, script: str) -> MockJob:
        with self._lock:
            job_id = self._next_id
            self._next_id += 1
            job = MockJob(
                job_id=job_id,
                submit_time=int(time.time()),
                script=script,
            )
            self._jobs[job_id] = job
            return job

    def get(self, job_id: int) -> MockJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all_running(self) -> list[MockJob]:
        with self._lock:
            return [
                j
                for j in self._jobs.values()
                if j.state in (MockJobState.PENDING, MockJobState.RUNNING)
            ]


store = JobStore()

# ---------------------------------------------------------------------------
# Script parsing
# ---------------------------------------------------------------------------


def _extract_env_var(script: str, name: str) -> str:
    """Extract ``export NAME='value'`` or ``export NAME="value"`` from script."""
    # Try single-quoted
    m = re.search(rf"export\s+{name}='([^']*)'", script)
    if m:
        return m.group(1)
    # Try double-quoted
    m = re.search(rf'export\s+{name}="([^"]*)"', script)
    if m:
        return m.group(1)
    # Try unquoted
    m = re.search(rf"export\s+{name}=(\S+)", script)
    if m:
        return m.group(1)
    return ""


def _extract_worker_args(script: str) -> dict[str, str]:
    """Extract worker CLI arguments from the bash script."""
    args: dict[str, str] = {}
    m = re.search(r"--task-type\s+(\S+)", script)
    if m:
        args["task_type"] = m.group(1)
    m = re.search(r"--task-key\s+(\S+)", script)
    if m:
        args["task_key"] = m.group(1)
    m = re.search(r"--run-id\s+(\S+)", script)
    if m:
        args["run_id"] = m.group(1)
    m = re.search(r"--output\s+(\S+)", script)
    if m:
        args["output"] = m.group(1)
    return args


def _parse_job_script(job: MockJob) -> tuple[str, str]:
    """Parse script and populate job fields. Returns (callback_url, callback_token)."""
    worker_args = _extract_worker_args(job.script)
    job.task_type = worker_args.get("task_type", "unknown")
    job.task_key = worker_args.get("task_key", job.task_type)
    job.run_id = worker_args.get("run_id", "unknown")
    job.output_path = worker_args.get("output", "/tmp/output.json")
    callback_url = _extract_env_var(job.script, "CALLBACK_URL")
    callback_token = _extract_env_var(job.script, "CALLBACK_TOKEN")
    return callback_url, callback_token


# ---------------------------------------------------------------------------
# Mock PySR results
# ---------------------------------------------------------------------------


def _mock_pysr_results(task_input: dict | None) -> dict:
    """
    Plausible PySR-style output: least-squares fits of a few simple forms over
    the requested features (constants are real, so the backend re-scores sensibly).
    """
    import numpy as np

    if not task_input:
        return {"status": "success", "equations": [], "best_equation": None}

    data = task_input["data"]
    columns = data["columns"]
    rows = np.asarray(data["data"], dtype=float)
    target = task_input["target_column"]
    features = task_input["predictor_columns"]
    y = rows[:, columns.index(target)]
    transform = task_input.get("target_transform")
    if transform == "log":
        y = np.log(y)
    elif transform == "log1p":
        y = np.log1p(y)
    elif transform == "sqrt":
        y = np.sqrt(y)

    def fit(terms: list[tuple[str, np.ndarray]]) -> tuple[str, float]:
        A = np.column_stack([np.ones(len(y))] + [col for _, col in terms])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        parts = [f"{coef[0]:.5g}"] + [
            f"({c:.5g} * {name})" for c, (name, _) in zip(coef[1:], terms, strict=False)
        ]
        loss = float(np.mean((A @ coef - y) ** 2))
        return " + ".join(parts), loss

    cols = {f: rows[:, columns.index(f)] for f in features}
    candidates = [[(f, cols[f])] for f in features[:1]]
    candidates.append([(f, cols[f]) for f in features])
    positive = [f for f in features if np.all(cols[f] > 0)]
    if positive:
        candidates.append(
            [
                (f"log({f})" if f in positive else f, np.log(cols[f]) if f in positive else cols[f])
                for f in features
            ]
        )
    if len(features) >= 2:
        a, b = features[0], features[1]
        candidates.append([(a, cols[a]), (b, cols[b]), (f"{a} * {b}", cols[a] * cols[b])])

    equations = []
    for terms in candidates:
        eq, loss = fit(terms)
        equations.append(
            {
                "equation": eq,
                "complexity": 1 + 4 * len(terms),
                "loss": loss,
                "score": 0.0,
                "sympy_format": eq,
            }
        )
    best = min(equations, key=lambda e: e["loss"])
    return {
        "status": "success",
        "equations": equations,
        "best_equation": best,
        "iterations_completed": 100,
        "scatter_data": {},
        "target_transform": transform,
        "computation_time_seconds": 3.0,
    }


MOCK_PYSR_PROGRESS_STEPS = [
    (5, "Fetching input", "fetching_input"),
    (10, "Loading data", "pysr_loading"),
    (15, "Computing configuration", "pysr_config"),
    (20, "Creating PySR model", "pysr_model"),
    (30, "Running symbolic regression", "pysr_running"),
    (85, "Extracting equations", "pysr_extracting"),
    (90, "Finalizing", "pysr_finalizing"),
    (95, "Writing output", "writing_output"),
    (100, "Task completed", "completed"),
]


def _run_mock_pysr(job: MockJob, callback_url: str, callback_token: str) -> None:
    """Simulate PySR execution: fetch input, send progress, report least-squares equations."""
    job.state = MockJobState.RUNNING
    job.start_time = int(time.time())
    headers = {"X-Worker-Token": callback_token}
    base_url = callback_url.rstrip("/")

    logger.info(f"Job {job.job_id}: mock PySR ({job.task_key}) started for run {job.run_id}")

    try:
        task_input = None
        try:
            resp = http_requests.get(
                f"{base_url}/input/{job.run_id}",
                params={"task_type": job.task_type, "task_key": job.task_key},
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            task_input = resp.json()["input"]
        except Exception as e:
            logger.warning(f"Job {job.job_id}: input fetch failed: {e}")

        for progress, status, step in MOCK_PYSR_PROGRESS_STEPS:
            if job.state == MockJobState.CANCELLED:
                return

            payload = {
                "progress": progress,
                "status": status,
                "step_name": step,
                "task_type": "pysr",
                "task_key": job.task_key,
            }
            try:
                http_requests.post(
                    f"{base_url}/progress/{job.run_id}",
                    json=payload,
                    headers=headers,
                    timeout=5,
                )
            except Exception as e:
                logger.warning(f"Job {job.job_id}: progress callback failed: {e}")

            # Simulate work between steps
            time.sleep(0.5)

        results = _mock_pysr_results(task_input)
        try:
            http_requests.post(
                f"{base_url}/complete/{job.run_id}",
                json={"results": results, "task_key": job.task_key},
                headers=headers,
                timeout=10,
            )
        except Exception as e:
            logger.warning(f"Job {job.job_id}: complete callback failed: {e}")

        job.state = MockJobState.COMPLETED
        job.exit_code = 0
        job.end_time = int(time.time())
        logger.info(f"Job {job.job_id}: mock PySR completed")

    except Exception as e:
        logger.error(f"Job {job.job_id}: mock PySR failed: {e}")
        job.state = MockJobState.FAILED
        job.exit_code = 1
        job.end_time = int(time.time())


# ---------------------------------------------------------------------------
# Real subprocess launcher & monitor (non-PySR task types)
# ---------------------------------------------------------------------------


def _launch_worker(job: MockJob, callback_url: str, callback_token: str) -> None:
    """Launch ``python -m slurm_worker`` subprocess for real task execution."""
    # Create output directory
    output_dir = os.path.dirname(job.output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Build environment for subprocess
    env = os.environ.copy()
    if callback_url:
        env["CALLBACK_URL"] = callback_url
    if callback_token:
        env["CALLBACK_TOKEN"] = callback_token
    env.setdefault("PYTHONPATH", "/app")

    cmd = [
        sys.executable,
        "-m",
        "slurm_worker",
        "--task-type",
        job.task_type,
        "--task-key",
        job.task_key,
        "--run-id",
        job.run_id,
        "--output",
        job.output_path,
    ]

    logger.info(f"Job {job.job_id}: launching worker task_type={job.task_type} run_id={job.run_id}")
    logger.info(f"Job {job.job_id}: cmd = {' '.join(cmd)}")
    if callback_url:
        logger.info(f"Job {job.job_id}: CALLBACK_URL={callback_url}")

    try:
        job.process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        job.state = MockJobState.RUNNING
        job.start_time = int(time.time())

        # Start monitor daemon
        t = threading.Thread(target=_monitor_job, args=(job,), daemon=True)
        t.start()
    except Exception as e:
        logger.error(f"Job {job.job_id}: failed to launch: {e}")
        job.state = MockJobState.FAILED
        job.end_time = int(time.time())
        job.exit_code = 1


def _monitor_job(job: MockJob) -> None:
    """Wait for process to finish and update job state."""
    assert job.process is not None
    for line in job.process.stdout:
        decoded = line.decode("utf-8", errors="replace").rstrip()
        if decoded:
            logger.info(f"Job {job.job_id} [{job.task_type}]: {decoded}")

    job.process.wait()
    job.exit_code = job.process.returncode
    job.end_time = int(time.time())

    if job.state == MockJobState.CANCELLED:
        logger.info(f"Job {job.job_id}: cancelled")
    elif job.exit_code == 0:
        job.state = MockJobState.COMPLETED
        logger.info(f"Job {job.job_id}: completed successfully")
    else:
        job.state = MockJobState.FAILED
        logger.warning(f"Job {job.job_id}: failed with exit code {job.exit_code}")


# ---------------------------------------------------------------------------
# Job dispatch
# ---------------------------------------------------------------------------


def _dispatch_job(job: MockJob) -> None:
    """Route job to real worker or mock based on task type."""
    callback_url, callback_token = _parse_job_script(job)

    if job.task_type == "pysr":
        _run_mock_pysr(job, callback_url, callback_token)
    else:
        _launch_worker(job, callback_url, callback_token)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def _cleanup():
    """Terminate all running subprocesses on shutdown."""
    for job in store.all_running():
        if job.process and job.process.poll() is None:
            logger.info(f"Cleanup: terminating job {job.job_id}")
            job.process.terminate()


atexit.register(_cleanup)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Mock slurmrestd", version="0.0.41")


def _job_to_slurm_json(job: MockJob) -> dict:
    """Format job as slurmrestd-compatible JSON."""
    return {
        "job_id": job.job_id,
        "job_state": [job.state.value],
        "start_time": job.start_time,
        "end_time": job.end_time,
        "exit_code": {"return_code": job.exit_code},
        "nodes": "localhost",
        "state_reason": "None",
        "name": f"syxplain-{job.task_key}-{job.run_id[:8] if job.run_id else 'unknown'}",
    }


@app.get("/slurm/v0.0.41/ping")
async def ping():
    """Health check endpoint."""
    return {"status": "ok", "mock": True}


@app.post("/slurm/v0.0.41/job/submit")
async def submit_job(request: Request):
    """Submit a job -- parse script and dispatch to real worker or mock."""
    body = await request.json()
    script = body.get("script", "")

    if not script:
        return JSONResponse(
            status_code=400,
            content={"errors": [{"error": "No script provided"}]},
        )

    job = store.create(script)
    logger.info(f"Job {job.job_id}: submitted")

    threading.Thread(target=_dispatch_job, args=(job,), daemon=True).start()

    return {"job_id": job.job_id}


@app.get("/slurm/v0.0.41/job/{job_id}")
async def get_job(job_id: int):
    """Get job status."""
    job = store.get(job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"jobs": [], "errors": [{"error": f"Job {job_id} not found"}]},
        )

    return {"jobs": [_job_to_slurm_json(job)]}


@app.delete("/slurm/v0.0.41/job/{job_id}")
async def cancel_job(job_id: int):
    """Cancel a running job."""
    job = store.get(job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"errors": [{"error": f"Job {job_id} not found"}]},
        )

    if job.process and job.process.poll() is None:
        job.process.terminate()
    job.state = MockJobState.CANCELLED
    job.end_time = int(time.time())
    logger.info(f"Job {job_id}: cancel requested")

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Mock slurmrestd server")
    parser.add_argument("--port", type=int, default=6820, help="Listen port")
    parser.add_argument("--host", default="0.0.0.0", help="Listen host")
    args = parser.parse_args()

    logger.info(f"Starting mock slurmrestd on {args.host}:{args.port}")

    # Filter out noisy health check ping logs from uvicorn access logger
    class _PingFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return "/ping" not in record.getMessage()

    logging.getLogger("uvicorn.access").addFilter(_PingFilter())

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
