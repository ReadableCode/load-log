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

### `workout_sessions`

One session = one visit to the gym (or one workout block). A session can contain many exercises.

```sql
CREATE TABLE IF NOT EXISTS workout_sessions (
    id            SERIAL PRIMARY KEY,
    session_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    notes         TEXT
);
```

### `workout_sets`

Each row is one set within a session for a specific exercise.
`set_number` is 1-indexed and represents the order within that exercise within that session.

```sql
CREATE TABLE IF NOT EXISTS workout_sets (
    id           SERIAL PRIMARY KEY,
    session_id   INTEGER NOT NULL REFERENCES workout_sessions(id) ON DELETE CASCADE,
    exercise_id  INTEGER NOT NULL REFERENCES exercises(id),
    set_number   INTEGER NOT NULL,
    reps         INTEGER NOT NULL,
    weight_lbs   REAL NOT NULL
);
```

**Key queries:**
- All sets for a given session → display current session log
- Last session containing a given exercise → progressive overload reference
- All sessions with sets for a given exercise over time → volume/strength trend chart
- Per-exercise max weight over time → strength progress

---

## Progressive Overload Logic (in `workouts.py`)

Not a DB concept — computed from the data:

1. When a user starts logging an exercise in a new session, query the **most recent previous session** that included that exercise.
2. Display that session's sets (reps × weight) as the "last time" reference.
3. After the session is saved, compute a **suggested next target**:
   - If all sets hit their rep target: `weight + 5 lbs` (upper body) or `weight + 10 lbs` (lower body — determined by a flag or name heuristic)
   - If any set missed reps: `same weight`
   - If multiple failures in a row: `weight × 0.90` (deload)
4. Store nothing extra — the suggestion is always derived from logged history.

The "rep target" per set is the reps logged in the previous session (i.e., try to match or beat it at the same or higher weight).
