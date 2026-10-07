"""Infrastructure around discovery: profiling process, SSE replay buffer, worker handshake."""

import asyncio
import time

import numpy as np
import pandas as pd

from backend.api.sse.connection_manager import MAX_REPLAY_RUNS, get_connection_manager
from backend.services.discovery.profiling import compute_profile
from backend.services.discovery.session import DiscoverySession


def test_profiling_does_not_block_the_event_loop():
    rng = np.random.default_rng(0)
    n, p = 3000, 30
    df = pd.DataFrame(rng.uniform(1, 5, (n, p)), columns=[f"x{i}" for i in range(p)])
    df["y"] = np.sqrt(df["x0"]) * 3 + df["x1"] * df["x2"] + rng.normal(0, 0.3, n)
    s = DiscoverySession(df, "y", [f"x{i}" for i in range(p)])

    async def scenario():
        gaps = []

        async def ticker():
            last = time.monotonic()
            while True:
                await asyncio.sleep(0.05)
                now = time.monotonic()
                gaps.append(now - last)
                last = now

        tick = asyncio.create_task(ticker())
        profile = await s.ensure_profile()
        tick.cancel()
        return profile, max(gaps)

    profile, worst_gap = asyncio.run(scenario())
    assert worst_gap < 0.5
    assert profile["has_signal"] is True
    # same numbers as the in-process computation
    X = np.column_stack([s.fit_data.X[f] for f in s.features])
    direct = compute_profile(X, s.fit_data.y, list(s.features), [False] * p, 0)
    assert abs(direct["ceiling_r2"] - profile["noise_ceiling_r2"]) < 1e-3


def test_replay_buffer_is_cleaned_without_clients():
    manager = get_connection_manager()

    async def scenario():
        await manager.broadcast_event("run-x", {"kind": "agent", "text": "hi"})
        assert manager.recent_events("run-x")
        await manager.broadcast_progress(run_id="run-x", progress=100, status="completed")
        assert manager.recent_events("run-x") == []
        for i in range(MAX_REPLAY_RUNS + 50):
            await manager.broadcast_event(f"bulk-{i}", {"kind": "agent", "text": "x"})

    asyncio.run(scenario())
    assert len(manager._recent_events) <= MAX_REPLAY_RUNS


def test_worker_reports_version_on_input_fetch(monkeypatch):
    from contextlib import contextmanager

    from backend.api.routers import progress as router

    class FakeRun:
        input_data = {"pysr_1": {"data": "x"}}

    run = FakeRun()

    class FakeQuery:
        def filter(self, *a):
            return self

        def first(self):
            return run

    class FakeDB:
        def query(self, *a):
            return FakeQuery()

        def commit(self):
            pass

    @contextmanager
    def fake_session():
        yield FakeDB()

    monkeypatch.setattr(router, "get_db_session", fake_session)
    monkeypatch.setattr(router, "_validate_worker_token", lambda t: True)
    out = asyncio.run(
        router.get_job_input(
            "run-1", task_type="pysr", task_key="pysr_1", worker_version="3.0.0", x_worker_token="t"
        )
    )
    assert out == {"input": {"data": "x"}}
    assert run.input_data["pysr_1"] == {"fetched": True, "worker_version": "3.0.0"}
