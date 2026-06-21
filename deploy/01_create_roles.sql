-- 01_create_roles.sql — one-time PostgREST role setup (cluster-global roles).
-- Run ONCE on the EliteDesk Postgres. Roles are cluster-wide; you can run this
-- connected to any database. Safe to re-run: guarded with DO blocks.
--
--   docker exec -i postgres psql -U "$POSTGRES_USER" -d postgres < 01_create_roles.sql
--
-- IMPORTANT: replace CHANGE_ME_POSTGREST_DB_PASSWORD below with the SAME value
-- you put in POSTGREST_DB_PASSWORD in the .env that docker_compose_projects.yaml
-- uses. The two must match or PostgREST cannot connect.

-- Connection role PostgREST logs in as.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgrest_authenticator') THEN
    CREATE ROLE postgrest_authenticator WITH LOGIN PASSWORD 'CHANGE_ME_POSTGREST_DB_PASSWORD' NOINHERIT;
  END IF;
END
$$;

-- Anonymous role for unauthenticated requests (gets nothing by default).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'web_anon') THEN
    CREATE ROLE web_anon NOLOGIN;
  END IF;
END
$$;

-- App role that authenticated load-log users map to (the JWT 'role' claim).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'load_log_user') THEN
    CREATE ROLE load_log_user NOLOGIN;
  END IF;
END
$$;

-- Let the authenticator switch into the app/anon roles.
GRANT web_anon       TO postgrest_authenticator;
GRANT load_log_user  TO postgrest_authenticator;
