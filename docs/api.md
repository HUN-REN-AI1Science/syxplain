# Programmatic API

The `/api/v1` endpoints run analyses from scripts and pipelines. The backend serves
interactive documentation, with every field and response schema, at `/docs` (for
example, `http://localhost:8000/docs` in development).

Chat assistants reach the same analyses through the [MCP endpoint](mcp.md).

## Authentication

Every endpoint accepts either credential.

**API key.** Create one in the web app under **Profile → API Keys**. Each user has one
key; regenerating it revokes the old one. Send it in the `X-API-Key` header:

```bash
export SYXPLAIN_API_KEY=syxp_...
curl -H "X-API-Key: $SYXPLAIN_API_KEY" http://localhost:8000/api/v1/models
```

**Keycloak access token.** A technical client with a service account (see
[Technical account](mcp.md#technical-account)) requests a token with the
client-credentials grant and sends it as `Authorization: Bearer <token>`:

```bash
TOKEN=$(curl -s -X POST \
  "https://<domain>/keycloak/realms/syxplain/protocol/openid-connect/token" \
  -d grant_type=client_credentials -d client_id=<client-id> \
  --data-urlencode client_secret=<secret> | jq -r .access_token)
curl -H "Authorization: Bearer $TOKEN" https://<domain>/api/v1/models
```

Tokens last five minutes; request a new one when a call returns `401`. A client that can
only set the `Authorization` header may also send an API key as `Bearer syxp_...`.

Runs started through the API belong to the authenticated account and appear in the web
app too. `GET /api/v1/models` tells whether the account runs on the server's LLM keys
(`"server_keys": true`) or has to send its own.

## Endpoints

| Method and path | Purpose | Rate limit |
|---|---|---|
| `POST /api/v1/analyze` | Upload a data file and start an analysis (returns `202` with a `run_id`) | 5/min |
| `GET /api/v1/runs/{run_id}` | Status, progress and phase; the full results and the artifacts | 60/min |
| `GET /api/v1/runs/{run_id}/summary` | The outcome in compact form | 60/min |
| `GET /api/v1/runs` | Your runs, paginated (`page`, `page_size`, `sort_order`, `status`) | 30/min |
| `POST /api/v1/runs/{run_id}/cancel` | Cancel a pending or running run | 10/min |
| `GET /api/v1/runs/{run_id}/artifacts/{filename}` | Download a plot or file produced by the run | 60/min |
| `GET /api/v1/models` | Whether you run on server keys, and the models for your own key | 30/min |

Rate limits count per credential. An account can also have only
`MAX_ACTIVE_RUNS_PER_USER` (default 3) pending or running analyses at a time; a further
`POST /api/v1/analyze` returns `429` with `"error": "too_many_active_runs"`.

## Starting an analysis

`POST /api/v1/analyze` takes `multipart/form-data` with two fields:
- `file`: the data, as `.csv`, `.xlsx` or `.xls`
- `params`: a JSON string

```json
{
  "project_description": "Predict soil phosphorus availability from chemical properties",
  "target_variable": "al_p2o5",
  "features": {
    "ph_kcl": "Soil pH measured in KCl solution",
    "organic_matter": "Organic matter (%)"
  }
}
```

The project description and the feature descriptions (with units) are what the LLM steps
reason from, so they are worth writing carefully. The request has no other analysis
options: the search budgets are server settings, and the structure of the data is
detected.

Accounts without server-key access add their own LLM settings to `params`. Accounts with
it send none, and any they send are ignored.

| Field | Description |
|---|---|
| `provider` | `"gemini"` (default) or `"openai_compatible"` (OpenAI, OpenRouter, vLLM, LiteLLM, ...) |
| `api_key` | Key for that provider |
| `model` | Model name (Gemini default: `gemini-3.1-pro-preview`; required for OpenAI-compatible) |
| `api_base` | Base URL for OpenAI-compatible providers (default `https://api.openai.com/v1`) |
| `openai_api_key` | OpenAI key for the literature search. Without it there is no literature step, unless `api_key` is itself an OpenAI key on the default endpoint |

### Supplying your own literature

`literature_text` (optional, plain text, up to 60 000 characters) holds your own
literature on the problem: papers, notes, reports. When it is given:

- it is read by the main LLM, without a web search, in addition to the web literature
  research. `web_literature: false` turns the web research off; it is accepted only
  together with `literature_text`, because one kind of literature research is always used;
- every statement of the web literature research carries its `validity` for the context
  of your data: `yes` removes equations that break it, `unknown` decides only between
  equations that are equally good on the metric (within one standard error;
  `selection.coherence_first.unknown_validity`), `no` is only shown;
- equations of the literature among the other variables are measured against the data
  (`discovery.literature.relations`: as published and with constants fitted again), and a
  law for the target implied by a holding relationship is fitted too (`composed_from`);
- the exploration stays blind to it, as it is to every known law;
- besides equations for the target, the step returns what the text states about it:
  variables that are not causes, the region where an equation must be defined, the
  direction of an effect, the limit of a quantity;
- every fitted equation is tested against these statements by code;
- the recommended equation is chosen among the equations without a conflict
  (coherence first), by the usual cross-validation rule. The best-scoring equation
  overall is kept beside it as the challenger.

`discovery.selection.coherence_first` reports the outcome: `n_candidates`, `n_coherent`,
`challenger_model_id`, `gap_se` (how much better the challenger scores, in standard
errors) and `challenger_conflicts`. A small gap with a conflicting challenger points to a
wrong relationship; a large gap means the data and the literature disagree, and a
warning says so. If no discovered equation is coherent, a coherent law from the
literature is recommended (`headline_reason` `coherent_literature_law`); if there is none
either, the cross-validated error alone decides (`..._no_coherent_model`).

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "X-API-Key: $SYXPLAIN_API_KEY" \
  -F "file=@data/example_1/sample_data.csv" \
  -F "params=$(cat data/example_1/problem_description.json)"
# {"run_id": "…", "status": "pending", "status_url": "/api/v1/runs/…",
#  "cancel_url": "…", "summary_url": "…", "renamed_columns": {}}
```

**Column names.** Names that are not valid identifiers (spaces, dots, hyphens,
parentheses) are rewritten with underscores, because the equations use them as variable
names. `target_variable` and `features` may use the names as written in the file or the
rewritten ones; `renamed_columns` in the response maps one to the other, and the results
use the rewritten names.

**Time series.** Keep the time column in the file, and the column that identifies each
series when there are several. They need not be listed in `features`. When the data is
time-ordered, the holdout is the last part of each series instead of a random sample, and
an LLM step may add features of earlier periods (lags and period aggregates) before the
search.

The request is refused before anything is stored when the file cannot be parsed, a column
does not exist (`400`), the account is at its limit of active runs (`429`) or the
computing cluster is unreachable (`503`).

## Polling for results

A run moves from `pending` to `running`, and ends as `completed`, `failed`, `timeout` or
`cancelled`. A typical analysis takes 10 to 30 minutes. Poll `GET /api/v1/runs/{run_id}`
every 15 to 30 seconds until it reaches a terminal state. While it runs, `progress` is
the percentage and `phase` names the pipeline step (`discovery_agent`,
`relate_known_laws`, `llm_explanation`, ...). A run interrupted by a server restart ends
as `failed`.

`warnings` lists steps that were skipped or failed without failing the run, for example
`{"stage": "literature", "message": "..."}` when no literature search was possible. A
completed run can therefore still be missing its explanation or its literature
comparison; check `warnings` before relying on those sections.

### Results

`results` is complete when the run is `completed`. A running analysis already exposes
the interim results once the equation search has finished and the explanation is being
written.

| Key | Content |
|---|---|
| `best_equation` | The selected (headline) equation |
| `equations` | The shortlist. Each has `equation`, `model_id`, `origin` (`symbolic`, `classic: ...`, `literature: ...`, `custom: ...`), `complexity`, `n_params`, `holdout_r2`, `holdout_n`, `cv_r2`, `cv_rmse`, `cv_se`, `verdict`, `reasons`, `variables`, `is_headline`, `agent_recommended`, `agent_why` |
| `explanations` | The LLM's reading: one card per equation (`overview`, `term_explanations`, `citations`), `summary` (`key_drivers`, `findings`), `recommendation`, `coherence`. `{"error": ...}` when it could not be written |
| `discovery.split` | Rows uploaded, complete and dropped; train and holdout sizes; `metric_basis` (`holdout`, or `cv` for data too small to hold rows out); `order` (`random` or `chronological`) |
| `discovery.series` | Time series only, otherwise `null`: `time_column`, `group_column`, `n_series`, the derived `lag_features` with the reason for each, `feature_stage` |
| `discovery.selection` | Why the headline was chosen, and whether the agent's pick was overruled. With supplied literature also `coherence_first` (see above) |
| `discovery.leaderboard` | Every fitted model with its scores, and with supplied literature its `literature_conflicts` |
| `discovery.agent` | The agent's summary, insights, rejected forms and open questions |
| `discovery.literature` | Published laws found by the literature search and how each fits the data. With supplied literature, `source` is `supplied` and `constraints` lists the statements read from it |
| `discovery.relations` | How the headline relates to classic and published laws |
| `discovery.coherence` | Consistency checks of the headline (noise ceiling, holdout, SHAP, known laws) |
| `discovery.dynamics` | Rate laws (SINDy), for time-ordered data |
| `scatter_data` | Actual and predicted values for plotting |
| `warnings` | Same list as the top-level `warnings` |
| `usage` | LLM calls, tokens and cost per model, with `total_cost_usd` |

Holdout scores are computed once, on rows no model was fitted to. `cv_r2` and `cv_rmse`
are out-of-fold cross-validation scores on the training rows.

`artifacts` gives download URLs for `pysr_explanations.json`, the feature-versus-target
plots (`feature_0_vs_target.png`, ...) and the SHAP plots (`shap_summary.png`,
`shap_dependence_<feature>.png`).

### Summary

`GET /api/v1/runs/{run_id}/summary` returns the run state and a `summary` object that
keeps what is needed to judge the outcome and leaves out the plot data, the leaderboard
and the agent's activity log: `headline`, `equations`, `data` (the split), `series`,
`selection`, `agent`, `literature`, `known_laws`, `explanation`, `warnings` and
`llm_cost_usd`. It is typically a tenth of the size of `results` or less. `summary` is
`null` until results exist.

## Example client

[`examples/api_client.py`](../examples/api_client.py) submits an example folder, polls
until the run ends, prints the headline equation, and saves the results and every
artifact:

```bash
python examples/api_client.py data/example_1 --base-url http://localhost:8000
```

For a folder with several data files, name the one to analyse:

```bash
python examples/api_client.py data/example_3 --data-file Celegans_AggregatedData.csv
```
