-- 03_secure_users.sql — keep the credentials table unreachable through
-- PostgREST (I4). Applied by backend/src/bootstrap.py after 02_schema.sql.
--
-- The shared postgrest-auth service reads load_log.users directly as the
-- superuser to verify a login, so the PostgREST-facing roles need no grant on
-- it — and must not have one, including via an embedded resource.
--
-- Idempotent: REVOKE of a privilege that was never granted is a no-op.

REVOKE ALL ON load_log.users FROM load_log_user;
REVOKE ALL ON load_log.users FROM web_anon;

-- ----------------------------------------------------------------------------
-- Row Level Security (DEFERRED, and why): the data tables — habits,
-- habit_completions, exercises, workout_sets — have no user_id column, so there
-- is nothing to key a policy on. load-log is single-user (Jason) today and
-- load_log_user can see every row, which is the same thing as seeing its own.
--
-- When multi-user support arrives, add user_id to each table in a new numbered
-- deploy file, bump SCHEMA_VERSION, and add deploy/04_rls.sql modelled on
-- Solitaire_Associations/deploy/04_rls.sql — a load_log.jwt_user_id() function
-- plus an ENABLE ROW LEVEL SECURITY and a DROP POLICY IF EXISTS / CREATE POLICY
-- pair per table, with both USING and WITH CHECK. Omitting WITH CHECK leaves
-- users able to write rows they cannot read.
--
-- The auth service already puts user_id in the JWT, so the claim is ready.
-- ----------------------------------------------------------------------------
