-- 02_schema.sql — the load_log schema. Applied by backend/src/bootstrap.py at
-- app startup, version-gated on load_log.deploy_meta (I6).
--
-- Idempotent and additive only (I7): CREATE ... IF NOT EXISTS and
-- ADD COLUMN IF NOT EXISTS. Never DROP, TRUNCATE, or ALTER COLUMN — a
-- destructive change is a new numbered file plus a SCHEMA_VERSION bump.
--
-- Two audiences, and they need different statements:
--
--   * A fresh database (the local dev stack, a clone) — built entirely by the
--     CREATE TABLE blocks below.
--   * The live elitedesk database — every table here already exists, created by
--     Alembic revisions 0001-0003 before this file replaced them. Every CREATE
--     is skipped there, and only the users ADD COLUMN statements do anything.
--
-- This file reproduces the live schema as of Alembic 0003 (verified against
-- information_schema on 2026-08-28), plus the four users columns the shared
-- postgrest-auth service reads. That combination is SCHEMA_VERSION 1.

CREATE SCHEMA IF NOT EXISTS load_log;

-- ---------------------------------------------------------------------------
-- Habits
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS load_log.habits (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    created_at DATE NOT NULL DEFAULT CURRENT_DATE,
    -- Nullable on purpose: clients order with nullslast and assign positions on
    -- insert/reorder, so NULL means "not yet reordered, sort last".
    sort_order INTEGER
);

CREATE TABLE IF NOT EXISTS load_log.habit_completions (
    id             SERIAL PRIMARY KEY,
    habit_id       INTEGER NOT NULL REFERENCES load_log.habits (id) ON DELETE CASCADE,
    completed_date DATE NOT NULL,
    UNIQUE (habit_id, completed_date)
);

-- ---------------------------------------------------------------------------
-- Workouts
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS load_log.exercises (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS load_log.workout_sets (
    id           SERIAL PRIMARY KEY,
    workout_date DATE NOT NULL DEFAULT CURRENT_DATE,
    exercise_id  INTEGER NOT NULL REFERENCES load_log.exercises (id),
    set_number   INTEGER NOT NULL,
    reps         INTEGER NOT NULL,
    weight_lbs   REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS workout_sets_date_idx
    ON load_log.workout_sets (workout_date);

-- ---------------------------------------------------------------------------
-- Credentials
-- ---------------------------------------------------------------------------
-- Read ONLY by the shared postgrest-auth service over its own superuser
-- connection. 03_secure_users.sql revokes this table from every PostgREST-facing
-- role, so there is no HTTP path to a password hash (I4).
--
-- password_hash is an opaque string. Nothing here parses or re-encodes it —
-- algorithms are self-identifying by prefix ($2b$ bcrypt, $argon2id$ argon2id)
-- and the auth service rehashes bcrypt rows to argon2id on the next successful
-- login.

CREATE TABLE IF NOT EXISTS load_log.users (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username            text UNIQUE NOT NULL,
    password_hash       text NOT NULL,
    role                text NOT NULL DEFAULT 'user',
    display_name        text NOT NULL DEFAULT '',
    disabled            boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),
    password_changed_at timestamptz NOT NULL DEFAULT now()
);

-- The live table predates the four columns above (Alembic 0002 created only id,
-- username, password_hash, created_at), and CREATE TABLE IF NOT EXISTS skips an
-- existing table wholesale rather than reconciling its columns. These ALTERs are
-- what actually converges production; on a fresh database they are no-ops.
--
-- The shared auth service selects role and disabled at login, and apps that
-- validate sessions compare the token's iat against password_changed_at.
ALTER TABLE load_log.users ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'user';
ALTER TABLE load_log.users ADD COLUMN IF NOT EXISTS display_name text NOT NULL DEFAULT '';
ALTER TABLE load_log.users ADD COLUMN IF NOT EXISTS disabled boolean NOT NULL DEFAULT false;
ALTER TABLE load_log.users ADD COLUMN IF NOT EXISTS password_changed_at timestamptz NOT NULL DEFAULT now();

-- Known drift, deliberately not fixed here: production's users.created_at is
-- nullable (Alembic 0002 wrote `timestamptz DEFAULT now()` without NOT NULL),
-- while the CREATE TABLE above gives a fresh database NOT NULL to match the
-- fleet-canonical shape. Correcting production needs ALTER COLUMN SET NOT NULL,
-- which I7 keeps out of a boot-time path. The column always has a value in
-- practice, so this is cosmetic.

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------
-- Data tables only. load_log.users is deliberately absent and is revoked
-- explicitly in 03_secure_users.sql.

GRANT USAGE ON SCHEMA load_log TO load_log_user;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    load_log.habits,
    load_log.habit_completions,
    load_log.exercises,
    load_log.workout_sets
  TO load_log_user;

GRANT USAGE, SELECT ON
    load_log.habits_id_seq,
    load_log.habit_completions_id_seq,
    load_log.exercises_id_seq,
    load_log.workout_sets_id_seq
  TO load_log_user;
