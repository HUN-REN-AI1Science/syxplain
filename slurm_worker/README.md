# Syxplain Slurm worker

`slurm_worker` is the program that runs on the compute nodes. It runs one task per
Slurm job, currently one PySR symbolic-regression search. Each search of a run has its own
task key (`pysr_1`, `pysr_2`, ...), under which the backend stores its input and its
result.

This README is for people working on the worker code. To connect Syxplain to a cluster
(configuration, building and deploying the image, network requirements, troubleshooting)
see [docs/slurm.md](../docs/slurm.md).

Current version: `__version__` in [`__init__.py`](__init__.py) (3.2.0). The `Version`
labels in the `.def` files are not authoritative.

## Contents

- [Package layout](#package-layout)
- [How a task runs](#how-a-task-runs)
- [Command line](#command-line)
- [Environment variables](#environment-variables)
- [Backend endpoints](#backend-endpoints)
- [Task types](#task-types)
- [Adding a task type](#adding-a-task-type)
- [Running locally](#running-locally)
- [Building the image](#building-the-image)

## Package layout

```
slurm_worker/
├── __init__.py              # __version__, TaskRegistry export
├── __main__.py              # entry point for python -m slurm_worker
├── cli.py                   # argument parsing, WorkerRunner (fetch input, run task, report)
├── config.py                # CallbackConfig, PySRConfig, WorkerConfig
├── logging_config.py        # logging to stdout
├── io/file_handler.py       # read --input, write --output (result or error JSON)
├── reporting/reporter.py    # ProgressReporter: HTTP callbacks to the backend
├── tasks/
│   ├── base.py              # Task base class, TaskResult, DataFrameInput
│   ├── registry.py          # TaskRegistry (task type name -> class)
│   ├── pysr_task.py         # the "pysr" task
│   └── pysr_progress.py     # live search progress, read from PySR's progress bar
├── requirements.txt         # dependencies for a non-container (conda) install
├── syxplain-worker.def      # full Singularity/Apptainer image
├── syxplain-worker-code.def # code-only rebuild on top of an existing image
└── example-job.sbatch       # manual test job (local input file, no backend)
```

## How a task runs

The backend never sends files to the cluster. It stores the task input in its database,
submits a job whose script exports `CALLBACK_URL` and `CALLBACK_TOKEN`, and runs:

```bash
singularity run [...] syxplain-worker.sif \
    --task-type pysr --task-key pysr_2 --run-id <run-uuid> --output /tmp/syxplain_<uuid>/output.json
```

(or `python -m slurm_worker` with the same arguments in a conda environment). The worker
then:

1. reports progress 1% ("Fetching input");
2. fetches its input with `GET {CALLBACK_URL}/input/{run_id}`, or reads `--input` if given;
3. creates the task from `TaskRegistry` and runs it, which validates the input, executes,
   and reports progress along the way;
4. writes the result JSON to `--output`, reports 100% and posts the result to
   `{CALLBACK_URL}/complete/{run_id}`;
5. on any exception, posts the error and traceback to `{CALLBACK_URL}/error/{run_id}`,
   writes an error JSON to `--output` and exits with code 1.

The backend reads the result from the completion callback, not from the output file. In
backend-submitted jobs the output file is in the node's `/tmp` and is only useful for
debugging on the node.

## Command line

```
python -m slurm_worker --task-type {pysr} --output PATH [options]
```

| Argument | Required | Description |
|---|---|---|
| `--task-type` | yes | Registered task type (`pysr`). |
| `--output` | yes | Path of the output JSON. Parent directories are created. |
| `--task-key` | no | Key of the task within the run, for example `pysr_2`. Default: the task type. |
| `--run-id` | no | Run ID used in callback URLs. Default: `$SLURM_JOB_ID`, else `local`. |
| `--input` | no | Read the input from this JSON file instead of fetching it from the backend. |
| `--callback-url` | no | Overrides `CALLBACK_URL`. |
| `--callback-token` | no | Overrides `CALLBACK_TOKEN`. |
| `--verbose`, `-v` | no | Accepted; currently has no effect. |

The worker needs an input source: either `--input`, or both a callback URL and a token.
Without either it fails with `No input source: provide --input file or configure
callback URL`. With `--input` and no callback configuration, it runs without reporting
(useful for testing) and logs a warning.

## Environment variables

Variables the worker reads:

| Variable | Read by | Purpose |
|---|---|---|
| `CALLBACK_URL` | `config.py` | Base URL of the backend's worker API, ending in `/api/internal`. Set by the job script from the backend's `WORKER_CALLBACK_URL`. |
| `CALLBACK_TOKEN` | `config.py` | Sent as the `X-Worker-Token` header. Set from `WORKER_CALLBACK_TOKEN`. |
| `SLURM_JOB_ID` | `config.py`, `pysr_task.py` | Fallback run ID. |
| `SLURM_CPUS_PER_TASK` | `pysr_task.py` | Number of PySR worker processes and Julia threads. Falls back to `os.cpu_count()`. |

Julia-related variables set by the image (`%environment` in `syxplain-worker.def`) or by
the job script:

| Variable | Value | Purpose |
|---|---|---|
| `JULIA_DEPOT_PATH` | `<SLURM_JULIA_DEPOT>:/opt/julia-depot` (set by the job script) | Writable depot on shared storage, stacked on the image's read-only precompiled depot. |
| `PYTHON_JULIACALL_EXE`, `PYTHON_JULIACALL_PROJECT` | `/opt/julia-1.11.5/bin/julia`, `/opt/julia-env` | Make juliacall load the Julia environment baked into the image, without resolving or downloading anything. |
| `PYTHON_JULIAPKG_EXE` | Julia binary in the image | Keeps juliapkg from downloading its own Julia. |
| `JULIA_CPU_TARGET` | broad x86_64 target | Matches the build-time precompilation, so the native code runs on different node CPUs. |

The backend-side settings (`SLURM_*`, `WORKER_CALLBACK_*`) are listed in
[docs/slurm.md](../docs/slurm.md#configuration-reference).

## Backend endpoints

All under `CALLBACK_URL` (the backend's `/api/internal` router, `backend/api/routers/progress.py`).
Every request carries `X-Worker-Token: <CALLBACK_TOKEN>`; the backend answers `401` if
the token is wrong or not configured.

| Request | Body / query | Notes |
|---|---|---|
| `GET /input/{run_id}` | query: `task_type`, `task_key`, `worker_version` | Returns `{"input": {...}}`. One-time: the backend replaces the stored input with `{"fetched": true, "worker_version": ...}`, and later requests get `410 Gone`. |
| `POST /progress/{run_id}` | `progress` (0-100), `status`, `step_name`, `task_type`, `task_key` | Sent at milestones and, during the search, whenever PySR's progress bar moves (at most every 5 s). |
| `POST /complete/{run_id}` | `results`, `task_key` | The task's result dict. 30 s timeout. |
| `POST /error/{run_id}` | `error`, `details` (with `traceback`), `task_key` | |
| `GET /health` | (no token) | Connectivity check. |

Failed progress, completion and error callbacks are logged as warnings and do not stop
the worker. A lost completion callback still loses the result, because the backend does
not read the output file.

## Task types

### `pysr`

Symbolic regression with [PySR](https://github.com/MilesCranmer/PySR) 2.7.0 (pinned,
because the backend relies on its `guesses` argument and equation string format).

Input:

```json
{
  "data": {
    "columns": ["x1", "x2", "y"],
    "data": [[1.0, 2.0, 5.0], [2.0, 3.0, 8.0]]
  },
  "target_column": "y",
  "predictor_columns": ["x1", "x2"],
  "config": {
    "niterations": 40,
    "populations": 15,
    "population_size": 33,
    "ncycles_per_iteration": 550,
    "binary_operators": ["+", "-", "*", "/"],
    "unary_operators": ["exp", "log", "sqrt", "abs"],
    "maxsize": 20,
    "maxdepth": 10,
    "timeout_in_seconds": 3600,
    "parsimony": 0.0032,
    "turbo": true,
    "template": null,
    "template_expressions": []
  },
  "target_transform": null,
  "guesses": ["x1 + 2*x2"],
  "return_full_front": true
}
```

- `data` is passed to `pandas.DataFrame(**data)`, so the `split` orientation
  (`columns`, `data`, optionally `index`) works.
- `data`, `target_column` and a non-empty `predictor_columns` are required. Every `config`
  field is optional; the values above are the defaults, except `niterations`, which is
  estimated from the data size when omitted.
- `target_transform` (`log`, `log1p`, `sqrt` or null): PySR fits `f(X) ~ transform(y)`.
  The backend applies the inverse when it scores the equations.
- `template` and `template_expressions`: a PySR template such as `"f(a, b) + g(c)"` and the
  names of its subexpressions. Equations then come back as `f = ...; g = ...`, and the
  backend composes them.
- `guesses`: seed formulas (PySR's warm start). If the fit with guesses fails, the search
  reruns without them.
- `return_full_front`: return the whole hall of fame without scatter data (the backend
  re-scores every equation itself).

Output (the `results` of the completion callback, and the content of `--output`):

```json
{
  "status": "success",
  "equations": [
    {"equation": "x1 + 2*x2", "complexity": 5, "loss": 0.01, "score": 0.95, "sympy_format": "x1 + 2*x2"}
  ],
  "best_equation": {"equation": "x1 + 2*x2", "...": "..."},
  "iterations_completed": 40,
  "scatter_data": {},
  "target_transform": null,
  "computation_time_seconds": 312.4
}
```

On failure the output is `{"status": "error", "error": "...", "traceback": "..."}`.

Progress: 1-3% for input and setup, 3-15% while Julia starts and compiles (estimated from
elapsed time), 15-97% following PySR's own iteration bar, then 98-100% for extraction and
completion.

## Adding a task type

1. Create a module in `tasks/`:

   ```python
   # slurm_worker/tasks/my_task.py
   from slurm_worker.tasks.base import Task, TaskResult
   from slurm_worker.tasks.registry import TaskRegistry


   @TaskRegistry.register("my_task")
   class MyTask(Task):
       name = "my_task"

       def _validate_input(self, input_data):
           if "required_field" not in input_data:
               raise ValueError("Missing required_field")

       def _execute(self, input_data):
           self._report(10, "Starting", "my_task_start")
           answer = 42  # the computation
           self._report(90, "Finalizing", "my_task_done")
           return TaskResult.success(answer=answer)
   ```

2. Import it in `tasks/__init__.py` so that it registers:

   ```python
   from slurm_worker.tasks import my_task  # noqa: F401
   ```

3. Submit it from the backend with a `TaskInput(task_type="my_task", ...)`
   (`backend/infrastructure/slurm/models.py`). The task type may contain only letters, digits,
   `_` and `-` (the backend checks this before putting it into the job script).

4. Add any new dependency to `requirements.txt` and to the `pip install` line in
   `syxplain-worker.def`, then rebuild the image (a code-only rebuild is enough if there
   are no new dependencies). The local emulator runs task types other than `pysr` for
   real, so you can try the task with `docker compose up` before building an image.

## Running locally

**Through the full stack.** `docker compose up` starts a local Slurm emulator
(`mock-slurm`, `dev/mock_slurmrestd.py`) that the backend uses by default. It mounts this
directory, so code changes apply to the next job. PySR searches are faked with
least-squares fits unless you start it with `LOCAL_PYSR=true docker compose up --build`,
which builds Julia and PySR into the emulator image and runs this package's real PySR
task (`LOCAL_PYSR_CPUS`, default 2, sets the CPUs per search). Details in
[docs/slurm.md](../docs/slurm.md#local-development-without-a-cluster).

**One task directly.** `dev/run_worker_task.py` (run from the repository root) runs a
task on an example data set, with progress printed to the console and no backend, Slurm
or database:

```bash
# classic-law screen (Mitscherlich, Langmuir, power law, ...) with the backend's fitting
# engine; needs the backend's Python dependencies, not Julia
python dev/run_worker_task.py --task classic --example 1

# the PySR task; needs PySR and Julia (pip install -r slurm_worker/requirements.txt)
python dev/run_worker_task.py --task pysr --example 1 --niterations 5 --output results.json

# PySR on log(target), seeded with a guess
python dev/run_worker_task.py --task pysr --example 3 --target-transform log --guesses "Synapses + Degree"

# your own data
python dev/run_worker_task.py --task classic --data path/to/data.csv \
    --target my_target --predictors "col1,col2,col3"
```

The first PySR run on a machine installs Julia and PySR's Julia packages, which takes
several minutes. Run `python dev/run_worker_task.py --help` for the list of examples and
options.

**The CLI with a local input file.**

```bash
python -m slurm_worker --task-type pysr --input input.json --output output.json
```

Use the input format from [Task types](#task-types); no callbacks are needed.

**The image.** After building it, on any machine with Singularity or Apptainer:

```bash
singularity run --bind "$PWD" syxplain-worker.sif \
    --task-type pysr --run-id test --input "$PWD/input.json" --output "$PWD/output.json"
```

## Building the image

From this directory:

```bash
# full image: Python 3.11, Julia 1.11.5, PySR 2.7.0 precompiled (about 25 minutes)
singularity build --fakeroot syxplain-worker.sif syxplain-worker.def

# code-only: replace /app/slurm_worker in an existing image (seconds)
singularity build --fakeroot --build-arg base=/path/to/syxplain-worker.sif \
    syxplain-worker-<version>.sif syxplain-worker-code.def
```

The full build fails if PySR's Julia packages cannot be installed and precompiled, and
its `%test` fits a small PySR model offline on the finished, read-only image. Check the
version in an image with:

```bash
singularity exec syxplain-worker.sif python -c "import slurm_worker; print(slurm_worker.__version__)"
```

Where to build, build space, deploying the image to a running installation and keeping
backend and worker versions in step are covered in
[docs/slurm.md](../docs/slurm.md#building-the-worker-image).
