-- Create a separate schema and role for Keycloak tables.
-- This keeps Keycloak data isolated from the application schema
-- and follows the principle of least privilege.
-- Note: This script runs only on fresh PostgreSQL init (empty pgdata volume).
-- For existing deployments, run manually:
--   docker exec syxplain-db psql -U syxplain -d syxplain -f /docker-entrypoint-initdb.d/init-keycloak-schema.sql
CREATE SCHEMA IF NOT EXISTS keycloak;

-- Create a dedicated role for Keycloak with limited access
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'keycloak_user') THEN
        CREATE USER keycloak_user WITH PASSWORD 'keycloak';
    END IF;
END
$$;

GRANT ALL ON SCHEMA keycloak TO keycloak_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA keycloak GRANT ALL ON TABLES TO keycloak_user;
