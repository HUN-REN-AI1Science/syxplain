#!/usr/bin/env bash
# Create a verified login for local development (the dev realm has no mail server, so
# self-registered users would get stuck at email verification).
#
# Usage: ./dev/create-dev-user.sh [email] [password]
# Defaults: dev@example.com / Dev-password-1 (the realm requires a digit and a
# special character). The user gets the syxplain-admin role, which also allows running
# analyses on the server's LLM keys (OPENAI_API_KEY in .env).
set -euo pipefail

EMAIL="${1:-dev@example.com}"
PASSWORD="${2:-Dev-password-1}"
CONTAINER="${KEYCLOAK_CONTAINER:-syxplain-keycloak}"
ADMIN_USER="${KEYCLOAK_ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
REALM="syxplain"

kcadm() { docker exec "$CONTAINER" /opt/keycloak/bin/kcadm.sh "$@"; }

echo "Logging in to Keycloak in container '$CONTAINER'..."
kcadm config credentials --server http://localhost:8080/keycloak --realm master \
    --user "$ADMIN_USER" --password "$ADMIN_PASSWORD" >/dev/null

USER_ID="$(kcadm get users -r "$REALM" -q "email=$EMAIL" -q exact=true --fields id --format csv --noquotes | head -n1)"
if [ -z "$USER_ID" ]; then
    kcadm create users -r "$REALM" -s "username=$EMAIL" -s "email=$EMAIL" \
        -s enabled=true -s emailVerified=true -s firstName=Dev -s lastName=User >/dev/null
    echo "Created user $EMAIL"
else
    kcadm update "users/$USER_ID" -r "$REALM" -s enabled=true -s emailVerified=true >/dev/null
    echo "User $EMAIL already exists; marked as verified"
fi

kcadm set-password -r "$REALM" --username "$EMAIL" --new-password "$PASSWORD" >/dev/null
kcadm add-roles -r "$REALM" --uusername "$EMAIL" --rolename syxplain-admin >/dev/null

echo
echo "Log in at http://localhost:5173 with:"
echo "  email:    $EMAIL"
echo "  password: $PASSWORD"
