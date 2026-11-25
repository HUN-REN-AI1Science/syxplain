# Contributing to Syxplain

Thanks for your interest! Bug reports, ideas, documentation fixes and code are all welcome.

- For questions and ideas, open an issue.
- For bugs, open an issue with steps to reproduce (the bug template asks for what we need).
- Never report security issues in public issues. See [SECURITY.md](SECURITY.md).
- For larger changes, open an issue first, so we can agree on the approach before you
  invest the time.

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

The quickest setup is the Docker stack in the [README](README.md#quick-start).
`./dev/create-dev-user.sh` gives you a login.

For running tests and tools outside Docker:

```bash
# Python 3.10 (the backend image's version); uv picks it from pyproject.toml
uv run --with-requirements requirements.txt pytest       # backend tests
uv run ruff check . && uv run ruff format --check .      # lint + format (ruff from uv.lock)

# Frontend (Node 24)
cd frontend && npm ci
npm run lint && npm run typecheck && npm run format:check
```

Install the git hooks once with `uv run pre-commit install`. They run ruff and prettier on
every commit.

The backend tests need no database, cluster, Keycloak or LLM key: LLM calls use DSPy's
`DummyLM`, and PySR searches use a fake launcher.

## Principles for the discovery pipeline

These keep the results trustworthy. Please keep them in mind when changing anything in
`backend/services/discovery/`:

1. Code decides, the LLM proposes and explains. Model selection, metrics, relations
   to known laws and the coherence verdict are computed with fixed rules. LLMs choose
   what to try and put results into words. They never override a computed check.
2. Exploration stays blind to known laws. The agent must not see the classic catalog
   or the literature while it searches. Known laws are fitted and compared only
   afterwards (`relate.py`), so the search is not steered towards textbook answers. The
   statements of the context and the literature take part only in the final selection
   (`literature_coherence.py`).
3. A general tool, not tuned to examples. Do not shape algorithms, thresholds or
   prompts around a particular example dataset. Validate a change on independent data
   (synthetic generators with neutral variable names, and real datasets the change was
   not developed on), and report the results in the pull request.
4. Every candidate is scored the same way. Agent formulas, PySR equations and known
   laws all go through `fitting.fit_model`.

## Code conventions

### Backend (Python 3.10, FastAPI)

- Routers live in `backend/api/routers/`, schemas in `backend/schemas/`, and business
  logic in `backend/services/`.
- New LLM capabilities:
  - Add a DSPy signature to `backend/infrastructure/llm/signatures.py`. Its docstring is
    the prompt.
  - Call it from a service with a model from `backend/infrastructure/llm/client.py`.
  - Token usage and cost inside a run are counted automatically.
- New settings go in `backend/core/config.py`. Also document them in `.env.example` and
  `docs/configuration.md`, and pass them through `docker-compose.prod.yml`.
- Ruff settings are in `pyproject.toml`. Line length is 100.

### Frontend (React + TypeScript)

- Use PrimeReact components (for example `Button`, not a raw `<button>`) and Tailwind
  for layout.
- Feature components go in `src/components/<Feature>/`, and shared ones in
  `src/components/common/`.
- Fetch data in pages or hooks, not in presentational components.
- Prettier settings are in `frontend/.prettierrc`.

### Compute worker (`slurm_worker/`)

- The worker runs on Python 3.11 in the Singularity image. PySR is pinned (`pysr==2.7.0`)
  because the backend relies on its equation format.
- Bump the version in `slurm_worker/__init__.py` when the worker changes, and see
  [docs/slurm.md](docs/slurm.md) for rebuilding the image.

## Pull requests

- Keep each pull request focused on one change, with a description of what and why.
- Add or update tests for behaviour changes.
- Update the docs (`README.md`, `docs/`, `.env.example`, the in-app help in
  `frontend/src/pages/HelpView.tsx`) when behaviour or settings change.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `chore:`, with an optional scope such as `fix(worker):`).
- CI must pass: backend lint and tests, frontend lint, types and build.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
