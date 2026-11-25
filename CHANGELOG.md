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
- Coherence-first selection. Every fitted equation is tested by code against statements
  about the target, and the recommended equation is chosen among the equations without a
  conflict. The best-scoring equation overall is kept beside it as the challenger, with
  the gap between the two in standard errors (`discovery.selection.coherence_first`,
  `literature_conflicts` per equation, a coherence check for the context and the
  literature). The statements come from three sources:
  - the scientific context: an LLM reads the realistic limits of the target from its
    meaning and unit (`discovery.context`), and an equation that leaves them inside the
    range of the data conflicts;
  - the web literature research, whose statements carry their validity for the data
    (`yes`, `unknown`, `no`). `unknown` decides only between equally good equations;
  - supplied literature: `literature_text` on `POST /api/v1/analyze`, the MCP
    `start_analysis` tool and the problem description. `web_literature: false` turns the
    web research off when a text is given; one kind of literature research is always used.
- Relationships of the literature among the other variables are measured on the data, as
  published and with refitted constants (`discovery.literature.relations`), and a law for
  the target implied by a holding relationship is fitted.
- When the challenger breaks a "not a cause" statement, the coherence check reports
  whether the data speak against the literature or the better score is more likely a
  wrong relationship.
- Time series: the earlier values offered as features come from the orders of an
  automatic ARIMA fit (`pmdarima`): earlier values of the target and earlier errors of
  that fit. `DISCOVERY_SERIES_FEATURES` selects `orders` (default), `llm` or `both`.
- Web application: a field for your own literature on the Define Problem step, with a
  switch for the web literature research; the results show the statements, the
  relationships and the coherence-first selection reason.

### Changed
- A long series no longer has to be evenly spaced: the step is the typical distance
  between measurements, and an earlier value is read between the two measurements around
  that moment.
- The example datasets in `data/` are the four use cases of the paper: soil phosphorus,
  two problems on a synthetic coating line with supplied literature, and a river water
  temperature series. The perovskite, connectome and grassland examples were removed.
- Keycloak 26.8.2.
- An account can have 3 pending or running analyses at a time by default
  (`MAX_ACTIVE_RUNS_PER_USER`; `0` removes the limit).
- `/api/v1` and `/mcp` are rate-limited per credential instead of per client address.
- `POST /api/v1/analyze` checks the columns and the cluster before storing the file.
- ID and refresh tokens no longer authenticate API calls.
- API-key roles are re-checked against Keycloak every five minutes, also for keys in
  constant use.
- Requires `mcp` 2.3 or later, and `pmdarima` and `statsmodels`.

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
