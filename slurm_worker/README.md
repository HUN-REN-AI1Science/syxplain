# Syxplain Slurm Worker

Standalone worker for executing PySR symbolic-regression searches on Slurm clusters. Each search of a run has its own task key (`--task-key pysr_2`), under which the backend stores its input and results.

> **Note:** For overall Slurm integration setup (environment variables, SSH tunnels, token management), see [SLURM.md](../SLURM.md).

## Table of Contents

- [Quick Start](#quick-start)
- [Local Testing](#local-testing)
- [Singularity Container](#singularity-container)
- [Task Types](#task-types)
- [Adding New Tasks](#adding-new-tasks)
- [Progress Callbacks](#progress-callbacks)
- [Troubleshooting](#troubleshooting)

## Quick Start

### 1. Deploy Worker Code to Cluster

Copy the worker code to the cluster's shared storage:

```bash
scp -r slurm_worker ai4science@slurm.science-cloud.hu:/storage/ai4science/syxplain/
```

### 2. Build the Singularity Container on Cluster

SSH to the cluster and build (no local Singularity installation needed):

```bash
# SSH to the cluster
ssh ai4science@slurm.science-cloud.hu

# Create containers directory
mkdir -p /storage/ai4science/syxplain/containers

# Build the container
cd /storage/ai4science/syxplain/slurm_worker
singularity build --fakeroot ../containers/syxplain-worker.sif syxplain-worker.def
```

This creates `syxplain-worker.sif` with all dependencies pre-installed and Julia pre-compiled.

### 3. Test the Container

On the cluster, verify it works:

```bash
# Test PySR import
singularity exec ../containers/syxplain-worker.sif python -c "import pysr; print('PySR', pysr.__version__)"

# Test CLI help
singularity run ../containers/syxplain-worker.sif --help
```

Expected output:
```
PySR 2.7.0
usage: __main__.py [-h] --task-type {pysr} [--task-key TASK_KEY] ...
```

### 4. Update/Refresh the Container

When you make changes to the worker code:

```bash
# From your local machine - copy updated code
scp -r slurm_worker ai4science@slurm.science-cloud.hu:/storage/ai4science/syxplain/

# SSH and rebuild with --force to overwrite
ssh ai4science@slurm.science-cloud.hu
cd /storage/ai4science/syxplain/slurm_worker
singularity build --fakeroot --force ../containers/syxplain-worker.sif syxplain-worker.def
```

## Local Testing

Test tasks locally without Slurm using the example data:

```bash
# Install dependencies (if not using container)
pip install -r slurm_worker/requirements.txt

# Screen classic laws (Mitscherlich, Langmuir, power law, ...) on the soil example
python test_worker_local.py --task classic --example 1

# Run PySR with limited iterations (faster)
python test_worker_local.py --task pysr --example 1 --niterations 5 --output results.json

# PySR on log(target), seeded with a guess
python test_worker_local.py --task pysr --example 3 --target-transform log --guesses "Synapses + Degree"
```

Available examples:
- `--example 1`: Soil phosphate prediction (119 rows, 5 features)
- `--example 2`: Perovskite solar cell (33 rows, auto-detected features)
- `--example 3`: C. elegans connectome (299 rows, 2 features)

Use custom data:
```bash
python test_worker_local.py --task classic \
    --data path/to/data.csv \
    --target my_target \
    --predictors "col1,col2,col3"
```

## Singularity Container

The Singularity container is the recommended deployment method. It includes:

- Python 3.11 with scientific computing stack
- Julia 1.11 with PySR 2.7.0 (pinned) packages pre-compiled
- The worker code ready to execute

Build instructions are in the [Quick Start](#quick-start) section above.

### Container Storage

The container is deployed to a location accessible by all compute nodes:

```bash
# Container location on slurm.science-cloud.hu
/storage/ai4science/syxplain/containers/syxplain-worker.sif

# Worker source code location
/storage/ai4science/syxplain/slurm_worker/
```

### Running the Container

```bash
# Basic usage
singularity run syxplain-worker.sif --help

# With storage bind mount
singularity run --bind /storage:/storage syxplain-worker.sif \
    --task-type pysr \
    --task-key pysr_1 \
    --run-id abc123 \
    --input /storage/user/staging/abc123/input.json \
    --output /storage/user/staging/abc123/output.json

# With progress callbacks
singularity run --bind /storage:/storage \
    --env CALLBACK_URL="https://syxplain.example.com/api/internal" \
    --env CALLBACK_TOKEN="secret-token" \
    syxplain-worker.sif \
    --task-type pysr \
    --run-id abc123 \
    --input /storage/user/staging/abc123/input.json \
    --output /storage/user/staging/abc123/output.json
```

## Task Types

### PySR (`--task-type pysr`)

Performs symbolic regression to discover equations.

**Input JSON:**
```json
{
  "data": {
    "columns": ["x1", "x2", "y"],
    "index": [0, 1, 2],
    "data": [[1.0, 2.0, 3.0], ...]
  },
  "target_column": "y",
  "predictor_columns": ["x1", "x2"],
  "config": {
    "niterations": 40,
    "populations": 15,
    "binary_operators": ["+", "-", "*", "/"],
    "unary_operators": ["exp", "log", "sqrt"],
    "maxsize": 20
  },
  "target_transform": null,
  "guesses": ["x1 + 2*x2"],
  "return_full_front": true
}
```

- `target_transform` (`log`, `log1p`, `sqrt` or null): PySR searches `f(X) ~ transform(y)`; the backend applies the inverse when it scores the equations.
- `guesses`: seed formulas (PySR's warm start). If a guess cannot be parsed, the search reruns without them.
- `return_full_front`: return the whole hall of fame without scatter data (the backend re-scores every equation itself).

**Output JSON:**
```json
{
  "status": "success",
  "equations": [
    {"equation": "x1 + x2", "complexity": 3, "loss": 0.01, "score": 0.95}
  ],
  "best_equation": {...},
  "iterations_completed": 40,
  "computation_time_seconds": 1234.5
}
```

## Adding New Tasks

To add a new task type, create a new file in `tasks/`:

```python
# slurm_worker/tasks/my_task.py
from slurm_worker.tasks.base import Task, TaskResult
from slurm_worker.tasks.registry import TaskRegistry

@TaskRegistry.register("my_task")
class MyTask(Task):
    name = "my_task"

    def _validate_input(self, input_data):
        # Validate input data
        if "required_field" not in input_data:
            raise ValueError("Missing required_field")

    def _execute(self, input_data):
        self._report(10, "Starting", "my_task_start")

        # Do computation...
        result = {"answer": 42}

        self._report(90, "Finalizing", "my_task_done")
        return TaskResult.success(**result)
```

Then import it in `tasks/__init__.py`:
```python
from slurm_worker.tasks import my_task  # noqa: F401
```

After adding new tasks, rebuild the Singularity container.

## Progress Callbacks

If `CALLBACK_URL` and `CALLBACK_TOKEN` are configured, the worker will:

- POST progress updates to `{CALLBACK_URL}/progress/{run_id}`
- POST errors to `{CALLBACK_URL}/error/{run_id}`
- POST completion to `{CALLBACK_URL}/complete/{run_id}`

All requests include the `X-Worker-Token` header for authentication.

## Troubleshooting

### Container Build Fails

**Fakeroot not available:**
```bash
# Use sudo instead
sudo singularity build syxplain-worker.sif syxplain-worker.def
```

**Out of disk space:**
```bash
# Build in a directory with more space
export SINGULARITY_TMPDIR=/path/to/large/tmp
singularity build --fakeroot syxplain-worker.sif syxplain-worker.def
```

### Julia Compilation Slow

The container pre-compiles Julia, but if you're not using the container:
```bash
python -c "from pysr import PySRRegressor; PySRRegressor(niterations=1).fit([[1,2],[3,4]], [1,2])"
```

### Container Can't Access Files

Ensure the storage path is bind-mounted:
```bash
singularity run --bind /storage:/storage syxplain-worker.sif ...
```

### Memory Issues

Increase job memory allocation:
```bash
#SBATCH --mem=8G
```

Or reduce subsampling in the input config.

### Callback Failures

Workers continue running even if callbacks fail. Results are always written to the output file.

### Testing Container Locally

```bash
# Create test input
cat > /tmp/test-input.json << 'EOF'
{
  "data": {
    "columns": ["x1", "x2", "y"],
    "index": [0, 1, 2, 3, 4],
    "data": [[1, 2, 5], [2, 3, 8], [3, 4, 11], [4, 5, 14], [5, 6, 17]]
  },
  "target_column": "y",
  "predictor_columns": ["x1", "x2"]
}
EOF

# Run PySR task
singularity run --bind /tmp:/tmp syxplain-worker.sif \
    --task-type pysr \
    --run-id test \
    --input /tmp/test-input.json \
    --output /tmp/test-output.json

# Check output
cat /tmp/test-output.json
```
