# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

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
