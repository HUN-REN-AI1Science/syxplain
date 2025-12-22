"""
PySR output streaming service.

Captures PySR stdout and makes it available for WebSocket streaming.
Uses multiprocessing.Manager for efficient memory-based IPC.
"""
import io
import re
import sys
import threading
from typing import Optional, Callable, Dict, Any

import logging

logger = logging.getLogger(__name__)

# Global registry to hold shared dictionaries (proxies) for active runs
# This typically exists only in the main process
# run_id -> dict_proxy
_active_streams: Dict[str, Any] = {}


def register_stream(run_id: str, stream_proxy: Any) -> None:
    """Register a shared dictionary for a run."""
    logger.info(f"Registering stream for run {run_id}")
    _active_streams[run_id] = stream_proxy


def unregister_stream(run_id: str) -> None:
    """Remove a shared dictionary from registry."""
    if run_id in _active_streams:
        logger.info(f"Unregistering stream for run {run_id}")
        del _active_streams[run_id]


def read_stream(run_id: str) -> Optional[str]:
    """Read content from the shared dictionary."""
    if run_id in _active_streams:
        try:
            content = _active_streams[run_id].get('content', '')
            # logger.debug(f"Reading stream for {run_id}: {len(content)} chars")
            return content
        except Exception as e:
            # Handle potential proxy errors (e.g., process died)
            logger.debug(f"Error reading stream for {run_id}: {e}")
            return None
    else:
        # logger.debug(f"Stream not found for {run_id}")
        pass
    return None


class PySROutputCapture:
    """
    Captures PySR stdout and writes to a shared dictionary.

    Usage:
        with PySROutputCapture(stream_dict) as capture:
            pysr.fit(X, y)
    """

    def __init__(self, stream_proxy: Any):
        self.stream_proxy = stream_proxy
        self.original_stdout = None
        self.capture_buffer = io.StringIO()
        self.running = False

    def __enter__(self):
        """Start capturing stdout."""
        self.original_stdout = sys.stdout
        self.running = True
        sys.stdout = TeeWriter(
            self.original_stdout,
            self._on_write
        )
        logger.info("Started stdout capture for PySR")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop capturing and restore stdout."""
        self.running = False
        sys.stdout = self.original_stdout
        logger.info("Stopped stdout capture for PySR")
        return False

    def _on_write(self, text: str):
        """Called when text is written to stdout."""
        self.capture_buffer.write(text)

        # Parse and extract Hall of Fame content
        full_output = self.capture_buffer.getvalue()
        equations = self._extract_equations(full_output)

        if equations:
            try:
                self.stream_proxy['content'] = equations
                logger.debug(f"Updated stream content: {len(equations)} chars")
            except Exception as e:
                logger.error(f"Failed to update stream proxy: {e}")
        else:
            logger.debug("No equations extracted from current buffer")
            pass

    def _extract_equations(self, output: str) -> str:
        """Extract the Hall of Fame table from PySR output."""
        # Strip ANSI color codes
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_output = ansi_escape.sub('', output)

        lines = clean_output.split('\n')

        # Find lines with equation table format
        equation_lines = []
        in_hall_of_fame = False

        for line in lines:
            stripped = line.strip()

            # Detect Hall of Fame header
            if 'Hall of Fame' in line or ('Complexity' in line and 'Loss' in line and 'Equation' in line):
                in_hall_of_fame = True
                equation_lines = [line]
                continue

            if in_hall_of_fame:
                if not stripped:
                    # Empty line might indicate end of table, but keep checking
                    continue

                # Skip progress bars and info logs
                if 'Evolving' in line or 'ETA:' in line or stripped.startswith('Info:'):
                    continue

                # Keep lines that look like table rows (digits, borders, equations)
                # Matches: "1   1.23e-1   x0 + x1" or borders "─────"
                if (re.match(r'^\d+\s+', stripped) or
                    'y =' in stripped or
                    '───' in stripped or
                    '════' in stripped or
                    'Complexity' in stripped):
                    equation_lines.append(line)

        if equation_lines:
            logger.debug(f"Extracted {len(equation_lines)} lines of equations")
            # Return valid table lines
            return '\n'.join(equation_lines[-20:])

        return ""


class TeeWriter:
    """
    Writes to multiple destinations simultaneously.
    """

    def __init__(self, original: io.TextIOBase, callback: Callable[[str], None]):
        self.original = original
        self.callback = callback

    def write(self, text: str):
        self.original.write(text)
        try:
            self.callback(text)
        except Exception:
            pass

    def flush(self):
        self.original.flush()

    def __getattr__(self, name):
        return getattr(self.original, name)
