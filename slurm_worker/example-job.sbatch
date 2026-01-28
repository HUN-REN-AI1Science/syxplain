#!/bin/bash
#SBATCH --job-name=syxplain-compute
#SBATCH --partition=batch_cpu_m2.large
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --output=/storage/%u/syxplain/logs/%j.out
#SBATCH --error=/storage/%u/syxplain/logs/%j.err

# Syxplain Worker Slurm Job Script
#
# This is a template job script for running Syxplain compute tasks.
# The backend submits jobs programmatically, but this can be used for testing.
#
# Required environment variables (set by backend or manually for testing):
#   TASK_TYPE    - Task type: "shap" or "pysr"
#   RUN_ID       - Unique run identifier
#   INPUT_PATH   - Path to input JSON file
#   OUTPUT_PATH  - Path for output JSON file
#
# Optional environment variables:
#   CALLBACK_URL   - Backend API URL for progress reporting
#   CALLBACK_TOKEN - Authentication token for callbacks
#   CONTAINER_PATH - Path to Singularity container (default: see below)

# Default container location
CONTAINER_PATH="${CONTAINER_PATH:-/storage/ai4science_admin/containers/syxplain-worker.sif}"

# Validate required variables
if [ -z "$TASK_TYPE" ] || [ -z "$RUN_ID" ] || [ -z "$INPUT_PATH" ] || [ -z "$OUTPUT_PATH" ]; then
    echo "Error: Missing required environment variables"
    echo "Required: TASK_TYPE, RUN_ID, INPUT_PATH, OUTPUT_PATH"
    exit 1
fi

# Validate container exists
if [ ! -f "$CONTAINER_PATH" ]; then
    echo "Error: Singularity container not found: $CONTAINER_PATH"
    exit 1
fi

# Validate input file exists
if [ ! -f "$INPUT_PATH" ]; then
    echo "Error: Input file not found: $INPUT_PATH"
    exit 1
fi

# Create output directory if needed
OUTPUT_DIR=$(dirname "$OUTPUT_PATH")
mkdir -p "$OUTPUT_DIR"

# Log job info
echo "=== Syxplain Worker Job ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "Task Type: $TASK_TYPE"
echo "Run ID: $RUN_ID"
echo "Input: $INPUT_PATH"
echo "Output: $OUTPUT_PATH"
echo "Container: $CONTAINER_PATH"
echo "Start Time: $(date)"
echo "=========================="

# Run the worker in the Singularity container
# --bind mounts the storage directory so the container can access input/output files
singularity run \
    --bind /storage:/storage \
    --cleanenv \
    --env CALLBACK_URL="$CALLBACK_URL" \
    --env CALLBACK_TOKEN="$CALLBACK_TOKEN" \
    "$CONTAINER_PATH" \
    --task-type "$TASK_TYPE" \
    --run-id "$RUN_ID" \
    --input "$INPUT_PATH" \
    --output "$OUTPUT_PATH"

EXIT_CODE=$?

echo "=========================="
echo "End Time: $(date)"
echo "Exit Code: $EXIT_CODE"

exit $EXIT_CODE
