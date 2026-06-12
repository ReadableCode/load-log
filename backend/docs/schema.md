# Database Schema

Database: `load_log`

All tables created idempotently in `db.py::ensure_tables()`.

---

## Habit Tracker

### `habits`

Defines a recurring daily goal (e.g., "10,000 steps", "60s plank").

```sql
CREATE TABLE IF NOT EXISTS habits (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    created_at  DATE NOT NULL DEFAULT CURRENT_DATE
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

**Crash safety:** every `INSERT` of a set commits its own transaction, so a
TUI/web crash mid-workout never loses already-logged sets.

**No destructive bootstrap.** `db.ensure_tables()` only `CREATE TABLE IF NOT
EXISTS`s. If it detects schema drift (e.g. the legacy `workout_sets.session_id`
column), it **raises and refuses to start** rather than silently dropping
tables. Run `backend/scripts/migrate_drop_sessions.py` to migrate explicitly;
that script backs `workout_sets` and `workout_sessions` up into timestamped
backup tables (`workout_sets_backup_YYYYMMDD_HHMMSS`) **before** rewriting
anything.

**Test isolation.** `tests/conftest.py` forces `POSTGRES_DB=load_log_test`
(override with `LOAD_LOG_TEST_DB`) before `config.py` reads the env. A
`pytest` run can never touch the production `load_log` DB. The test DB is
auto-created on first run, alongside `load_log`, on the same Postgres host.

---

## Progressive Overload Logic (in `workouts.py`)

Not a DB concept — computed from the data:

1. When the user picks an exercise on a given `workout_date`, query the **most
   recent prior `workout_date`** that included that exercise.
2. Display that day's sets (reps × weight) as the "last time" reference.
3. After sets are logged, derive a **suggested next weight**:
   - All current reps ≥ previous reps → `prev_max_weight + 5 lbs`
   - Any current reps < previous reps → hold at `prev_max_weight`
   - No previous history → `None` (build a baseline)
4. Nothing extra is stored — the suggestion always recomputes from history.
