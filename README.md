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

Syxplain uses a **Slurm-based compute architecture** that separates LLM operations from compute-intensive tasks. The Backend API and the Slurm HPC cluster run on different servers:

```
  Application Server                          Slurm HPC Cluster
 ┌──────────────────┐                        (slurm.science-cloud.hu)
 │     Frontend     │                  ┌──────────────────────────────────┐
 │     (React)      │                  │                                  │
 └────────┬─────────┘                  │  ┌────────────────────────────┐  │
          │                            │  │    slurmrestd REST API     │  │
          ▼                            │  │       (port 6820)          │  │
 ┌──────────────────┐  HTTP (6820)     │  └─────────────┬──────────────┘  │
 │   Backend API    │─────────────────▶│                │                 │
 │                  │                  │                ▼                 │
 │  - Orchestrator  │                  │  ┌──────────────────────────┐    │
 │  - Discovery     │  HTTP (callback) │  │     Slurm Scheduler      │    │
 │    agent (LLM)   │◀─────────────────│  └─────────┬──────────┬─────┘    │
 │  - Classic fits  │                  │            │          │          │
 │  - SSE           │                  │            ▼          ▼          │
 └──────────────────┘                  │  ┌────────────┐ ┌────────────┐   │
                                       │  │ PySR task  │ │ PySR task  │...│
                                       │  │  pysr_1    │ │  pysr_2    │   │
                                       │  └────────────┘ └────────────┘   │
                                       └──────────────────────────────────┘
```

PySR symbolic-regression searches are submitted to an external **Slurm cluster** at `slurm.science-cloud.hu` via the slurmrestd REST API. The backend runs on a separate application server and communicates with the cluster over HTTP.

### Agentic equation discovery

Equations are found by an **AI-scientist agent** (DSPy ReAct, `backend/services/discovery/`) that runs in the backend:

1. A baseline PySR search (all continuous features, operators chosen by an LLM from the feature plots) is submitted first, so the cluster queue wait overlaps with the agent's work. Integer-coded categories (soil type codes and the like) are never used as magnitudes, only as `level(x, k)` indicators.
2. The agent profiles the data: correlations, mutual information, random-forest permutation importance, a **noise ceiling** (out-of-fold random-forest R², roughly the best achievable accuracy) and **SHAP** on that forest: importance, interacting feature pairs (candidates for product terms and multiplicative laws) and each feature's partial-effect shape with the other features accounted for.
3. It fits **classic named laws** (Mitscherlich, Michaelis-Menten/Langmuir, Freundlich/power, logistic, Gompertz, linear/quadratic-plateau, Gaussian peak, Mitscherlich-Baule, Cobb-Douglas, ...) and its own formulas. Each fit comes back with **diagnosed reasons it falls short**: wrong curve shape (and where), missing variable (and which one), variance growing with the value, unidentifiable parameters, or "matches the noise ceiling".
4. Guided by those reasons, it launches **targeted PySR searches** (feature subset, operators, target transform, its best formulas as warm-start guesses) and compares the results with the classic laws.
5. It records findings in a **lab notebook** (rejected forms with reasons, insights, data issues), which the explanation LLM reads.
6. A literature scout searches the web in the background (the main model, `OPENAI_MODEL_NAME`, with the Responses API web-search tool, maximum search context) for published laws, writes them solved for the target, and fits each one to the data like any other model, so the agent can say whether the published law holds for these samples.
7. **Code, not an LLM, picks the headline model**: models are ranked by 5-fold cross-validation on the training rows, checked by guards, and the simplest model within one standard error of the best wins. The 20% holdout is scored once at the end; datasets under 40 rows use cross-validation only.

The agent is bounded by a budget (`DISCOVERY_*` variables; ceilings, it stops earlier when done). If it fails, the run still finishes with the baseline search and an automatic screen of the classic catalog. `python test_worker_local.py --task classic --example 1` runs the classic-law screen locally without any services.

**Cost per analysis.** Every LLM call of a run is counted (tokens per model, cached and reasoning tokens, web searches) and priced. Each run logs one line and stores the same summary under `results.usage`:

```bash
docker logs syxplain-backend 2>&1 | grep "ANALYTICS run_usage"
# ANALYTICS run_usage {"run_id":"...","outcome":"completed","models":{"openai/gpt-6.1-sol":{"calls":17,"input_tokens":...,"cost_usd":0.41}},"total_cost_usd":0.41,...}
```

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
- `SLURM_PARTITION` - Slurm partition (default: `cpu_m2.2xlarge`)
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

### Managing Roles via Keycloak

Admin and HUN-REN API key access are managed through Keycloak realm roles:

1. Open the Keycloak admin console (e.g. `http://localhost:8080/keycloak/admin`)
2. Navigate to **Users** → select a user → **Role mapping** tab
3. Assign roles:
   - `syxplain-admin` — full admin access (admin panel, all endpoints)
   - `hunren-member` — HUN-REN API key access (built-in API keys)

Admins can also manage HUN-REN access for users through the Admin UI at `/admin`.

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
