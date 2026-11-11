# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- MCP endpoint at `/mcp` (streamable HTTP) for chat assistants such as LibreChat: start an
  analysis from inline CSV text, follow it, and read a compact result summary. It runs
  on the server's LLM keys only.
- Technical access: Keycloak service accounts (client-credentials tokens) are accepted on
  `/api/v1` and `/mcp`; `dev/create-technical-client.sh` creates a client and its API key.
- `GET /api/v1/runs/{run_id}/summary`: the outcome of a run in compact form.
- Run status reports the pipeline `phase`, `warnings`, `target_variable`, and the interim
  results of a running analysis. `POST /api/v1/analyze` returns `renamed_columns` and
  accepts column names as written in the file.
- `GET /api/v1/models` reports `server_keys`.
- Settings: `KEYCLOAK_ALLOWED_CLIENTS`, `MAX_ACTIVE_RUNS_PER_USER`, `MCP_MAX_CSV_KB`.

### Changed
- An account can have 3 pending or running analyses at a time by default
  (`MAX_ACTIVE_RUNS_PER_USER`; `0` removes the limit).
- `/api/v1` and `/mcp` are rate-limited per credential instead of per client address.
- `POST /api/v1/analyze` checks the columns and the cluster before storing the file.
- ID and refresh tokens no longer authenticate API calls.
- API-key roles are re-checked against Keycloak every five minutes, also for keys in
  constant use.
- Requires `mcp` 2.3 or later.

### Fixed
- A run could load another user's file when both had uploaded the same filename.
- Excel files whose column names had to be rewritten could not be analysed.
- Runs cut off by a backend restart stayed "running" forever; they are now marked failed
  at startup.
- The API reported `analysis_type: "quick"` for new runs and documented result fields and
  artifacts that no longer exist.

## [1.0.0] - 2026-11

First public release.

### Discovery pipeline
- An AI-scientist agent (DSPy ReAct) steers PySR symbolic-regression searches. It
  profiles the data (noise ceiling, SHAP effects and interactions), explores blind to
  known laws, gets diagnosed reasons why each formula falls short, and keeps a lab
  notebook.
- Discoveries are related to known laws only after exploration:
  - classic named laws are screened on the variables the discoveries use
  - published laws come from a literature scout with web search
  - each relation is equivalent, similar, partial or different
- Code selects the headline model with 5-fold cross-validation, preferring the simplest
  model within one standard error. A one-time holdout score and a SHAP agreement check
  follow.
- A coherence verdict compares the headline with the noise ceiling, the holdout, SHAP,
  known laws, parameter identifiability and the agent's conclusion.
- Time-ordered data:
  - LLM-proposed lag and period features for long series
  - a chronological holdout
  - SINDy rate laws, validated by integration
- LLM cost accounting per run.

### Application
- Web app with live progress (SSE), results page, PDF report, sharing links.
- Keycloak authentication. Users either run on the server's LLM keys (`SERVER_KEYS_ROLE`)
  or bring their own key (Gemini, or any OpenAI-compatible endpoint).
- Programmatic API (`/api/v1`) with per-user API keys.
- Compute on Slurm through slurmrestd, with a Singularity worker image.

### Open-source release
- Local development needs only an LLM key: a Slurm emulator (`mock-slurm`), optional
  real local PySR (`LOCAL_PYSR=true`), and a dev login script.
- No deployment-specific values remain in code or defaults. The partition, container
  binds, Julia depot, nginx domain and server-keys role are all settings.
- Documentation (`docs/`), contributing guide, security policy, citation metadata, CI
  (backend tests, frontend build), and Dependabot.

### Known issues
- The frontend still uses Vite 4 and ESLint 8, and the `xlsx` package is the last npm
  release of SheetJS (0.18.5), which has published advisories. These upgrades are
  planned.
