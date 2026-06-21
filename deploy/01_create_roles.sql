-- 01_create_roles.sql — one-time PostgREST role setup (cluster-global roles).
-- Safe to re-run (idempotent).
--
-- The PostgREST connection password is read from the POSTGREST_DB_PASSWORD
-- ENVIRONMENT VARIABLE at run time (via psql \getenv) and is NEVER written into
-- this committed file. Make that variable available to psql when you run it:
--
--   PW=$(grep -E '^POSTGREST_DB_PASSWORD=' /path/to/compose/.env | cut -d= -f2- | tr -d "\"'")
--   sudo docker exec -i -e POSTGREST_DB_PASSWORD="$PW" postgres \
--     psql -U postgres -d postgres -v ON_ERROR_STOP=1 < load-log/deploy/01_create_roles.sql
--
-- (\getenv requires psql 11+; the postgres:17 image is fine. Roles are
-- cluster-wide, so connecting to any database is OK.)

\getenv pgrest_pw POSTGREST_DB_PASSWORD
\if :{?pgrest_pw}
\else
  \echo '>>> POSTGREST_DB_PASSWORD is not set in the environment. Aborting.'
  \quit
\endif

-- Connection role PostgREST logs in as (password set from the env var below).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgrest_authenticator') THEN
    CREATE ROLE postgrest_authenticator WITH LOGIN NOINHERIT;
  END IF;
END
$$;

-- Set/refresh the password from the environment (kept out of this file).
ALTER ROLE postgrest_authenticator WITH PASSWORD :'pgrest_pw';

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
