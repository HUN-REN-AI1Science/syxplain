# Syxplain Slurm Worker

Standalone worker for executing compute-intensive tasks (SHAP and PySR) on Slurm clusters.

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
# Test SHAP import
singularity exec ../containers/syxplain-worker.sif python -c "import shap; print('SHAP OK')"

# Test CLI help
singularity run ../containers/syxplain-worker.sif --help
```

Expected output:
```
SHAP OK
usage: __main__.py [-h] --task-type {pysr,shap} ...
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

# Run SHAP task on soil data example
python test_worker_local.py --task shap --example 1

# Run PySR with limited iterations (faster)
python test_worker_local.py --task pysr --example 1 --niterations 5

# Run both tasks
python test_worker_local.py --task both --example 1 --output results.json
```

Available examples:
- `--example 1`: Soil phosphate prediction (119 rows, 5 features)
- `--example 2`: Perovskite solar cell (33 rows, auto-detected features)
- `--example 3`: C. elegans connectome (299 rows, 2 features)

Use custom data:
```bash
python test_worker_local.py --task shap \
    --data path/to/data.csv \
    --target my_target \
    --predictors "col1,col2,col3"
```

## Singularity Container

The Singularity container is the recommended deployment method. It includes:

- Python 3.11 with scientific computing stack
- Julia 1.10.2 with PySR packages pre-compiled
- SHAP and all required dependencies
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
    --task-type shap \
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

### SHAP (`--task-type shap`)

Computes feature interactions using SHAP values.

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
  "subsample_fraction": 0.1,
  "subsample_min": 1000,
  "subsample_max": 5000
}
```

**Output JSON:**
```json
{
  "status": "success",
  "interactions": [
    {"feature1": "x1", "feature2": "x2", "interaction_strength": 0.85, "rank": 1}
  ],
  "top_features": ["x1", "x2"],
  "samples_used": 1000,
  "computation_time_seconds": 45.2
}
```

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
  }
}
```

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

# Run SHAP task
singularity run --bind /tmp:/tmp syxplain-worker.sif \
    --task-type shap \
    --run-id test \
    --input /tmp/test-input.json \
    --output /tmp/test-output.json

# Check output
cat /tmp/test-output.json
```
