-- 02_migrate_schema.sql — move load-log tables from `public` into the `load_log`
-- schema (inside the load_log database) and grant the app role access.
--
-- Run AFTER 01_create_roles.sql, connected to the load_log database:
--
--   docker exec -i postgres psql -U "$POSTGRES_USER" -d load_log < 02_migrate_schema.sql
--
-- This is reversible-ish: ALTER TABLE ... SET SCHEMA just relocates the table,
-- it does not touch the rows. A verified CSV/Parquet backup already exists under
-- load-log/data/backup_*/ before you run this.

CREATE SCHEMA IF NOT EXISTS load_log;

-- Move each existing load-log table into the load_log schema. IF EXISTS guards
-- make this safe to re-run after a partial application.
ALTER TABLE IF EXISTS public.habits             SET SCHEMA load_log;
ALTER TABLE IF EXISTS public.habit_completions  SET SCHEMA load_log;
ALTER TABLE IF EXISTS public.exercises          SET SCHEMA load_log;
ALTER TABLE IF EXISTS public.workout_sets       SET SCHEMA load_log;

-- CRITICAL: make unqualified table references resolve to load_log first. The
-- TUI/db.py still issue unqualified `CREATE TABLE IF NOT EXISTS` + queries; without
-- this they would recreate empty tables in `public` and silently diverge from the
-- real data now living in load_log. Scoped to the load_log database only.
ALTER DATABASE load_log SET search_path = load_log, public;

-- Grant the app role access to the DATA tables only (NOT the future users table,
-- which holds password hashes and must never be exposed through PostgREST).
GRANT USAGE ON SCHEMA load_log TO load_log_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    load_log.habits,
    load_log.habit_completions,
    load_log.exercises,
    load_log.workout_sets
  TO load_log_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA load_log TO load_log_user;

-- Verify the move: these counts must match load-log/data/backup_*/manifest.json
--   habits=3  habit_completions=22  exercises=1  workout_sets=31
SELECT 'habits' AS tbl, count(*) FROM load_log.habits
UNION ALL SELECT 'habit_completions', count(*) FROM load_log.habit_completions
UNION ALL SELECT 'exercises', count(*) FROM load_log.exercises
UNION ALL SELECT 'workout_sets', count(*) FROM load_log.workout_sets;
