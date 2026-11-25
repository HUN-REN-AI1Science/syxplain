"""Infrastructure around discovery: profiling process, SSE replay buffer, worker handshake."""

import asyncio
import time

import numpy as np
import pandas as pd

from backend.api.sse.connection_manager import (
    MAX_RECENT_EVENTS,
    MAX_REPLAY_RUNS,
    get_connection_manager,
)
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


def test_search_progress_is_state_not_history():
    manager = get_connection_manager()

    async def scenario():
        await manager.broadcast_event("run-p", {"kind": "fit", "text": "C1", "model_id": "C1"})
        for pct in (10, 50, 90):
            for sid in ("pysr_1", "pysr_2"):
                await manager.broadcast_search_progress("run-p", sid, pct)
        return manager.recent_events("run-p"), manager.search_progress("run-p")

    events, progress = asyncio.run(scenario())
    assert [m["event"]["kind"] for m in events] == ["fit"]  # pings never enter the replay log
    assert progress == {"pysr_1": 90, "pysr_2": 90}


def test_replay_never_evicts_fits_or_searches():
    manager = get_connection_manager()

    async def scenario():
        await manager.broadcast_event("run-long", {"kind": "fit", "model_id": "C1"})
        await manager.broadcast_event("run-long", {"kind": "search_started", "search_id": "s1"})
        for i in range(MAX_RECENT_EVENTS + 20):
            await manager.broadcast_event("run-long", {"kind": "thought", "text": str(i)})
        return [m["event"] for m in manager.recent_events("run-long")]

    events = asyncio.run(scenario())
    assert len(events) == MAX_RECENT_EVENTS
    assert events[0]["kind"] == "fit" and events[1]["kind"] == "search_started"
    assert events[-1]["text"] == str(MAX_RECENT_EVENTS + 19)  # the oldest narration made room


def _fake_db(monkeypatch, run):
    from contextlib import contextmanager

    from backend.api.routers import progress as router

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
    return router


def test_search_progress_after_the_run_ended_is_dropped(monkeypatch):
    class FakeRun:
        status = "completed"
        progress = 100

    router = _fake_db(monkeypatch, FakeRun())
    update = router.WorkerProgressUpdate(progress=40, task_key="pysr_1")
    asyncio.run(router.receive_progress("run-late", update, x_worker_token="t"))
    assert get_connection_manager().search_progress("run-late") == {}


def test_worker_reports_version_on_input_fetch(monkeypatch):
    class FakeRun:
        input_data = {"pysr_1": {"data": "x"}}

    run = FakeRun()
    router = _fake_db(monkeypatch, run)
    out = asyncio.run(
        router.get_job_input(
            "run-1", task_type="pysr", task_key="pysr_1", worker_version="3.0.0", x_worker_token="t"
        )
    )
    assert out == {"input": {"data": "x"}}
    assert run.input_data["pysr_1"] == {"fetched": True, "worker_version": "3.0.0"}
