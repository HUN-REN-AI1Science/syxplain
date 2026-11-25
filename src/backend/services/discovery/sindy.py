"""
SINDy: sparse identification of the rate law d(target)/dt = f(state, inputs).

The library is built from named terms in the expression grammar (``y``, ``y^2``,
``y*T``, ``exp(T)``), so every equation comes back as a formula the session can
parse and re-score without translating pysindy's notation. Sequentially thresholded
least squares (pysindy's STLSQ) is swept over thresholds; each threshold gives one
sparsity level, and together they form a front from the simplest law to the fullest.

SINDy takes seconds, so it runs in the backend (``LocalSindyLauncher``) behind the
same launcher protocol as the PySR searches on Slurm.
"""

import asyncio
import itertools
import logging
from collections.abc import Callable
from typing import Any

import numpy as np

from backend.services.discovery.expression import parse_expression

logger = logging.getLogger(__name__)

MAX_TERMS = 120
N_THRESHOLDS = 10


def library(
    X: dict[str, np.ndarray],
    variables: list[str],
    degree: int,
    extra_functions: list[str],
) -> tuple[list[str], np.ndarray]:
    """Named candidate terms and their values (columns of the library matrix)."""
    names = ["1"]
    for d in range(1, degree + 1):
        for combo in itertools.combinations_with_replacement(variables, d):
            counts = {v: combo.count(v) for v in dict.fromkeys(combo)}
            names.append("*".join(v if c == 1 else f"{v}^{c}" for v, c in counts.items()))
    for v in variables:
        x = X[v]
        if "exp" in extra_functions and np.max(np.abs(x)) < 50:
            names.append(f"exp({v})")
        if "log" in extra_functions and np.all(x > 0):
            names.append(f"log({v})")
        if "inv" in extra_functions and np.all(np.abs(x) > 1e-12):
            names.append(f"1/{v}")
    names = names[:MAX_TERMS]
    columns = []
    kept = []
    for name in names:
        values = parse_expression(name, variables, parameters=()).evaluate(X, {})
        if np.all(np.isfinite(values)):
            kept.append(name)
            columns.append(values)
    return kept, np.column_stack(columns)


def _format(coef: np.ndarray, names: list[str]) -> str:
    parts = []
    for c, name in zip(coef, names, strict=True):
        if c == 0:
            continue
        value = f"{abs(c):.6g}"
        term = value if name == "1" else f"{value}*{name}"
        parts.append(("- " if c < 0 else "+ ") + term)
    if not parts:
        return "0"
    text = " ".join(parts)
    return text[2:] if text.startswith("+ ") else "-" + text[2:]


def run_sindy(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Fit the sparsity front. Input: ``X`` (alias -> values), ``dydt``, ``variables``,
    ``degree``, ``extra_functions``. Returns ``{"equations": [{equation, complexity,
    loss}]}`` like a PySR hall of fame.
    """
    import pysindy as ps

    X = {k: np.asarray(v, dtype=float) for k, v in input_data["X"].items()}
    y = np.asarray(input_data["dydt"], dtype=float)
    variables = list(input_data["variables"])
    names, theta = library(
        X, variables, int(input_data.get("degree", 2)), list(input_data.get("extra_functions", []))
    )
    norms = np.linalg.norm(theta, axis=0)
    norms[norms == 0] = 1.0
    theta_n = theta / norms
    full, *_ = np.linalg.lstsq(theta_n, y, rcond=None)
    top = float(np.max(np.abs(full))) or 1.0
    thresholds = top * np.logspace(-4, -0.3, N_THRESHOLDS)

    alpha = 1e-6 * theta_n.shape[1]  # columns are unit-norm: sum of squares = column count
    equations, seen = [], set()
    for threshold in thresholds:
        opt = ps.STLSQ(threshold=float(threshold), alpha=alpha, max_iter=50)
        try:
            opt.fit(theta_n, y.reshape(-1, 1))
        except Exception as e:
            logger.debug(f"STLSQ failed at threshold {threshold:.3g}: {e}")
            continue
        coef = np.asarray(opt.coef_).ravel() / norms
        support = tuple(np.flatnonzero(coef))
        if not support or support in seen:
            continue
        seen.add(support)
        resid = y - theta @ coef
        equations.append(
            {
                "equation": _format(coef, names),
                "complexity": len(support),  # number of terms
                "loss": float(np.mean(resid**2)),
            }
        )
    return {"equations": equations}


class LocalSindyLauncher:
    """Runs SINDy searches in a worker thread behind the ``SearchLauncher`` protocol."""

    def __init__(self) -> None:
        self._jobs: dict[str, asyncio.Future] = {}

    async def submit(
        self, search_id: str, input_data: dict[str, Any], on_job_id: Callable[[str], None]
    ) -> str:
        job_id = f"local-{search_id}"
        on_job_id(job_id)
        self._jobs[job_id] = asyncio.ensure_future(asyncio.to_thread(run_sindy, input_data))
        return job_id

    async def wait(self, job_id: str) -> tuple[bool, dict[str, Any] | None, str | None]:
        job = self._jobs.get(job_id)
        if job is None:
            return False, None, f"unknown job {job_id}"
        try:
            result = await job
            self._jobs.pop(job_id, None)  # finished: nothing left to cancel
            return True, result, None
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"SINDy job {job_id} failed: {e}", exc_info=True)
            return False, None, f"{type(e).__name__}: {e}"

    async def cancel(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is not None and not job.done():
            job.cancel()  # the thread finishes on its own; its result is dropped
