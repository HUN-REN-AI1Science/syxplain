#!/bin/bash
# Create a separate schema and role for Keycloak tables.
# This keeps Keycloak data isolated from the application schema
# and follows the principle of least privilege.
#
# Runs only on fresh PostgreSQL init (empty pgdata volume).
# Uses KC_DB_PASSWORD env var if set, falls back to 'keycloak' for dev.

set -e

KC_PASS="${KC_DB_PASSWORD:-keycloak}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE SCHEMA IF NOT EXISTS keycloak;

    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'keycloak_user') THEN
            CREATE USER keycloak_user WITH PASSWORD '${KC_PASS}';
        END IF;
    END
    \$\$;

    GRANT ALL ON SCHEMA keycloak TO keycloak_user;
    ALTER DEFAULT PRIVILEGES IN SCHEMA keycloak GRANT ALL ON TABLES TO keycloak_user;
EOSQL
