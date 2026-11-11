# Configuration

All settings are environment variables, read by `backend/core/config.py`. Put them in
`.env` at the repository root; [`.env.example`](../.env.example) lists them with
comments.

- In development, `docker-compose.yml` passes every variable in `.env` to the backend and
  supplies working defaults for the rest.
- In production, `docker-compose.prod.yml` passes the listed variables. Variables it marks
  as required stop `docker compose up` with an error when they are missing.

## LLM

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | – | **Required.** Server-side key, used for users with server-key access |
| `OPENAI_API_BASE` | – | OpenAI-compatible endpoint; empty = api.openai.com |
| `OPENAI_MODEL_NAME` | `gpt-4o` | Main model: agent, configuration, explanation, literature scout |
| `SMALL_MODEL_NAME` | `gpt-5-mini` | Small model for lightweight tasks (column description suggestions) |
| `SMALL_USER_MODEL_NAME` | `gemini-2.5-flash` | Small model used with a user's own Gemini key |
| `USER_API_MODELS` | `gemini-3.1-pro-preview,gemini-3-pro-preview,gemini-2.5-pro` | Models users can choose with their own key |
| `LLM_PRICES_JSON` | – | Extra or overriding prices, USD per 1M tokens `[input, cached input, output]` per model |
| `LLM_WEB_SEARCH_USD` | `0.01` | Price per web search call |

The literature scout calls the main model through the OpenAI Responses API with the
web-search tool, so it needs an endpoint that supports it (OpenAI does). If the scout
fails or is unavailable, the run continues: the discoveries are still related to the
classic named laws. Users on their own keys get the literature step only when they also
give an OpenAI key.

Users without server-key access bring their own key in the web app or the API: Gemini, or
any OpenAI-compatible endpoint.

## Authentication (Keycloak)

| Variable | Default | Description |
|---|---|---|
| `KEYCLOAK_URL` | `http://localhost:8080/keycloak` | Keycloak base URL as the backend reaches it (JWKS, Admin API) |
| `KEYCLOAK_REALM` | `syxplain` | Realm |
| `KEYCLOAK_CLIENT_ID` | `syxplain-frontend` | Public OIDC client of the web app |
| `KEYCLOAK_ADMIN_USERNAME` / `KEYCLOAK_ADMIN_PASSWORD` | `admin` / `admin` | Admin account, used to manage user roles. **Change in production** |
| `KEYCLOAK_ISSUER` | – | Expected token issuer. Empty in development; `https://<domain>/keycloak/realms/syxplain` in production |
| `SERVER_KEYS_ROLE` | `server-llm-access` | Realm role that lets a user run on the server's LLM keys (`syxplain-admin` always can) |
| `KEYCLOAK_ALLOWED_CLIENTS` | – | Comma-separated Keycloak client ids whose access tokens are accepted (the token's `azp`). Empty accepts any client of the realm; in production list the web client and the [technical clients](mcp.md#technical-account) |
| `VITE_KEYCLOAK_URL` / `VITE_KEYCLOAK_REALM` / `VITE_KEYCLOAK_CLIENT_ID` | dev values | Frontend build-time settings (browser-reachable Keycloak URL) |

## Compute (Slurm)

PySR searches run as Slurm jobs submitted through the slurmrestd REST API. In development,
the compose file points the backend at a local emulator. See [slurm.md](slurm.md) for
running on a real cluster.

| Variable | Default | Description |
|---|---|---|
| `SLURM_API_URL` | – (dev: local emulator) | slurmrestd URL, e.g. `http://slurm.example.org:6820` |
| `SLURM_AUTH_TOKEN` | – | JWT from `scontrol token username=<user> lifespan=<seconds>` |
| `SLURM_USER_NAME` | `slurm` | Cluster user the jobs run as |
| `SLURM_STAGING_DIR` | `/tmp/syxplain` | Shared directory for job logs and output |
| `SLURM_CONTAINER_PATH` | – | Singularity worker image. Empty = run `python -m slurm_worker` in the conda env `syxplain_worker` |
| `SLURM_CONTAINER_BINDS` | `SLURM_STAGING_DIR` | Host paths mounted into the container (comma-separated `--bind` specs) |
| `SLURM_JULIA_DEPOT` | `$SLURM_STAGING_DIR/.julia` | Writable Julia depot, stacked on the image's precompiled one |
| `SLURM_PARTITION` | – | Partition; empty = the cluster's default |
| `SLURM_CPUS` | `4` | CPUs per job |
| `SLURM_MEMORY` | `8G` | Memory per job |
| `SLURM_TIME_LIMIT` | `04:00:00` | Time limit per job |
| `SLURM_RETRY_INTERVAL` | `60` | Seconds before retrying a submission rejected by quota |
| `WORKER_CALLBACK_URL` | – (dev: `http://backend:8000/api/internal`) | Where workers fetch input and report progress. Must be reachable from the compute nodes |
| `WORKER_CALLBACK_TOKEN` | – | Shared secret for worker callbacks |
| `JOB_POLL_INTERVAL` | `10` | Seconds between job status polls |
| `COMPUTE_MAX_RETRIES` | `3` | Retries of a failed submission |

The local emulator's own setting exists only in development (`docker-compose.yml`). It
runs each job with the CPUs the job requests (`SLURM_CPUS`).

| Variable | Default | Description |
|---|---|---|
| `LOCAL_PYSR` | `false` | `true` builds Julia + PySR into the emulator and runs searches for real |

## Discovery agent

These are budget ceilings; the agent stops earlier when it is done.

| Variable | Default | Description |
|---|---|---|
| `DISCOVERY_AGENT_ENABLED` | `true` | `false` = fixed pipeline: one PySR search, no agent |
| `DISCOVERY_AGENT_MODEL` | `OPENAI_MODEL_NAME` | Agent model for server keys |
| `DISCOVERY_MAX_ITERS` | `40` | Agent reasoning steps |
| `DISCOVERY_MAX_PYSR_RUNS` | `6` | PySR searches per run, including the baseline |
| `DISCOVERY_MAX_SINDY_RUNS` | `6` | SINDy rate-law searches per run |
| `DISCOVERY_WALL_CLOCK_MIN` | `150` (dev: `30`) | Agent time budget in minutes |
| `DISCOVERY_MAX_CONCURRENT_PYSR` | `2` | PySR searches running at the same time |
| `DISCOVERY_SHAP_IMAGES` | `true` | Show SHAP plots to the agent as images |
| `DISCOVERY_PYSR_TIMEOUT_S` | `1800` | Timeout per PySR search (seconds) |
| `DISCOVERY_REVIEW_STEPS` | `5` | Read-only agent steps for searches that finish after it stopped (0 = off) |
| `DISCOVERY_FIRST_RESULT_TIMEOUT_S` | `3600` | Max wait for a first PySR result when none has completed |
| `DISCOVERY_SPARSE_COLUMN_THRESHOLD` | `0.2` | Drop a predictor whose missing values alone would remove more than this share of rows |
| `DISCOVERY_MAX_CATEGORICAL_LEVELS` | `10` | Consecutive integer codes with up to this many levels are treated as categories |

## Application

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://syxplain:syxplain@localhost:5432/syxplain` | PostgreSQL connection |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` / `DB_POOL_RECYCLE` | `40` / `5` / `30` / `300` | Connection pool |
| `ANALYSIS_TIMEOUT_HOURS` | `24` | Run timeout; `0` disables it |
| `MAX_FILE_SIZE_MB` | `50` | Upload size limit |
| `MAX_ACTIVE_RUNS_PER_USER` | `3` | Pending and running analyses one account may have at a time; `0` removes the limit. Raise it for a technical account shared by many people |
| `MCP_MAX_CSV_KB` | `256` | Largest CSV the MCP `start_analysis` tool accepts as text |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins (set your domain in production) |
| `GITHUB_FEEDBACK_TOKEN` / `_REPO_OWNER` / `_REPO_NAME` | – | When all three are set, in-app feedback opens GitHub issues; otherwise it is only logged |

## Production deployment

These are read by `docker-compose.prod.yml` only. See [deployment.md](deployment.md).

| Variable | Description |
|---|---|
| `POSTGRES_PASSWORD`, `KC_DB_PASSWORD` | Database passwords (required) |
| `KC_HOSTNAME` | Public hostname of Keycloak, e.g. `syxplain.example.org` (required) |
| `SERVER_NAME` | Public domain for nginx. HTTPS is enabled when `/etc/letsencrypt/live/$SERVER_NAME/` exists |
| `BACKEND_IMAGE`, `FRONTEND_IMAGE` | Images to run (default: the project's GHCR images) |
| `BACKEND_PORT`, `FRONTEND_HTTP_PORT`, `FRONTEND_HTTPS_PORT` | Published ports (`8000`, `80`, `443`) |
| `BACKEND_CPU_LIMIT`, `BACKEND_MEMORY_LIMIT` | Backend container limits (`4`, `4G`). Keep the CPU limit at or below the host's CPU count |
