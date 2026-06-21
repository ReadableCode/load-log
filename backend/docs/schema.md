# Database Schema

Database: `apps` · schema: `load_log`

Tables live in the `load_log` schema and are created/evolved via Alembic
migrations (`backend/alembic/versions/`). The DDL below is the canonical shape.

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

**Crash safety:** each set is inserted as its own request/transaction, so a
TUI/web crash mid-workout never loses already-logged sets.

**Migrations, not bootstrap.** Schema changes go through Alembic
(`backend/alembic/versions/`). Migrations are non-destructive by default (no
`DROP`/`ALTER COLUMN`/unfiltered `DELETE` without explicit review). The baseline
`0001` uses `CREATE ... IF NOT EXISTS` (a no-op on the populated prod DB; builds
a fresh dev DB). Take a backup first with the read-only
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
