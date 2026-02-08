# Syxplain

[![CI/CD](https://github.com/HUN-REN-AI1Science/syxplain/actions/workflows/deploy.yml/badge.svg)](https://github.com/HUN-REN-AI1Science/syxplain/actions/workflows/deploy.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/downloads/release/python-3100/)
[![Node.js 24.12.0](https://img.shields.io/badge/node.js-24.12.0_LTS-339933.svg)](https://nodejs.org/)
[![React 18.3.1](https://img.shields.io/badge/react-18.3.1-61dafb.svg)](https://react.dev/)
[![Slurm](https://img.shields.io/badge/Slurm-HPC-orange.svg)](https://slurm.schedmd.com/)

This is a proof of concept system which uses state of the art symbolic regression models to predict a selected variable in a dataset and explain the predicted equations in natural language using large language models. Setting the hiperparameters of the symbolic regression can be tedious, so here we use an LLM with vision capabilities to analyze the dataset and suggest hiperparameters for the symbolic regression model.

## Quick Navigation

| I want to... | Go to |
|--------------|-------|
| Run locally for development | [Quick Start](#quick-start-development) |
| Deploy to production server | [Production Deployment](#production-deployment) |
| Set up Slurm HPC compute | [SLURM.md](./SLURM.md) |
| Develop the Slurm worker | [slurm_worker/README.md](./slurm_worker/README.md) |

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start (Development)](#quick-start-development)
- [Docker Compose Configurations](#docker-compose-configurations)
- [Environment Variables](#environment-variables)
- [Production Deployment](#production-deployment)
- [Slurm Integration](#slurm-integration)
- [Admin Setup](#admin-setup)
- [Feedback System](#feedback-system)

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
                    │  └──────────────┬───────────────────────┘   │
                    │                 │                           │
                    │                 ▼                           │
                    │  ┌──────────────────────────────────────┐   │
                    │  │     Slurm Compute Backend            │   │
                    │  │   (via slurmrestd REST API)          │   │
                    │  └──────────────┬───────────────────────┘   │
                    └─────────────────┼───────────────────────────┘
                                      │ HTTP (port 6820)
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
    ┌─────────────────┐                           ┌─────────────────┐
    │   SHAP Task     │                           │   PySR Task     │
    │ - Feature       │                           │ - Symbolic      │
    │   interactions  │                           │   regression    │
    └─────────────────┘                           └─────────────────┘
```

Compute-intensive tasks (SHAP analysis, PySR symbolic regression) are submitted to an external **Slurm cluster** at `slurm.science-cloud.hu` via the slurmrestd REST API.

## Prerequisites

- Docker and Docker Compose
- An OpenAI-compatible LLM API key
- Access to the Slurm cluster (SSH for token generation only)

## Quick Start (Development)

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env with your API keys and Slurm config

# 2. Generate Slurm token (requires one-time SSH access)
ssh <username>@slurm.science-cloud.hu "scontrol token username=<username> lifespan=3600"
# Copy token to .env as SLURM_AUTH_TOKEN

# 3. Start the development stack
docker-compose up --build
```

The development stack includes:
- PostgreSQL database on `localhost:5432`
- Backend API on `http://localhost:8000` (with hot reload)
- Frontend on `http://localhost:5173` (with hot reload via Vite)

## Docker Compose Configurations

| File | Purpose | Use Case |
|------|---------|----------|
| `docker-compose.yml` | Development | Local development with hot reload |
| `docker-compose.prod.yml` | Production | Production deployment |

### Development

```bash
docker-compose up --build
```

### Production

```bash
docker-compose -f docker-compose.prod.yml up -d
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

**Required:**
- `OPENAI_API_KEY` - LLM API key
- `SLURM_API_URL` - Slurm REST API (`http://slurm.science-cloud.hu:6820`)
- `SLURM_AUTH_TOKEN` - JWT token from `scontrol token`
- `SLURM_USER_NAME` - Your Slurm username
- `SLURM_STAGING_DIR` - Staging directory on cluster (`/storage/<username>/syxplain`)

**Optional:**
- `OPENAI_API_BASE` - Custom LLM endpoint
- `OPENAI_MODEL_NAME` - Model name (default: `gpt-4o`)
- `SLURM_PARTITION` - Slurm partition (default: `batch_cpu_m2.large`)
- `SUPABASE_*` - For authentication
- `LANGFUSE_*` - For LLM tracing
- `GITHUB_FEEDBACK_TOKEN` - GitHub personal access token for creating feedback issues
- `GITHUB_FEEDBACK_REPO_OWNER` - GitHub repository owner (e.g. `HUN-REN-AI1Science`)
- `GITHUB_FEEDBACK_REPO_NAME` - GitHub repository name (e.g. `syxplain`)

See `.env.example` for the complete list.

## Production Deployment

### 1. Generate Long-Lived Token

```bash
ssh <username>@slurm.science-cloud.hu "scontrol token username=<username> lifespan=31536000"
```

### 2. Deploy Worker to Slurm Cluster

Build and deploy the Singularity container:

```bash
cd slurm_worker
./build-singularity.sh
scp syxplain-worker.sif <username>@slurm.science-cloud.hu:/storage/<username>/containers/
```

### 3. Configure Production Environment

Set all required environment variables in your deployment configuration.

### 4. Start Services

```bash
docker-compose -f docker-compose.prod.yml up -d
```

## Slurm Integration

The backend communicates with the Slurm cluster via the **slurmrestd REST API** - no SSH tunnel is required. The API is publicly accessible at `slurm.science-cloud.hu:6820`.

**Key points:**
- Input/output data is transferred via HTTP (base64 encoded JSON)
- Job scripts are submitted via the REST API
- The worker code must be pre-deployed on the cluster (Singularity container or conda environment)
- SSH is only needed to generate authentication tokens

For detailed Slurm setup, architecture diagrams, worker deployment, and troubleshooting, see:
- **[SLURM.md](./SLURM.md)** - Complete Slurm integration guide
- **[slurm_worker/README.md](./slurm_worker/README.md)** - Worker documentation

### Quick Connectivity Test

```bash
curl -H "Authorization: Bearer $SLURM_AUTH_TOKEN" \
     -H "Slurm-User-Name: $SLURM_USER_NAME" \
     http://slurm.science-cloud.hu:6820/slurm/v0.0.41/ping
```

## Admin Setup

### Granting HUN-REN API Key Access

Add admin email addresses to the `ADMIN_EMAILS` environment variable:

```bash
ADMIN_EMAILS=admin@example.com,admin2@example.com
```

Admins can manage user permissions through the Admin UI at `/admin`.

## Feedback System

Users can report bugs and request features directly from the app via the **Feedback** button in the header. Submissions automatically include application context (current page, run ID, browser info) to help with diagnosis.

### Without GitHub (default)

Feedback is logged to the backend console. No additional configuration needed.

### With GitHub Issues

To automatically create GitHub issues from feedback, set these environment variables:

```bash
GITHUB_FEEDBACK_TOKEN=ghp_...        # Personal access token with `repo` scope
GITHUB_FEEDBACK_REPO_OWNER=your-org  # Repository owner
GITHUB_FEEDBACK_REPO_NAME=your-repo  # Repository name
```

Bug reports are labeled `bug`, feature requests are labeled `enhancement`. If the GitHub API is unreachable, feedback silently falls back to logging.
