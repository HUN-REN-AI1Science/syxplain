#!/bin/bash
# Build Singularity container for Syxplain Worker
#
# This script builds the Singularity image from the definition file.
# Run this on a machine with Singularity installed and sudo/fakeroot access.
#
# Usage:
#   ./build-singularity.sh              # Build with default name
#   ./build-singularity.sh my-image.sif # Build with custom name
#
# After building, copy the .sif file to the Slurm cluster's shared storage.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_FILE="${1:-syxplain-worker.sif}"

echo "Building Syxplain Worker Singularity container..."
echo "Output: ${OUTPUT_FILE}"
echo ""

# Check if singularity is available
if ! command -v singularity &> /dev/null; then
    echo "Error: singularity command not found"
    echo "Please install Singularity: https://sylabs.io/guides/latest/user-guide/quick_start.html"
    exit 1
fi

# Check if definition file exists
if [ ! -f "${SCRIPT_DIR}/syxplain-worker.def" ]; then
    echo "Error: syxplain-worker.def not found in ${SCRIPT_DIR}"
    exit 1
fi

# Build the container
cd "${SCRIPT_DIR}"

# Try fakeroot first (no sudo required), fall back to sudo
if singularity build --fakeroot "${OUTPUT_FILE}" syxplain-worker.def 2>/dev/null; then
    echo ""
    echo "Build successful (fakeroot mode)"
else
    echo "Fakeroot not available, trying with sudo..."
    sudo singularity build "${OUTPUT_FILE}" syxplain-worker.def
    echo ""
    echo "Build successful (sudo mode)"
fi

echo ""
echo "Container built: ${OUTPUT_FILE}"
echo "Size: $(du -h "${OUTPUT_FILE}" | cut -f1)"
echo ""
echo "Next steps:"
echo "  1. Copy to Slurm cluster: scp ${OUTPUT_FILE} <user>@slurm.science-cloud.hu:/storage/<user>/containers/"
echo "  2. Test the container: singularity run ${OUTPUT_FILE} --help"
echo "  3. Run a test task: singularity run --bind /storage:/storage ${OUTPUT_FILE} --task-type shap --run-id test --input /path/to/input.json --output /path/to/output.json"
