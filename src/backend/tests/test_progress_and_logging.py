"""Progress phase config and access-log token masking."""

import logging

from backend.core.logging import EndpointFilter
from backend.services.progress_service import get_phase, get_progress_phases


def test_phases_start_in_order_and_have_durations():
    phases = get_progress_phases()
    starts = [p["progress_start"] for p in phases]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)
    assert starts[0] == 0 and starts[-1] < 100
    assert all(p["expected_s"] > 0 for p in phases)
    # Each step of the progress page's tracker is a run of consecutive phases
    groups = [p["group"] for p in phases]
    steps = [g for i, g in enumerate(groups) if i == 0 or g != groups[i - 1]]
    assert all(groups) and len(steps) == len(set(steps))
    # The agent phase is the bulk of a run, so it gets the bulk of the bar
    agent, wrapup = get_phase("discovery_agent"), get_phase("discovery_wrapup")
    assert wrapup["progress_start"] - agent["progress_start"] >= 70


def _access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("172.18.0.5:1", "GET", path, "1.1", 200),
        None,
    )


def test_access_log_masks_sse_token():
    record = _access_record("/api/sse/progress/abc?token=eyJhbGciOi.payload.sig&x=1")
    assert EndpointFilter().filter(record)
    message = record.getMessage()
    assert "eyJ" not in message
    assert "/api/sse/progress/abc?token=***&x=1" in message


def test_access_log_leaves_other_paths_alone():
    record = _access_record("/api/run")
    assert EndpointFilter().filter(record)
    assert record.getMessage().endswith('"GET /api/run HTTP/1.1" 200')
