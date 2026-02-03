# Slurm Integration Guide

This guide explains how Syxplain integrates with a Slurm HPC cluster for compute-intensive tasks (SHAP analysis, PySR symbolic regression).

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [How It Works](#how-it-works)
- [Initial Setup (One-Time)](#initial-setup-one-time)
- [Environment Configuration](#environment-configuration)
- [Token Management](#token-management)
- [Worker Deployment](#worker-deployment)
- [Testing the Integration](#testing-the-integration)
- [Monitoring Jobs](#monitoring-jobs)
- [Troubleshooting](#troubleshooting)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Your Server / Local Machine                        │
│  ┌─────────────┐     ┌─────────────────────────────────────────────────┐    │
│  │   Frontend  │────▶│              Backend API                        │    │
│  │   (React)   │     │                                                 │    │
│  └─────────────┘     │  1. Orchestrates analysis workflow              │    │
│                      │  2. Submits jobs via slurmrestd REST API        │    │
│                      │  3. Uploads input data (JSON over HTTP)         │    │
│                      │  4. Polls job status                            │    │
│                      │  5. Downloads results when complete             │    │
│                      └──────────────────┬──────────────────────────────┘    │
└─────────────────────────────────────────┼───────────────────────────────────┘
                                          │
                                          │ HTTP (port 6820)
                                          │ Direct access from prod server
                                          │ (SSH tunnel needed for local dev)
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Slurm Cluster (slurm.science-cloud.hu)                   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         slurmrestd API                                │   │
│  │                     http://slurm.science-cloud.hu:6820               │   │
│  │                                                                       │   │
│  │  - Receives job submissions                                          │   │
│  │  - Handles file upload/download (base64 over HTTP)                   │   │
│  │  - Reports job status                                                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         Slurm Scheduler                               │   │
│  │                                                                       │   │
│  │  - Queues jobs                                                       │   │
│  │  - Allocates resources                                               │   │
│  │  - Dispatches to compute nodes                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                    ┌───────────────┴───────────────┐                        │
│                    ▼                               ▼                        │
│  ┌─────────────────────────────┐   ┌─────────────────────────────┐         │
│  │      Compute Node 1         │   │      Compute Node N         │         │
│  │                             │   │                             │         │
│  │  ┌───────────────────────┐  │   │  ┌───────────────────────┐  │         │
│  │  │  syxplain_worker      │  │   │  │  syxplain_worker      │  │         │
│  │  │  (Singularity/Conda)  │  │   │  │  (Singularity/Conda)  │  │         │
│  │  │                       │  │   │  │                       │  │         │
│  │  │  - SHAP analysis      │  │   │  │  - PySR regression    │  │         │
│  │  │  - PySR regression    │  │   │  │  - SHAP analysis      │  │         │
│  │  └───────────────────────┘  │   │  └───────────────────────┘  │         │
│  └─────────────────────────────┘   └─────────────────────────────┘         │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      Shared Storage (/storage/)                       │   │
│  │                                                                       │   │
│  │  /storage/<username>/syxplain/           <- Staging directory        │   │
│  │  ├── <job-uuid>/input.json               <- Input data               │   │
│  │  ├── <job-uuid>/output.json              <- Results                  │   │
│  │  └── <job-uuid>/output.json.stdout       <- Job logs                 │   │
│  │                                                                       │   │
│  │  /storage/<username>/containers/         <- Singularity containers   │   │
│  │  └── syxplain-worker.sif                                             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## How It Works

### Job Submission Flow

1. **User initiates analysis** via the web UI
2. **Backend orchestrator** prepares input data and generates PySR configuration using LLM
3. **Backend uploads input JSON** to the staging directory via slurmrestd file API
4. **Backend submits job script** via slurmrestd job submission API
5. **Slurm scheduler** queues the job and allocates resources
6. **Compute node** runs the worker script (inside Singularity container or conda env)
7. **Worker writes results** to output.json in the staging directory
8. **Backend polls** job status via slurmrestd
9. **Backend downloads results** when job completes
10. **Orchestrator generates** LLM explanations and returns final results

### What Gets Transferred Over HTTP

| Data | Direction | Method |
|------|-----------|--------|
| Input JSON (dataset, config) | Backend → Slurm | base64 encoded via `PUT /slurm/v0.0.41/file` |
| Job script (bash) | Backend → Slurm | JSON payload via `POST /slurm/v0.0.41/job/submit` |
| Job status | Slurm → Backend | JSON via `GET /slurm/v0.0.41/job/{id}` |
| Output JSON (results) | Slurm → Backend | base64 encoded via `GET /slurm/v0.0.41/file` |

### What Must Be Pre-Deployed on Slurm

The **worker code** (`slurm_worker/` Python module) must be available on the compute nodes. This is NOT transferred at runtime - it must be deployed beforehand via:

- **Option A: Singularity container** (recommended) - self-contained, reproducible
- **Option B: Conda environment** - requires conda setup on the cluster

## Initial Setup (One-Time)

### 1. Get Cluster Access

Contact your Slurm administrator to obtain:
- SSH access to the login node (`slurm.science-cloud.hu`)
- A Slurm username with job submission permissions
- Access to a partition (e.g., `batch_cpu_m2.large`)
- Storage space under `/storage/<username>/`

### 2. Create Staging Directory

SSH to the cluster and create the staging directory:

```bash
ssh <username>@slurm.science-cloud.hu

# Create staging directory for job files
mkdir -p /storage/<username>/syxplain

# Create directory for Singularity containers
mkdir -p /storage/<username>/containers
```

### 3. Deploy the Worker

See [Worker Deployment](#worker-deployment) section below.

## Environment Configuration

### Production vs Local Development

The Slurm REST API (`slurm.science-cloud.hu:6820`) is accessible directly from the production server. However, for **local development**, you need to set up an SSH tunnel first:

```bash
# Open SSH tunnel (run this in a separate terminal before starting the backend)
ssh ai4science@slurm.science-cloud.hu -L 6820:localhost:6820
```

Keep this tunnel open while developing. After the tunnel is established, you can access the Slurm API via `localhost:6820`.

**Important:** If running the backend inside Docker (via docker-compose), you need two changes:

1. **Bind the SSH tunnel to all interfaces** (not just localhost):
   ```bash
   # Note the 0.0.0.0: prefix - this allows Docker containers to reach the tunnel
   ssh ai4science@slurm.science-cloud.hu -L 0.0.0.0:6820:localhost:6820
   ```

2. **Use `host.docker.internal`** in your `.env` file:
   ```bash
   SLURM_API_URL=http://host.docker.internal:6820
   ```

This works because:
- `0.0.0.0` makes the tunnel listen on all network interfaces, including Docker's bridge network
- `host.docker.internal` resolves to the host machine (configured via `extra_hosts` in docker-compose.yml)

### Environment Variables

Configure these environment variables in your `.env` file:

```bash
# Slurm REST API endpoint
# Production:        http://slurm.science-cloud.hu:6820 (direct access)
# Local dev native:  http://localhost:6820 (via SSH tunnel)
# Local dev Docker:  http://host.docker.internal:6820 (via SSH tunnel on host)
SLURM_API_URL=http://slurm.science-cloud.hu:6820

# JWT token for authentication (see Token Management section)
SLURM_AUTH_TOKEN=<your-jwt-token>

# Your Slurm username
SLURM_USER_NAME=<your-username>

# Partition to submit jobs to
SLURM_PARTITION=batch_cpu_m2.large

# Staging directory on shared storage (must exist and be writable)
SLURM_STAGING_DIR=/storage/<username>/syxplain

# Resource allocation per job
SLURM_CPUS=4              # CPUs per job
SLURM_MEMORY="8G"         # Memory per job
SLURM_TIME_LIMIT="04:00:00"  # Max job time (HH:MM:SS)

# Singularity container path (required for production)
# If set, jobs run inside the container; if empty, falls back to conda
SLURM_CONTAINER_PATH="/storage/<username>/syxplain/containers/syxplain-worker.sif"
```

## Token Management

The Slurm REST API requires JWT authentication. Tokens are generated on the cluster using `scontrol`.

### Generate a Token

```bash
# SSH to the cluster
ssh <username>@slurm.science-cloud.hu

# Generate token (lifespan in seconds)
scontrol token username=<username> lifespan=3600      # 1 hour
scontrol token username=<username> lifespan=86400     # 1 day
scontrol token username=<username> lifespan=604800    # 1 week
scontrol token username=<username> lifespan=31536000  # 1 year
```

### One-Liner (for scripts)

```bash
ssh <username>@slurm.science-cloud.hu "scontrol token username=<username> lifespan=3600"
```

### Token Refresh

Tokens expire after their lifespan. For production:
- Generate a long-lived token (1 year)
- Set up a cron job or reminder to refresh before expiration
- Update `SLURM_AUTH_TOKEN` in your environment when refreshed

## Worker Deployment

The worker code must be deployed to the Slurm cluster. Choose one method:

### Option A: Singularity Container (Recommended)

Singularity containers are self-contained and ensure reproducible environments.

#### Build on the Cluster (Easiest)

Most HPC clusters have Singularity installed. Build directly on the cluster without installing Singularity locally:

```bash
# 1. Copy worker code to the cluster
scp -r slurm_worker ai4science@slurm.science-cloud.hu:/storage/ai4science/syxplain/

# 2. SSH to the cluster
ssh ai4science@slurm.science-cloud.hu

# 3. Create containers directory
mkdir -p /storage/ai4science/syxplain/containers

# 4. Build the container
cd /storage/ai4science/syxplain/slurm_worker
singularity build --fakeroot ../containers/syxplain-worker.sif syxplain-worker.def
```

This creates `syxplain-worker.sif` containing:
- Python 3.11 with scientific computing stack
- Julia 1.10.2 with PySR pre-compiled
- SHAP and all dependencies
- The worker code ready to execute

#### Verify the Container

After building, test that the container works:

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

#### Updating/Refreshing the Container

When you make changes to the worker code, redeploy:

```bash
# 1. Copy updated worker code
scp -r slurm_worker ai4science@slurm.science-cloud.hu:/storage/ai4science/syxplain/

# 2. SSH and rebuild
ssh ai4science@slurm.science-cloud.hu
cd /storage/ai4science/syxplain/slurm_worker
singularity build --fakeroot --force ../containers/syxplain-worker.sif syxplain-worker.def
```

The `--force` flag overwrites the existing container.

#### Configure Backend to Use Container

Set the `SLURM_CONTAINER_PATH` environment variable in your `.env` file:

```bash
SLURM_CONTAINER_PATH="/storage/ai4science/syxplain/containers/syxplain-worker.sif"
```

When this variable is set, the backend automatically generates job scripts that use Singularity:

```bash
singularity run \
    --bind /storage:/storage \
    --cleanenv \
    --env CALLBACK_URL="$CALLBACK_URL" \
    --env CALLBACK_TOKEN="$CALLBACK_TOKEN" \
    /storage/ai4science/syxplain/containers/syxplain-worker.sif \
    --task-type <type> --run-id <id> --input <path> --output <path>
```

If `SLURM_CONTAINER_PATH` is not set (empty string), the backend falls back to using a conda environment for development purposes.

### Option B: Conda Environment

If you prefer conda, set up the environment on the cluster.

#### Create Environment

SSH to the cluster and run:

```bash
# Load conda (cluster-specific)
module load anaconda  # or: source /path/to/conda/etc/profile.d/conda.sh

# Create environment
conda create -n syxplain_worker python=3.11 -y
conda activate syxplain_worker

# Install dependencies
pip install -r /path/to/slurm_worker/requirements.txt

# Install Julia for PySR (first run will be slow)
python -c "from pysr import PySRRegressor; print('Julia ready')"
```

#### Install Worker Code

```bash
# Copy worker code to cluster
scp -r slurm_worker <username>@slurm.science-cloud.hu:/storage/<username>/

# Or install as a package
cd /storage/<username>/slurm_worker
pip install -e .
```

## Testing the Integration

### 1. Test API Connectivity

#### From Production Server

```bash
curl -H "Authorization: Bearer $SLURM_AUTH_TOKEN" \
     -H "Slurm-User-Name: $SLURM_USER_NAME" \
     http://slurm.science-cloud.hu:6820/slurm/v0.0.41/ping
```

#### From Local Development (requires SSH tunnel)

First, open the SSH tunnel in a separate terminal:
```bash
ssh ai4science@slurm.science-cloud.hu -L 6820:localhost:6820
```

Then test connectivity via localhost:
```bash
curl -H "Authorization: Bearer $SLURM_AUTH_TOKEN" \
     -H "Slurm-User-Name: $SLURM_USER_NAME" \
     http://localhost:6820/slurm/v0.0.41/ping
```

Expected response:
```json
{"meta":{"slurm":{"version":{"major":...}}}}
```

### 2. Test File Upload

```bash
# Create test file content (base64 encoded)
CONTENT=$(echo '{"test": "hello"}' | base64)

# Upload via API
curl -X PUT \
     -H "Authorization: Bearer $SLURM_AUTH_TOKEN" \
     -H "Slurm-User-Name: $SLURM_USER_NAME" \
     -H "Content-Type: application/json" \
     -d "{\"path\": \"/storage/$SLURM_USER_NAME/syxplain/test.json\", \"data\": \"$CONTENT\", \"encoding\": \"base64\"}" \
     http://slurm.science-cloud.hu:6820/slurm/v0.0.41/file
```

### 3. Test Job Submission

SSH to the cluster and submit a test job:

```bash
# Simple test job
sbatch <<EOF
#!/bin/bash
#SBATCH --job-name=test
#SBATCH --partition=batch_cpu_m2.large
#SBATCH --time=00:01:00

echo "Hello from Slurm!"
hostname
EOF

# Check job status
squeue -u $USER
```

### 4. Test Worker Locally

Before deploying, test the worker locally:

```bash
cd slurm_worker
pip install -r requirements.txt

# Run SHAP task on example data
python test_worker_local.py --task shap --example 1

# Run PySR with limited iterations
python test_worker_local.py --task pysr --example 1 --niterations 5
```

## Monitoring Jobs

### Via Command Line (SSH)

```bash
# List your jobs
squeue -u <username>

# Job details
scontrol show job <job_id>

# Job history
sacct -j <job_id> --format=JobID,JobName,State,ExitCode,Elapsed,MaxRSS

# Cancel a job
scancel <job_id>
```

### Via REST API

```bash
# Get job status
curl -H "Authorization: Bearer $SLURM_AUTH_TOKEN" \
     -H "Slurm-User-Name: $SLURM_USER_NAME" \
     http://slurm.science-cloud.hu:6820/slurm/v0.0.41/job/<job_id>
```

### Check Job Output

```bash
# SSH to cluster
ssh <username>@slurm.science-cloud.hu

# View job stdout
cat /storage/<username>/syxplain/<job-uuid>/output.json.stdout

# View job stderr
cat /storage/<username>/syxplain/<job-uuid>/output.json.stderr

# View results
cat /storage/<username>/syxplain/<job-uuid>/output.json | python -m json.tool
```

## Troubleshooting

### Connection Issues

**"Connection refused" or timeout:**
- **Local development (native):** Make sure the SSH tunnel is open:
  ```bash
  ssh ai4science@slurm.science-cloud.hu -L 6820:localhost:6820
  ```
  Then use `SLURM_API_URL=http://localhost:6820` in your `.env`
- **Local development (Docker):** The tunnel must bind to all interfaces, not just localhost:
  ```bash
  ssh ai4science@slurm.science-cloud.hu -L 0.0.0.0:6820:localhost:6820
  ```
  Then use `SLURM_API_URL=http://host.docker.internal:6820` in your `.env`
- **Production:** Verify the API URL: `http://slurm.science-cloud.hu:6820`
- Check your network/firewall allows outbound connections to port 6820
- Test with curl: `curl http://slurm.science-cloud.hu:6820/slurm/v0.0.41/ping`

**"401 Unauthorized":**
- Token may be expired - generate a new one
- Token may be for wrong user - verify `SLURM_USER_NAME` matches token

### Job Failures

**Job stuck in PENDING:**
```bash
# Check why via SSH
squeue -u <username> -l
scontrol show job <job_id> | grep Reason
```

Common reasons:
- `Resources` - waiting for nodes to free up
- `Priority` - other jobs have higher priority
- `QOSMaxJobsPerUserLimit` - hit job limit

**Job fails immediately:**
- Check job stderr: `cat /storage/.../output.json.stderr`
- Verify worker is deployed correctly
- Verify staging directory exists and is writable

**"ModuleNotFoundError: syxplain_worker":**
- Worker code not installed on compute nodes
- If using conda: activate environment not working
- If using Singularity: container path incorrect

**Julia compilation errors:**
- First PySR run compiles Julia (slow but one-time)
- If using container, Julia should be pre-compiled
- Rebuild container if Julia issues persist

### File Transfer Issues

**"File not found" during upload:**
- Staging directory doesn't exist
- Create it: `ssh user@slurm... "mkdir -p /storage/<user>/syxplain"`

**"Permission denied":**
- Directory not owned by your user
- Check permissions: `ls -la /storage/<user>/`

### Container Issues

**Container not found:**
- Verify path: `/storage/<username>/containers/syxplain-worker.sif`
- Check file was copied: `ssh user@slurm... "ls -la /storage/<user>/containers/"`

**Container can't access files:**
- Need bind mount: `singularity run --bind /storage:/storage ...`

**Out of memory during container build:**
```bash
export SINGULARITY_TMPDIR=/path/to/large/tmp
./build-singularity.sh
```

## Additional Resources

- [slurm_worker/README.md](../slurm_worker/README.md) - Detailed worker documentation
- [Slurm Documentation](https://slurm.schedmd.com/documentation.html)
- [slurmrestd API Reference](https://slurm.schedmd.com/rest_api.html)
- [Singularity Documentation](https://docs.sylabs.io/guides/latest/user-guide/)
