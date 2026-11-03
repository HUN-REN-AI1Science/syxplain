# Programmatic API

The `/api/v1` endpoints run analyses from scripts and pipelines. The backend serves
interactive documentation, with every field and response schema, at `/docs` (for
example, `http://localhost:8000/docs` in development).

## Authentication

Create an API key in the web app under **Profile → API Keys**. Each user has one key;
regenerating it revokes the old one. Send it in the `X-API-Key` header:

```bash
export SYXPLAIN_API_KEY=syxp_...
curl -H "X-API-Key: $SYXPLAIN_API_KEY" http://localhost:8000/api/v1/models
```

Runs started through the API belong to the key's user and appear in the web app too.

## Endpoints

| Method and path | Purpose | Rate limit |
|---|---|---|
| `POST /api/v1/analyze` | Upload a data file and start an analysis (returns `202` with a `run_id`) | 5/min |
| `GET /api/v1/runs/{run_id}` | Status and progress; results and artifacts once completed | 60/min |
| `GET /api/v1/runs` | Your runs, paginated (`page`, `page_size`, `sort_order`, `status`) | 30/min |
| `POST /api/v1/runs/{run_id}/cancel` | Cancel a pending or running run | 10/min |
| `GET /api/v1/runs/{run_id}/artifacts/{filename}` | Download a plot or file produced by the run | 60/min |
| `GET /api/v1/models` | Models available for your own LLM key | 30/min |

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

Users without server-key access add their own LLM settings to `params`:

| Field | Description |
|---|---|
| `provider` | `"gemini"` (default) or `"openai_compatible"` (OpenAI, OpenRouter, vLLM, LiteLLM, ...) |
| `api_key` | Key for that provider |
| `model` | Model name (Gemini default: `gemini-3.1-pro-preview`; required for OpenAI-compatible) |
| `api_base` | Base URL for OpenAI-compatible providers (default `https://api.openai.com/v1`) |
| `openai_api_key` | OpenAI key for the literature search. Without it there is no literature step, unless `api_key` is itself an OpenAI key on the default endpoint |

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "X-API-Key: $SYXPLAIN_API_KEY" \
  -F "file=@data/example_1/sample_data.csv" \
  -F "params=$(cat data/example_1/problem_description.json)"
# {"run_id": "…", "status": "pending", "status_url": "/api/v1/runs/…", "cancel_url": "…"}
```

## Polling for results

A run moves from `pending` to `running`, and ends as `completed`, `failed`, `timeout` or
`cancelled`. Poll `GET /api/v1/runs/{run_id}` until it reaches one of these terminal
states. A completed run includes:
- `results`: the full analysis output, i.e. equations, model selection, known-law
  relations, coherence, explanation and LLM cost usage
- `artifacts`: download URLs for the generated plots

## Example client

[`examples/api_client.py`](../examples/api_client.py) submits an example folder, polls
until the run ends, and saves the results and every artifact:

```bash
python examples/api_client.py data/example_1 --base-url http://localhost:8000
```
