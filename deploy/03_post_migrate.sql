-- 03_post_migrate.sql — run AFTER the load-log-streamlit container has started
-- once and Alembic has created the load_log.users table (migration 0002).
--
--   docker exec -i postgres psql -U "$POSTGRES_USER" -d load_log < 03_post_migrate.sql
--
-- Purpose: make sure the credentials table is NEVER reachable through PostgREST.
-- The auth service reads it directly as the postgres superuser, so it does not
-- need (and must not have) any grant for the app/anon roles.

REVOKE ALL ON load_log.users FROM load_log_user, web_anon;

-- ----------------------------------------------------------------------------
-- Row Level Security (DEFERRED): the current tables (habits, habit_completions,
-- exercises, workout_sets) have NO user_id column, so per-user isolation is not
-- applicable yet. load-log is effectively single-user (Jason) today, and
-- load_log_user can see all rows — acceptable for now.
--
-- When you add multi-user support, add a `user_id` column via an Alembic
-- migration, then enable RLS per table, e.g.:
--
--   ALTER TABLE load_log.workout_sets ENABLE ROW LEVEL SECURITY;
--   CREATE POLICY user_isolation ON load_log.workout_sets
--     USING (user_id = (current_setting('request.jwt.claims', true)::json->>'user_id'));
--
-- The auth service already puts `user_id` in the JWT, so the claim is ready.
-- ----------------------------------------------------------------------------
