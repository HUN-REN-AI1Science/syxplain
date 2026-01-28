"""
Entry point for running worker as module: python -m slurm_worker
"""
import sys
from slurm_worker.cli import main

if __name__ == "__main__":
    sys.exit(main())
