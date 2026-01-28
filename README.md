# Syxplain

[![CI/CD](https://github.com/HUN-REN-AI1Science/syxplain/actions/workflows/deploy.yml/badge.svg)](https://github.com/HUN-REN-AI1Science/syxplain/actions/workflows/deploy.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/downloads/release/python-3100/)
[![Node.js 24.12.0](https://img.shields.io/badge/node.js-24.12.0_LTS-339933.svg)](https://nodejs.org/)
[![React 18.3.1](https://img.shields.io/badge/react-18.3.1-61dafb.svg)](https://react.dev/)
[![Slurm](https://img.shields.io/badge/Slurm-HPC-orange.svg)](https://slurm.schedmd.com/)

This is a proof of concept system which uses state of the art symbolic regression models to predict a selected variable in a dataset and explain the predicted equations in natural language using large language models. Setting the hiperparameters of the symbolic regression can be tedious, so here we use an LLM with vision capabilities to analyze the dataset and suggest hiperparameters for the symbolic regression model.

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Slurm Setup (Required)](#slurm-setup-required)
- [Quick Start (Development)](#quick-start-development)
- [Docker Compose Configurations](#docker-compose-configurations)
- [Environment Variables Reference](#environment-variables-reference)
- [Production Deployment](#production-deployment)
- [Testing Worker Tasks Locally](#testing-worker-tasks-locally)
- [Slurm Worker Reference](#slurm-worker-reference)
- [Admin Setup](#admin-setup)

## Architecture

Syxplain uses a **Slurm-based compute architecture** that separates LLM operations from compute-intensive tasks:

```
┌─────────────┐     ┌─────────────────────────────────────────────┐
│   Frontend  │────▶│              Backend API                    │
│   (React)   │     │  ┌──────────────────────────────────────┐   │
└─────────────┘     │  │         Orchestrator Service         │   │
                    │  │  - Data summary & visualization      │   │
                    │  │  - LLM config generation             │   │
                    │  │  - LLM equation explanation          │   │
                    │  │  - Deep research (optional)          │   │
                    │  └──────────────┬───────────────────────┘   │
                    │                 │                           │
                    │                 ▼                           │
                    │  ┌──────────────────────────────────────┐   │
                    │  │     Slurm Compute Backend            │   │
                    │  │   (via slurmrestd API)               │   │
                    │  └──────────────┬───────────────────────┘   │
                    └─────────────────┼───────────────────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
    ┌─────────────────┐                           ┌─────────────────┐
    │   SHAP Task     │                           │   PySR Task     │
    │ - Feature       │                           │ - Symbolic      │
    │   interactions  │                           │   regression    │
    │ - Visualizations│                           │ - Scatter data  │
    └─────────────────┘                           └─────────────────┘
```

Compute-intensive tasks (SHAP analysis, PySR symbolic regression) are submitted to an external **Slurm cluster** at `slurm.science-cloud.hu` via the slurmrestd API.

## Prerequisites

- Docker and Docker Compose
- An OpenAI-compatible LLM API key
- SSH access to `slurm.science-cloud.hu`

## Slurm Setup (Required)

The backend requires access to a Slurm cluster via slurmrestd API. Both development and production environments connect to the external Slurm service.

### 1. SSH Tunnel to Slurm Controller

Connect to the Slurm cluster and forward the API port:

```bash
ssh -L 6820:localhost:6820 <username>@slurm.science-cloud.hu -i <SSH_KEY>
```

Keep this terminal open while developing.

### 2. Generate JWT Token

In the SSH session, generate an authentication token:

```bash
scontrol token username=<username> lifespan=3600
```

Copy the token value. Tokens expire after the specified lifespan (3600 seconds = 1 hour).

### 3. Configure Environment

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Add your Slurm configuration to `.env`:

```bash
SLURM_API_URL=http://localhost:6820
SLURM_AUTH_TOKEN=<paste-token-here>
SLURM_USER_NAME=<your-username>
SLURM_PARTITION=batch_cpu_m2.large
SLURM_STAGING_DIR=/storage/<username>/syxplain
```

### 4. Test Slurm Connection

With the SSH tunnel active, verify connectivity:

```bash
curl -H "Authorization: Bearer $SLURM_AUTH_TOKEN" \
     -H "Slurm-User-Name: $SLURM_USER_NAME" \
     http://localhost:6820/slurm/v0.0.41/ping
```

## Quick Start (Development)

Get started in 4 steps:

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env with your API keys and Slurm config

# 2. Start SSH tunnel (in a separate terminal)
ssh -L 6820:localhost:6820 <username>@slurm.science-cloud.hu -i <SSH_KEY>

# 3. Generate Slurm token (in SSH session)
scontrol token username=<username> lifespan=3600
# Copy token to .env as SLURM_AUTH_TOKEN

# 4. Start the development stack
docker-compose up --build
```

The development stack includes:
- PostgreSQL database on `localhost:5432`
- Backend API on `http://localhost:8000` (with hot reload)
- Frontend on `http://localhost:5173` (with hot reload via Vite)

Source code is mounted into containers, so changes to backend or frontend code will automatically reload.

## Docker Compose Configurations

| File | Purpose | Use Case |
|------|---------|----------|
| `docker-compose.yml` | Development | Local development with hot reload |
| `docker-compose.prod.yml` | Production | Production deployment |

### Development (`docker-compose.yml`)

The default configuration is optimized for developers:
- **Hot reload**: Source code is mounted for automatic reloading on changes
- **External Slurm**: Connects to `slurm.science-cloud.hu` via SSH tunnel

**Required environment variables** (set in `.env`):
- `OPENAI_API_KEY`: Your API key for the LLM service
- `SLURM_API_URL`: slurmrestd API URL (usually `http://localhost:6820` via tunnel)
- `SLURM_AUTH_TOKEN`: JWT token from `scontrol token`
- `SLURM_USER_NAME`: Your Slurm username
- `SLURM_STAGING_DIR`: Staging directory on Slurm cluster

**Optional environment variables:**
- `OPENAI_API_BASE`: Custom LLM endpoint
- `OPENAI_MODEL_NAME`: Model name (default: `gpt-4o`)
- `SUPABASE_*`: For Supabase authentication (optional for local dev)
- `LANGFUSE_*`: For LLM tracing (optional)

### Production (`docker-compose.prod.yml`)

For production deployment:

```bash
docker-compose -f docker-compose.prod.yml up -d
```

**Required environment variables:**

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | LLM API key |
| `DATABASE_URL` | PostgreSQL connection string |
| `SLURM_API_URL` | slurmrestd API URL |
| `SLURM_AUTH_TOKEN` | Slurm JWT authentication token |
| `SLURM_USER_NAME` | Slurm username |
| `SLURM_STAGING_DIR` | Shared staging directory path |
| `SUPABASE_JWT_SECRET` | JWT secret for authentication |
| `SUPABASE_URL` | Supabase project URL |
| `CORS_ORIGINS` | Allowed CORS origins (e.g., `https://syxplain.example.com`) |
| `VITE_SUPABASE_URL` | Supabase URL for frontend |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon key for frontend |

**Optional production variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_PORT` | `8000` | Backend API port |
| `FRONTEND_PORT` | `8080` | Frontend port |
| `SLURM_PARTITION` | `batch_cpu_m2.large` | Slurm partition name |
| `SLURM_DEFAULT_MEMORY` | `4G` | Memory per job |
| `SLURM_DEFAULT_CPUS` | `2` | CPUs per job |
| `SLURM_DEFAULT_TIME_LIMIT` | `01:00:00` | Job time limit |
| `WORKER_CALLBACK_URL` | - | URL for progress callbacks |
| `WORKER_CALLBACK_TOKEN` | - | Token for callback auth |

## Environment Variables Reference

**LLM Configuration:**
- `OPENAI_API_KEY`: Your API key for the LLM service (required)
- `OPENAI_API_BASE`: Base URL for the LLM API (optional)
- `OPENAI_MODEL_NAME`: Name of the model to use (default: `gpt-4o`)
- `DEEP_RESEARCH_MODEL`: Comma-separated list of deep research models
- `DEEP_RESEARCH_API_KEY`: API key for deep research model
- `DEEP_RESEARCH_API_BASE`: Base URL for deep research API
- `USER_API_MODELS`: Comma-separated list of models for user-provided API keys (default: `gpt-5.2-thinking,gpt-4o`)

**Admin Configuration:**
- `ADMIN_EMAILS`: Comma-separated list of admin email addresses

**Database:**
- `DATABASE_URL`: PostgreSQL connection string

**Authentication:**
- `SUPABASE_URL`: URL of your Supabase project
- `SUPABASE_JWT_SECRET`: JWT secret for Supabase authentication
- `SUPABASE_SERVICE_ROLE_KEY`: Service role key for GDPR account deletion
- `VITE_SUPABASE_URL`: Same as `SUPABASE_URL` (for frontend)
- `VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY`: Supabase publishable key
- `VITE_SUPABASE_ANON_KEY`: Supabase anon key

**Slurm Configuration:**
- `SLURM_API_URL`: URL of slurmrestd API
- `SLURM_AUTH_TOKEN`: JWT token for slurmrestd authentication
- `SLURM_USER_NAME`: Slurm username for job submission
- `SLURM_PARTITION`: Slurm partition to submit jobs (default: `batch_cpu_m2.large`)
- `SLURM_DEFAULT_MEMORY`: Memory per job (default: `4G`)
- `SLURM_DEFAULT_CPUS`: CPUs per job (default: `2`)
- `SLURM_DEFAULT_TIME_LIMIT`: Time limit per job (default: `01:00:00`)
- `SLURM_STAGING_DIR`: Directory for staging input/output files

**Compute Settings:**
- `WORKER_CALLBACK_URL`: URL for Slurm workers to report progress
- `WORKER_CALLBACK_TOKEN`: Secret token for worker authentication
- `JOB_POLL_INTERVAL`: Seconds between job status checks (default: `10`)
- `COMPUTE_MAX_RETRIES`: Max retries for failed compute tasks (default: `3`)

**Performance Tuning:**
- `SHAP_SUBSAMPLE_FRACTION`: Fraction of data for SHAP (default: `0.1`)
- `SHAP_SUBSAMPLE_MIN`: Minimum SHAP samples (default: `1000`)
- `SHAP_SUBSAMPLE_MAX`: Maximum SHAP samples (default: `5000`)
- `ANALYSIS_TIMEOUT_HOURS`: Analysis timeout (default: `24`)
- `MAX_FILE_SIZE_MB`: Max upload size (default: `50`)
- `CORS_ORIGINS`: Allowed CORS origins (default: `*`)
- `DB_POOL_SIZE`: Database pool size (default: `40`)
- `DB_MAX_OVERFLOW`: Max overflow connections (default: `5`)

**LLM Tracing (Langfuse):**
- `LANGFUSE_PUBLIC_KEY`: Langfuse public key
- `LANGFUSE_SECRET_KEY`: Langfuse secret key
- `LANGFUSE_BASE_URL`: Langfuse API URL (default: `https://cloud.langfuse.com`)
- `LANGFUSE_ENABLED`: Enable tracing (default: `false`)

## Production Deployment

### Architecture Overview

```
┌──────────────────┐         ┌─────────────────────────────────┐
│  Backend Server  │         │       Slurm Cluster             │
│  (API + LLM ops) │◀───────▶│  ┌──────────────────────────┐  │
│                  │ slurmrestd │  Compute Nodes             │  │
│                  │         │  │  - syxplain_worker       │  │
│                  │         │  │  - SHAP/PySR execution   │  │
└──────────────────┘         │  └──────────────────────────┘  │
                             │                                 │
                             │  Shared Storage                 │
                             │  /storage/<user>/syxplain/      │
                             └─────────────────────────────────┘
```

### Slurm Configuration

For production, generate a long-lived token:

```bash
scontrol token username=ai4science_admin lifespan=31536000  # 1 year
```

Set environment variables on your production server or in your deployment configuration.

### Worker Deployment (Singularity Container)

Workers are deployed as Singularity containers on the Slurm cluster. The container includes Python, Julia, and all dependencies pre-compiled.

**1. Build the Singularity container:**

On a machine with Singularity installed:

```bash
cd slurm_worker
./build-singularity.sh
```

This creates `syxplain-worker.sif` with:
- Python 3.11 with scientific computing stack
- Julia 1.10.2 with PySR pre-compiled
- SHAP and all required dependencies

**2. Deploy to the Slurm cluster:**

```bash
scp syxplain-worker.sif <username>@slurm.science-cloud.hu:/storage/<username>/containers/
```

Recommended production location:
```
/storage/ai4science_admin/containers/syxplain-worker.sif
```

**3. Test the container:**

SSH to the cluster and verify:

```bash
singularity run /storage/<username>/containers/syxplain-worker.sif --help
```

For detailed worker documentation, see [slurm_worker/README.md](slurm_worker/README.md).

### How It Works

1. **User submits analysis** via the API
2. **Orchestrator** generates data visualizations and PySR config using LLM
3. **Orchestrator** stages input data to `SLURM_STAGING_DIR`
4. **Backend** submits SHAP and PySR jobs to Slurm via slurmrestd
5. **Slurm** schedules jobs on compute nodes
6. **Workers** execute tasks and write results to staging directory
7. **Backend** polls for completion and retrieves results
8. **Orchestrator** generates LLM explanations and returns final results

### Monitoring Jobs

```bash
squeue -u <username>
sacct -j <job_id> --format=JobID,JobName,State,ExitCode,Elapsed
```

### Troubleshooting

**SSH tunnel disconnected:**
- Re-establish the tunnel: `ssh -L 6820:localhost:6820 <user>@slurm.science-cloud.hu -i <key>`
- Consider using autossh for persistent connections

**Token expired:**
- Generate a new token: `scontrol token username=<user> lifespan=3600`
- Update `SLURM_AUTH_TOKEN` in `.env`

**Jobs stuck in PENDING:**
- Check partition availability: `sinfo`
- Verify resource requests fit available nodes

**Jobs fail immediately:**
- Check worker environment is available on compute nodes
- Verify staging directory is accessible
- Check Slurm logs: `scontrol show job <job_id>`

**No progress updates:**
- Verify `WORKER_CALLBACK_URL` and `WORKER_CALLBACK_TOKEN` are set
- Check network connectivity from compute nodes to backend

**Container not found:**
- Verify the container path is correct (default: `/storage/ai4science_admin/containers/syxplain-worker.sif`)
- Check that the `.sif` file was copied to the cluster's shared storage

**Julia compilation slow:**
- The Singularity container pre-compiles Julia; if still slow, rebuild the container
- Ensure you're using the container, not a conda environment

## Testing Worker Tasks Locally

Test SHAP and PySR tasks without Slurm infrastructure:

```bash
# Run SHAP analysis on example data
python test_worker_local.py --task shap --example 1

# Run PySR symbolic regression (quick test)
python test_worker_local.py --task pysr --example 1 --niterations 5
```

See [slurm_worker/README.md](slurm_worker/README.md) for more testing options.

## Slurm Worker Reference

See [slurm_worker/README.md](slurm_worker/README.md) for detailed worker documentation including:
- Singularity container build instructions
- Task input/output formats
- Progress callback API
- Troubleshooting guide

## Admin Setup

### Granting HUN-REN API Key Access

After deployment, users need permission to use the built-in HUN-REN API keys. Users without this permission must provide their own OpenAI API key.

**Environment configuration for admins:**

Add admin email addresses to the `ADMIN_EMAILS` environment variable:

```bash
ADMIN_EMAILS=admin@example.com,admin2@example.com
```

Admins can manage permissions through the Admin UI at `/admin`.
