#!/usr/bin/env bash
# Create a technical (machine-to-machine) client in Keycloak and a Syxplain API key for it.
#
# The client gets a service account that holds the server-key role, so everything it
# starts runs on the server's LLM keys. It can authenticate in two ways:
#   - a Keycloak access token from the client-credentials grant (Authorization: Bearer),
#     for programs that can request and renew tokens;
#   - the Syxplain API key printed at the end (X-API-Key), for tools that can only send
#     a fixed header, such as an MCP server entry in LibreChat.
#
# Usage: ./dev/create-technical-client.sh <client-id> [backend-url] [keycloak-url]
#   client-id     e.g. adp-librechat
#   backend-url   where the backend is reachable from this machine
#                 (default http://localhost:8000)
#   keycloak-url  Keycloak base URL reachable from this machine; in production the
#                 public one, https://<domain>/keycloak, so the token's issuer matches
#                 KEYCLOAK_ISSUER (default http://localhost:8080/keycloak)
#
# Environment: KEYCLOAK_CONTAINER (default syxplain-keycloak), KEYCLOAK_ADMIN_USERNAME,
# KEYCLOAK_ADMIN_PASSWORD, SERVER_KEYS_ROLE (default server-llm-access).
# Safe to run again: an existing client is reused and its API key is replaced.
#
# If the backend restricts clients (KEYCLOAK_ALLOWED_CLIENTS), add the client id there
# and restart the backend before running this script.
set -euo pipefail

CLIENT_ID="${1:?Usage: $0 <client-id> [backend-url] [keycloak-url]}"
BACKEND_URL="${2:-http://localhost:8000}"
KEYCLOAK_URL="${3:-http://localhost:8080/keycloak}"
CONTAINER="${KEYCLOAK_CONTAINER:-syxplain-keycloak}"
ADMIN_USER="${KEYCLOAK_ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
ROLE="${SERVER_KEYS_ROLE:-server-llm-access}"
REALM="syxplain"

kcadm() { docker exec "$CONTAINER" /opt/keycloak/bin/kcadm.sh "$@"; }
json_field() { python3 -c "import json,sys; print(json.load(sys.stdin).get('$1') or '')"; }
client_uuid() {
    kcadm get clients -r "$REALM" -q "clientId=$CLIENT_ID" --fields id --format csv --noquotes | head -n1
}

echo "Logging in to Keycloak in container '$CONTAINER'..."
kcadm config credentials --server http://localhost:8080/keycloak --realm master \
    --user "$ADMIN_USER" --password "$ADMIN_PASSWORD" >/dev/null

UUID="$(client_uuid)"
if [ -z "$UUID" ]; then
    kcadm create clients -r "$REALM" \
        -s "clientId=$CLIENT_ID" \
        -s "description=Technical access to Syxplain (API and MCP)" \
        -s enabled=true -s publicClient=false -s serviceAccountsEnabled=true \
        -s standardFlowEnabled=false -s implicitFlowEnabled=false \
        -s directAccessGrantsEnabled=false >/dev/null
    UUID="$(client_uuid)"
    echo "Created client $CLIENT_ID"
else
    echo "Client $CLIENT_ID already exists; reusing it"
fi

kcadm add-roles -r "$REALM" --uusername "service-account-$CLIENT_ID" --rolename "$ROLE" >/dev/null
SECRET="$(kcadm get "clients/$UUID/client-secret" -r "$REALM" | json_field value)"

TOKEN="$(curl -fsS -X POST "$KEYCLOAK_URL/realms/$REALM/protocol/openid-connect/token" \
    -d grant_type=client_credentials -d "client_id=$CLIENT_ID" \
    --data-urlencode "client_secret=$SECRET" | json_field access_token)"
if [ -z "$TOKEN" ]; then
    echo "Could not get a token for $CLIENT_ID from $KEYCLOAK_URL." >&2
    exit 1
fi

# One active key per account: replace an existing one
AUTH=(-H "Authorization: Bearer $TOKEN")
if curl -fsS "${AUTH[@]}" "$BACKEND_URL/api/api-keys" | grep -q '"key_prefix"'; then
    API_KEY="$(curl -fsS -X POST "${AUTH[@]}" "$BACKEND_URL/api/api-keys/regenerate" | json_field key)"
else
    API_KEY="$(curl -fsS -X POST "${AUTH[@]}" "$BACKEND_URL/api/api-keys" | json_field key)"
fi
if [ -z "$API_KEY" ]; then
    echo "The backend at $BACKEND_URL did not issue an API key." >&2
    exit 1
fi

echo
echo "Technical client ready."
echo
echo "  Keycloak client id:      $CLIENT_ID"
echo "  Keycloak client secret:  $SECRET"
echo "  Syxplain API key:        $API_KEY"
echo
echo "The secret and the key are shown here only; store them in a secret manager."
echo "See docs/mcp.md for the LibreChat configuration."
