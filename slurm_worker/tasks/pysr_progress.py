"""
Live PySR search progress, read from PySR's own iteration bar.

Julia writes the bar ("Evolving for 800 iterations...  37%|...") to file descriptor 2, which
Python cannot hook. While the search runs, fd 2 is routed through a pipe: a thread copies
everything through to the original stderr unchanged and reports the bar's percentage.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress

logger = logging.getLogger(__name__)

_BAR = re.compile(rb"Evolving for \d+ iterations\.\.\.\s*(\d{1,3})%")
_MIN_INTERVAL_S = 5.0
_TAIL_BYTES = 512


def _pump(read_fd: int, out_fd: int, on_percent: Callable[[int], None]) -> None:
    """Copy the pipe to the original stderr, passing each new bar percentage on."""
    tail = b""
    while True:
        try:
            chunk = os.read(read_fd, 65536)
        except OSError:
            return
        if not chunk:
            return
        with suppress(OSError):
            os.write(out_fd, chunk)
        # The tail of the previous read catches a bar split across two reads
        buf = tail + chunk
        tail = buf[-_TAIL_BYTES:]
        matches = _BAR.findall(buf)
        if matches:
            try:
                on_percent(min(100, int(matches[-1])))
            except Exception:  # reporting must never stop the copy (a full pipe blocks Julia)
                logger.debug("Progress callback failed", exc_info=True)


@contextmanager
def pysr_bar_progress(report: Callable[[int], None], start: int, end: int) -> Iterator[None]:
    """
    Report the search's progress, mapped onto ``start..end``, while the block runs.

    Reports at most every few seconds and only when the mapped value grows. If fd 2 cannot be
    redirected, the block runs without live progress.
    """
    last = {"value": start, "at": 0.0}

    def on_percent(pct: int) -> None:
        value = start + round(pct / 100 * (end - start))
        now = time.monotonic()
        if value > last["value"] and now - last["at"] >= _MIN_INTERVAL_S:
            last["value"], last["at"] = value, now
            report(value)

    try:
        saved = os.dup(2)
        read_fd, write_fd = os.pipe()
    except OSError:
        logger.warning("Could not capture stderr; no live search progress")
        yield
        return

    os.dup2(write_fd, 2)
    os.close(write_fd)
    # Daemon: Julia worker processes that outlive the fit may keep the pipe open
    thread = threading.Thread(target=_pump, args=(read_fd, saved, on_percent), daemon=True)
    thread.start()
    try:
        yield
    finally:
        os.dup2(saved, 2)
        thread.join(timeout=5)
        if not thread.is_alive():
            os.close(read_fd)
            os.close(saved)
