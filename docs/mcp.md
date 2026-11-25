# MCP server and technical access

Syxplain serves a [Model Context Protocol](https://modelcontextprotocol.io) endpoint at
`/mcp`, so a chat assistant (LibreChat, Claude, or any MCP client) can start an analysis
from a conversation and report its results. The endpoint is part of the backend; nothing
extra has to be deployed.

Every analysis started through MCP runs on the server's LLM keys. The tools take no LLM
settings, and the endpoint refuses accounts without server-key access.

## Tools

| Tool | Purpose |
|---|---|
| `start_analysis` | Start an analysis of a table passed as CSV text, with the project description, the target column and a description of each predictor. Optional `literature_text`: the user's own literature, read in addition to the web literature research (`web_literature: false` turns the web research off, only together with `literature_text`). The recommendation is chosen among the equations coherent with the context and the literature (see [api.md](api.md#context-and-literature)). Returns a `run_id` at once |
| `get_analysis_status` | Status, progress and pipeline phase of a run |
| `get_analysis_results` | The outcome in compact form: headline equation and shortlist with holdout and cross-validation scores, data split, derived time-series features, the agent's conclusions, comparison with published laws, explanation, warnings, LLM cost |
| `list_analyses` | The account's most recent runs |
| `cancel_analysis` | Stop a pending or running run |

An analysis typically takes 10 to 30 minutes, so no tool waits for it. The server's
instructions tell the assistant to start the run, tell the user how long it takes, and
check back instead of polling in a loop.

The data travels through the chat model's context, so `start_analysis` accepts CSV text
up to `MCP_MAX_CSV_KB` (default 256 kB). Larger files go through the web app or the
[programmatic API](api.md). Runs started through MCP are ordinary runs of the account:
they also appear in the web app and under `/api/v1/runs`.

## Authentication

The endpoint accepts the same credentials as the API:

- a Syxplain API key in `X-API-Key` (or as `Authorization: Bearer syxp_...` for clients
  that can only set an Authorization header);
- a Keycloak access token as `Authorization: Bearer <token>`.

Requests without a valid credential get `401`; accounts without server-key access get
`403`. Requests are limited to 200 per minute per credential and 5 started analyses per
minute per account, and the account's limit of active runs (`MAX_ACTIVE_RUNS_PER_USER`)
applies.

## Technical account

A chat platform connects as one technical account: a Keycloak client with a service
account that holds the server-key role. Its users need no Syxplain account, and all their
runs belong to the technical account.

`dev/create-technical-client.sh` creates the client and an API key for it:

```bash
# development
./dev/create-technical-client.sh adp-librechat

# production, on the server (admin credentials from the deployment's .env)
KEYCLOAK_ADMIN_USERNAME=... KEYCLOAK_ADMIN_PASSWORD=... \
  ./dev/create-technical-client.sh adp-librechat \
  http://localhost:8000 https://<domain>/keycloak
```

It prints the client secret and the API key once. The script

1. creates a confidential client with the service account enabled and every browser flow
   disabled;
2. gives its service account the `server-llm-access` role (or your `SERVER_KEYS_ROLE`);
3. requests a client-credentials token and uses it to create the account's API key.

The API key exists because a Keycloak access token lasts five minutes, and an MCP client
configured with a fixed header cannot renew it. Programs that can renew tokens use the
client id and secret directly (see [API authentication](api.md#authentication)).

To revoke access, delete the client in Keycloak or remove the role from its service
account. No new tokens are issued, and the API key follows within five minutes, when its
roles are next checked against Keycloak. Running the script again replaces the API key
immediately.

In production, set `KEYCLOAK_ALLOWED_CLIENTS` to the clients the backend should accept,
for example `syxplain-frontend,adp-librechat`. Tokens issued to any other client of the
realm are then rejected. Add a new client to the list, and restart the backend, before
running the script for it.

One technical account serves everyone on the platform, so consider raising
`MAX_ACTIVE_RUNS_PER_USER` for the deployment: it is the only limit on how many analyses
(and how much LLM cost) the platform can have in flight.

## LibreChat

Add the server to `librechat.yaml` and put the API key in LibreChat's environment
(`SYXPLAIN_API_KEY`):

```yaml
mcpServers:
  syxplain:
    type: streamable-http
    url: https://<domain>/mcp
    requiresOAuth: false          # fixed-header authentication, skip OAuth detection
    serverInstructions: true      # pass the server's usage instructions to the model
    timeout: 60000
    headers:
      X-API-Key: "${SYXPLAIN_API_KEY}"
      X-End-User: "{{LIBRECHAT_USER_EMAIL}}"
```

`X-End-User` is optional. Syxplain does not use it for access control; it is written to
the backend log next to each started run, so that runs of the shared account can be
traced to a person. Leave it out if that is not wanted.

## Trying it

With the [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector
# Transport: Streamable HTTP, URL: http://localhost:8000/mcp
# Header: X-API-Key = syxp_...
```

Or directly:

```bash
curl -s http://localhost:8000/mcp \
  -H "X-API-Key: $SYXPLAIN_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```
