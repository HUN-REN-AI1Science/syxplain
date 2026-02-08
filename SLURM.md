# Slurm Integration Guide

This guide explains how Syxplain integrates with a Slurm HPC cluster for compute-intensive tasks (SHAP analysis, PySR symbolic regression).

## TL;DR Quick Setup

Get Slurm integration running in 5 steps:

1. **Get cluster access** - Contact your Slurm admin for SSH access and a username
2. **Create staging directory** on cluster:
   ```bash
   ssh <username>@slurm.science-cloud.hu "mkdir -p /storage/<username>/syxplain"
   ```
3. **Generate auth token**:
   ```bash
   ssh <username>@slurm.science-cloud.hu "scontrol token username=<username> lifespan=31536000"
   ```
4. **Deploy worker** - See [slurm_worker/README.md](./slurm_worker/README.md) for container build instructions
5. **Configure `.env`**:
   ```bash
   SLURM_API_URL="http://slurm.science-cloud.hu:6820"
   SLURM_AUTH_TOKEN="<token-from-step-3>"
   SLURM_USER_NAME="<username>"
   SLURM_STAGING_DIR="/storage/<username>/syxplain"
   SLURM_CONTAINER_PATH="/storage/<username>/containers/syxplain-worker.sif"
   ```

**Test connectivity:**
```bash
curl -H "Authorization: Bearer $SLURM_AUTH_TOKEN" \
     -H "Slurm-User-Name: $SLURM_USER_NAME" \
     http://slurm.science-cloud.hu:6820/slurm/v0.0.41/ping
```

For detailed configuration and troubleshooting, continue reading.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [How It Works](#how-it-works)
- [Environment Configuration](#environment-configuration)
- [Token Management](#token-management)
- [Testing the Integration](#testing-the-integration)
- [Monitoring Jobs](#monitoring-jobs)
- [Troubleshooting](#troubleshooting)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Your Server / Local Machine                       │
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
│                     Slurm Cluster (slurm.science-cloud.hu)                  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         slurmrestd API                               │   │
│  │                     http://slurm.science-cloud.hu:6820               │   │
│  │                                                                      │   │
│  │  - Receives job submissions                                          │   │
│  │  - Handles file upload/download (base64 over HTTP)                   │   │
│  │  - Reports job status                                                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         Slurm Scheduler                              │   │
│  │                                                                      │   │
│  │  - Queues jobs                                                       │   │
│  │  - Allocates resources                                               │   │
│  │  - Dispatches to compute nodes                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                    ┌───────────────┴───────────────┐                        │
│                    ▼                               ▼                        │
│  ┌─────────────────────────────┐   ┌─────────────────────────────┐          │
│  │      Compute Node 1         │   │      Compute Node N         │          │
│  │                             │   │                             │          │
│  │  ┌───────────────────────┐  │   │  ┌───────────────────────┐  │          │
│  │  │  syxplain_worker      │  │   │  │  syxplain_worker      │  │          │
│  │  │  (Singularity)        │  │   │  │  (Singularity)        │  │          │
│  │  │                       │  │   │  │                       │  │          │
│  │  │  - SHAP analysis      │  │   │  │  - PySR regression    │  │          │
│  │  │  - PySR regression    │  │   │  │  - SHAP analysis      │  │          │
│  │  └───────────────────────┘  │   │  └───────────────────────┘  │          │
│  └─────────────────────────────┘   └─────────────────────────────┘          │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      Shared Storage (/storage/)                      │   │
│  │                                                                      │   │
│  │  /storage/<username>/syxplain/           <- Staging directory        │   │
│  │  ├── logs/                               <- Job logs                 │   │
│  │  │   └── 2025-06-15/                     <- Date-organized           │   │
│  │  │       ├── 143052_shap_a1b2c3d4_e5f6g7h8.stdout                    │   │
│  │  │       └── 143052_shap_a1b2c3d4_e5f6g7h8.stderr                    │   │
│  │                                                                      │   │
│  │  /storage/<username>/containers/         <- Singularity containers   │   │
│  │  └── syxplain-worker.sif                                             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## How It Works

1. Backend uploads input data to Slurm staging directory via REST API
2. Backend submits job script via slurmrestd
3. Slurm scheduler runs the worker (Singularity container)
4. Worker writes results to staging directory
5. Backend polls for completion and downloads results

**Data transfer:** All data is base64 encoded JSON over HTTP - no SSH tunnel needed for file transfer.

**Worker deployment:** The worker code must be pre-deployed as a Singularity container. See [slurm_worker/README.md](./slurm_worker/README.md) for build instructions.

## Environment Configuration

### Configuration Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SLURM_API_URL` | Yes | - | Slurm REST API endpoint |
| `SLURM_AUTH_TOKEN` | Yes | - | JWT token (see [Token Management](#token-management)) |
| `SLURM_USER_NAME` | Yes | - | Your Slurm username |
| `SLURM_STAGING_DIR` | Yes | - | Staging directory on cluster storage |
| `SLURM_CONTAINER_PATH` | Yes* | - | Path to Singularity container |
| `SLURM_PARTITION` | No | `batch_cpu_m2.large` | Slurm partition for jobs |
| `SLURM_CPUS` | No | `4` | CPUs per job |
| `SLURM_MEMORY` | No | `8G` | Memory per job |
| `SLURM_TIME_LIMIT` | No | `04:00:00` | Max job time (HH:MM:SS) |
| `WORKER_CALLBACK_URL` | No | - | URL for progress updates |
| `WORKER_CALLBACK_TOKEN` | No | - | Auth token for callbacks |

\* Required for production; falls back to conda for development.

### Local Development: SSH Tunnel

The Slurm API is publicly accessible from the production server. For **local development**, set up an SSH tunnel:

```bash
# Native Python/venv development
ssh <username>@slurm.science-cloud.hu -L 6820:localhost:6820
# Use: SLURM_API_URL=http://localhost:6820

# Docker development (bind to all interfaces)
ssh <username>@slurm.science-cloud.hu -L 0.0.0.0:6820:localhost:6820
# Use: SLURM_API_URL=http://host.docker.internal:6820
```

### Progress Callbacks (Optional)

For real-time progress updates, configure callback URL and token. Without callbacks, jobs still complete - you just won't see live progress.

For local development, use [ngrok](https://ngrok.com/) to expose your backend:
```bash
ngrok http 8000
# Copy URL to WORKER_CALLBACK_URL in .env
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

## Testing the Integration

### Test API Connectivity

```bash
curl -H "Authorization: Bearer $SLURM_AUTH_TOKEN" \
     -H "Slurm-User-Name: $SLURM_USER_NAME" \
     $SLURM_API_URL/slurm/v0.0.41/ping
```

Expected: `{"meta":{"slurm":{"version":{"major":...}}}}`

For local development, ensure the SSH tunnel is running first (see [Local Development](#local-development-ssh-tunnel)).

### Test Worker Locally

Before deploying, test the worker on your machine:

```bash
cd slurm_worker
pip install -r requirements.txt
python test_worker_local.py --task shap --example 1
```

See [slurm_worker/README.md](./slurm_worker/README.md) for more testing options.

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

Logs are organized in date-structured directories under `{staging_dir}/logs/`.
Filenames encode the timestamp, task type, run ID, and job UUID:

```
logs/2025-06-15/143052_shap_a1b2c3d4_e5f6g7h8.stdout
                HHMMSS_type_runid____jobuuid
```

```bash
# SSH to cluster
ssh <username>@slurm.science-cloud.hu

# List today's logs
ls /storage/<username>/syxplain/logs/$(date +%Y-%m-%d)/

# View stdout/stderr for a specific job
cat /storage/<username>/syxplain/logs/2025-06-15/143052_shap_a1b2c3d4_e5f6g7h8.stdout
cat /storage/<username>/syxplain/logs/2025-06-15/143052_shap_a1b2c3d4_e5f6g7h8.stderr
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
- Check job stderr: `cat /storage/<username>/syxplain/logs/<date>/<logfile>.stderr`
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

- [slurm_worker/README.md](./slurm_worker/README.md) - Worker deployment, task types, and container building
- [Slurm Documentation](https://slurm.schedmd.com/documentation.html)
- [slurmrestd API Reference](https://slurm.schedmd.com/rest_api.html)
- [Singularity Documentation](https://docs.sylabs.io/guides/latest/user-guide/)
