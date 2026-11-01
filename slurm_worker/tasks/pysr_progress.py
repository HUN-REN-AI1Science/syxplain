"""
Live PySR search progress, read from PySR's own iteration bar.

Julia writes the bar ("Evolving for 800 iterations...  37%|...") to file descriptor 2, which
Python cannot hook. From before Julia starts, fd 2 is routed through a pipe: a thread copies
everything through to the original stderr unchanged and reports the bar's percentage.
"""

from __future__ import annotations

import logging
import math
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
                logger.warning("Search progress report failed", exc_info=True)


class BarProgress:
    """
    Handle of an active capture. Once ``enable()`` is called (the fit starts), the bar first
    creeps through ``start..bar_start`` on elapsed time while Julia compiles (~1-1.5 min,
    no output to follow), then follows PySR's own percentage over ``bar_start..end``.
    """

    def __init__(
        self,
        report: Callable[[int], None],
        start: int,
        end: int,
        bar_start: int | None = None,
        compile_expected_s: float = 75.0,
    ):
        self._report = report
        self._start, self._end = start, end
        self._bar_start = start if bar_start is None else bar_start
        self._compile_expected_s = compile_expected_s
        self._last_value, self._last_at = start, 0.0
        self._lock = threading.Lock()
        self.enabled = False
        self._seen = False

    def _emit(self, value: int, force: bool = False) -> None:
        with self._lock:
            now = time.monotonic()
            if value > self._last_value and (force or now - self._last_at >= _MIN_INTERVAL_S):
                self._last_value, self._last_at = value, now
                self._report(value)

    def enable(self) -> None:
        """The fit starts: report compile-time progress until PySR's bar appears."""
        self.enabled = True
        if self._bar_start <= self._start:
            return
        started = time.monotonic()

        def tick() -> None:
            while self.enabled and not self._seen:
                frac = 1 - math.exp(-2 * (time.monotonic() - started) / self._compile_expected_s)
                # Stop short of bar_start: only the bar itself may reach it
                self._emit(self._start + int(frac * (self._bar_start - 1 - self._start)))
                time.sleep(_MIN_INTERVAL_S)

        threading.Thread(target=tick, daemon=True).start()

    def disable(self) -> None:
        self.enabled = False

    def on_percent(self, pct: int) -> None:
        if not self._seen:
            self._seen = True
            logger.info(f"Search progress: PySR bar found ({pct}%), enabled={self.enabled}")
        if not self.enabled:
            return
        self._emit(self._bar_start + round(pct / 100 * (self._end - self._bar_start)))


@contextmanager
def pysr_bar_progress(
    report: Callable[[int], None], start: int, end: int, bar_start: int | None = None
) -> Iterator[BarProgress]:
    """
    Capture fd 2 for the block; while the handle is ``enabled``, report the search's progress
    mapped onto ``start..end`` (at most every few seconds, only when it grows).

    Enter it before PySR is imported: Julia binds its stderr when it starts, so a redirect
    made later never sees the bar. Julia keeps writing to the pipe after the block, so the
    copying thread outlives it. If fd 2 cannot be redirected, the block runs without progress.
    """
    bar = BarProgress(report, start, end, bar_start)
    try:
        saved = os.dup(2)
        read_fd, write_fd = os.pipe()
    except OSError:
        logger.warning("Could not capture stderr; no live search progress")
        yield bar
        return

    os.dup2(write_fd, 2)
    os.close(write_fd)
    thread = threading.Thread(target=_pump, args=(read_fd, saved, bar.on_percent), daemon=True)
    thread.start()
    try:
        yield bar
    finally:
        bar.disable()
        os.dup2(saved, 2)
