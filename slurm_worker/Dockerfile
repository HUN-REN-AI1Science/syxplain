# Syxplain Slurm Worker Docker Image
#
# This image can be used to create a Singularity container for Slurm
# or run the worker directly in containerized environments.
#
# Build: docker build -t syxplain-worker .
# Convert to Singularity: singularity build syxplain-worker.sif docker://syxplain-worker

FROM python:3.11-slim

LABEL maintainer="Syxplain Team"
LABEL description="Syxplain compute worker for SHAP and PySR tasks"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Julia (required for PySR)
ENV JULIA_VERSION=1.10.2
RUN curl -fsSL https://julialang-s3.julialang.org/bin/linux/x64/1.10/julia-${JULIA_VERSION}-linux-x86_64.tar.gz | \
    tar -xz -C /opt && \
    ln -s /opt/julia-${JULIA_VERSION}/bin/julia /usr/local/bin/julia

# Set up Python environment
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-compile Julia packages for PySR
# This takes a while but speeds up first run significantly
RUN python -c "from pysr import PySRRegressor; import numpy as np; \
    model = PySRRegressor(niterations=1, verbosity=0); \
    X = np.random.randn(10, 2); y = np.random.randn(10); \
    model.fit(X, y)" || true

# Copy worker code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 worker && \
    chown -R worker:worker /app
USER worker

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Default command
ENTRYPOINT ["python", "-m", "slurm_worker"]
CMD ["--help"]
