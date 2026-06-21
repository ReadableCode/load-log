-- dev_init.sql — runs automatically on FIRST init of the local dev Postgres
-- (mounted into /docker-entrypoint-initdb.d by docker-compose.dev.yml).
-- Creates the PostgREST roles + schema so the local stack mirrors prod. This is
-- DEV ONLY — passwords are throwaway localdev values.

CREATE ROLE postgrest_authenticator WITH LOGIN PASSWORD 'localdev' NOINHERIT;
CREATE ROLE web_anon NOLOGIN;
CREATE ROLE load_log_user NOLOGIN;
GRANT web_anon      TO postgrest_authenticator;
GRANT load_log_user TO postgrest_authenticator;

CREATE SCHEMA IF NOT EXISTS load_log;
ALTER DATABASE apps SET search_path = load_log, public;

GRANT USAGE ON SCHEMA load_log TO load_log_user;
-- Dev convenience: auto-grant the app role on tables Alembic creates later.
ALTER DEFAULT PRIVILEGES IN SCHEMA load_log GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO load_log_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA load_log GRANT USAGE, SELECT ON SEQUENCES TO load_log_user;
