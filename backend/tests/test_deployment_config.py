"""Site-independent deployment settings: Slurm job scripts and the server-keys role."""

import pytest

from backend.core import config
from backend.core.security import User
from backend.infrastructure.slurm.backend import SlurmBackend
from backend.infrastructure.slurm.models import SlurmJobSubmission, TaskInput


@pytest.fixture
def env(monkeypatch):
    """Set environment variables and rebuild the cached settings."""

    def _set(**values):
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        config.clear_settings_cache()

    yield _set
    config.clear_settings_cache()


def _container_script(env, **values) -> str:
    env(SLURM_CONTAINER_PATH="/shared/worker.sif", **values)
    task = TaskInput(task_type="pysr", run_id="run1", input_data={})
    return SlurmBackend()._generate_worker_script(
        task, "/shared/out.json", "/shared/o.log", "/shared/e.log", "/shared/logs"
    )


def test_container_binds_and_julia_depot_default_to_staging_dir(env, monkeypatch):
    monkeypatch.delenv("SLURM_CONTAINER_BINDS", raising=False)
    monkeypatch.delenv("SLURM_JULIA_DEPOT", raising=False)
    script = _container_script(env, SLURM_STAGING_DIR="/shared/syxplain")
    assert "--bind /shared/syxplain " in script
    assert "--env JULIA_DEPOT_PATH=/shared/syxplain/.julia:/opt/julia-depot" in script


def test_container_binds_and_julia_depot_are_configurable(env):
    script = _container_script(
        env,
        SLURM_STAGING_DIR="/shared/syxplain",
        SLURM_CONTAINER_BINDS="/storage, /scratch:/scratch",
        SLURM_JULIA_DEPOT="/scratch/julia",
    )
    assert "--bind /storage " in script
    assert "--bind /scratch:/scratch " in script
    assert "--bind /shared/syxplain " not in script
    assert "JULIA_DEPOT_PATH=/scratch/julia:/opt/julia-depot" in script


def test_empty_partition_is_left_to_the_cluster():
    request = SlurmJobSubmission(script="#!/bin/bash", name="job", partition="")
    assert "partition" not in request.to_slurm_request()["job"]

    request = SlurmJobSubmission(script="#!/bin/bash", name="job", partition="cpu")
    assert request.to_slurm_request()["job"]["partition"] == "cpu"


def test_server_keys_role_is_configurable(env):
    env(SERVER_KEYS_ROLE="lab-member")
    assert User("u", "u@example.org", ["lab-member"]).has_server_keys_access
    assert not User("u", "u@example.org", ["server-llm-access"]).has_server_keys_access
    assert User("u", "u@example.org", ["syxplain-admin"]).has_server_keys_access
    assert not User("u", "u@example.org", []).has_server_keys_access


def test_server_keys_role_default(env, monkeypatch):
    monkeypatch.delenv("SERVER_KEYS_ROLE", raising=False)
    env()
    assert User("u", "u@example.org", ["server-llm-access"]).has_server_keys_access
