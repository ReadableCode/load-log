# Database Schema

Database: `apps` · schema: `load_log`

Tables live in the `load_log` schema. `deploy/02_schema.sql` is the source of
truth for their shape, applied by `backend/src/bootstrap.py` at app startup. The
DDL below mirrors it.

---

## Habit Tracker

### `habits`

Defines a recurring daily goal (e.g., "10,000 steps", "60s plank").

```sql
CREATE TABLE IF NOT EXISTS habits (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    created_at  DATE NOT NULL DEFAULT CURRENT_DATE,
    sort_order  INTEGER  -- user-chosen display position (1..N); NULL sorts last
);
```

### `habit_completions`

One row per (habit, date) pair when the user marks it done.
Allows marking any date — past, today, or future.

```sql
CREATE TABLE IF NOT EXISTS habit_completions (
    id              SERIAL PRIMARY KEY,
    habit_id        INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
    completed_date  DATE NOT NULL,
    UNIQUE (habit_id, completed_date)
);
```

**Key queries:**
- All completions for a habit in the last N days → completion heatmap
- Toggle (upsert / delete) a completion for a specific (habit_id, date)
- Count of completions per habit in the last 7 / 30 / 365 days

---

## Credentials

### `users`

Read only at login, by the postgrest-auth library over the app's superuser
connection. `deploy/03_secure_users.sql` revokes this table from `load_log_user`
and `web_anon`, so there is no PostgREST path to a password hash.

```sql
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
```

This is the fleet-standard shape — every app that logs in through
postgrest-auth has it.
`role` and `disabled` are read at login; `password_changed_at` is what lets a
password change or a disable revoke live sessions without a server-side session
store (tokens issued before it are rejected).

`password_hash` is an opaque string, never parsed or re-encoded. Algorithms are
self-identifying by prefix (`$2b$` bcrypt, `$argon2id$` argon2id) — the library
verifies both and rehashes bcrypt rows to argon2id on the next successful login.

Two notes on the live table specifically. Its `created_at` is nullable, because
the original migration omitted `NOT NULL`; correcting that needs an
`ALTER COLUMN`, which is deliberately kept out of a boot-time path, and the
column always has a value in practice. And load-log does not compare a token's
`iat` against `password_changed_at` — it signs the JWT at login but never
decodes it afterwards, relying on PostgREST's `exp` check. That is acceptable while load-log is single-user with
RLS deferred; revisit if either changes.

---

## Workout Tracker

### `exercises`

Canonical list of exercise names, created on first use.

```sql
CREATE TABLE IF NOT EXISTS exercises (
    id    SERIAL PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE
);
```

### `workout_sets`

There is **no separate workout/session table** — a "workout" is just the set of
`workout_sets` rows that share a `workout_date`. This keeps the model simple
(one date picker, no session naming, no notes) and makes per-day volume queries
trivial. `set_number` is 1-indexed within (`workout_date`, `exercise_id`).

```sql
CREATE TABLE IF NOT EXISTS workout_sets (
    id            SERIAL PRIMARY KEY,
    workout_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    exercise_id   INTEGER NOT NULL REFERENCES exercises(id),
    set_number    INTEGER NOT NULL,
    reps          INTEGER NOT NULL,
    weight_lbs    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS workout_sets_date_idx ON workout_sets (workout_date);
```

**Key queries:**

- All sets for a given date → display the day's log
- `SELECT workout_date, SUM(reps * weight_lbs) GROUP BY workout_date` → volume
  heatmap (GitHub-style, color-graded by total daily volume)
- Most-recent prior date containing a given exercise → progressive-overload
  reference for "what to beat"
- Per-exercise max weight over time → strength trend chart

**Crash safety:** each set is inserted as its own request/transaction, so a
TUI/web crash mid-workout never loses already-logged sets.

**App-owned bootstrap.** Schema changes go in `deploy/02_schema.sql` (or a new
numbered file added to `SCHEMA_FILES`), with a `SCHEMA_VERSION` bump, applied by
`backend/src/bootstrap.py` at startup. The SQL is additive and idempotent by
construction: `CREATE ... IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS`, never
`DROP`, `TRUNCATE`, `ALTER COLUMN`, or an unfiltered `DELETE`. A destructive
change needs a reviewed, separate file — a boot must not be able to do one by
surprise. Take a backup first with the read-only
`backend/scripts/backup_to_files.py` (CSV/Parquet) before any risky change.

---

## Progressive Overload Logic (in `api_client.py`)

Not a DB concept — computed from the data:

1. When the user picks an exercise on a given `workout_date`, query the **most
   recent prior `workout_date`** that included that exercise.
2. Display that day's sets (reps × weight) as the "last time" reference.
3. After sets are logged, derive a **suggested next weight**:
   - All current reps ≥ previous reps → `prev_max_weight + 5 lbs`
   - Any current reps < previous reps → hold at `prev_max_weight`
   - No previous history → `None` (build a baseline)
4. Nothing extra is stored — the suggestion always recomputes from history.
