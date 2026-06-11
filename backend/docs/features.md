# Feature Specs

---

## Feature 1: Daily Habit Tracker

### What it does

The user defines habits they want to do every day (e.g., "10,000 steps", "30 pushups"). For each habit, the app renders a GitHub-style contribution heatmap showing the last 52 weeks. The user can check off any day — past, today, or future — with a single click/keypress.

---

### `habits.py` — functions to implement

```python
def get_all_habits() -> list[dict]
    # Returns [{id, name, created_at}, ...]

def add_habit(name: str) -> dict
    # INSERT INTO habits. Returns the new row.

def delete_habit(habit_id: int) -> None
    # DELETE FROM habits WHERE id = habit_id (cascades to completions)

def get_completions(habit_id: int, days: int = 365) -> list[date]
    # Returns sorted list of completed dates in the last `days` days

def toggle_completion(habit_id: int, target_date: date) -> bool
    # If (habit_id, target_date) exists: DELETE it, return False
    # If not: INSERT it, return True

def get_completion_counts(days: int = 7) -> dict[int, int]
    # Returns {habit_id: count} for the last `days` days — for the summary view
```

---

### Web UI (`web/app.py` — Streamlit)

**Sidebar:** list of all habits with an "+ Add Habit" text input and submit button.

**Main area:** one expander per habit showing:
- Habit name + streak count (current consecutive days ending today)
- GitHub-style heatmap (52 weeks × 7 days grid)
  - Built with Altair: a rect mark where x=week_number, y=day_of_week, color=completed (bool)
  - Weeks run left→right (oldest to newest), days run top→bottom (Mon→Sun)
  - Color scale: completed = `#216e39` (GitHub dark green), empty = `#ebedf0` (GitHub light gray)
  - Future dates shown in a lighter shade of gray (`#f6f8fa`)
- A date picker to check/uncheck a specific day (defaults to today)

**Interaction:** clicking "Mark [date]" calls `toggle_completion(habit_id, date)` and `st.rerun()`.

---

### TUI (`tui/habits.py` — Textual)

Screen layout:
```
┌─ Habits ──────────────────────────────────────┐
│ [+] New habit: ________________________ [Add] │
├───────────────────────────────────────────────┤
│ ✓  10,000 steps          streak: 4d  [Toggle] │
│ ✗  30 pushups            streak: 0d  [Toggle] │
│ ✓  60s plank             streak: 12d [Toggle] │
└───────────────────────────────────────────────┘
```

- "Toggle" marks today as complete or removes it
- Selecting a habit and pressing `d` opens a date picker to mark a different day
- Pressing `delete` on a selected habit removes it (with confirmation)

---

## Feature 2: Workout Tracker

### What it does

The user logs a workout session set by set. They pick an exercise name (autocompleted from history), then enter sets one at a time: reps and weight. After each set they can add another or move to the next exercise. The app always shows the last time they did that exercise so they know what to beat. Session notes are optional. After saving, the app shows whether to go up in weight next time.

---

### `workouts.py` — functions to implement

```python
def get_all_exercises() -> list[dict]
    # Returns [{id, name}, ...] sorted by name

def get_or_create_exercise(name: str) -> dict
    # Case-insensitive lookup, INSERT if not found. Returns {id, name}.

def create_session(session_date: date = None, notes: str = "") -> dict
    # INSERT INTO workout_sessions. Returns {id, session_date, notes}.

def add_set(session_id: int, exercise_id: int, set_number: int, reps: int, weight_lbs: float) -> dict
    # INSERT INTO workout_sets. Returns the new row.

def get_session_sets(session_id: int) -> list[dict]
    # Returns [{exercise_name, set_number, reps, weight_lbs}, ...] for a session

def get_last_session_for_exercise(exercise_id: int, before_session_id: int = None) -> list[dict]
    # Returns the sets from the most recent session that included this exercise
    # (excluding before_session_id if provided, so current session doesn't reference itself)
    # Returns [{set_number, reps, weight_lbs}, ...]

def get_exercise_history(exercise_id: int, limit: int = 20) -> pd.DataFrame
    # Returns a DataFrame: [session_date, set_number, reps, weight_lbs]
    # Ordered by session_date ASC, set_number ASC

def suggest_next_weight(exercise_id: int, current_session_id: int) -> float | None
    # Compares current session vs previous session for this exercise
    # Returns suggested weight for next time, or None if insufficient history

def update_session_notes(session_id: int, notes: str) -> None
    # UPDATE workout_sessions SET notes = %s WHERE id = %s
```

**`suggest_next_weight` logic:**
```python
# Get previous session sets and current session sets for this exercise
# If current reps >= previous reps for every set: return max(weight_lbs) + 5
# Else if current reps < previous reps on any set: return same weight as previous
# If insufficient history (first time doing exercise): return None
```

---

### Web UI (`web/app.py` — Streamlit)

**Sidebar:** "New Session" button. List of recent sessions (last 10) as links.

**Active Session view:**
```
Session: 2026-06-11    [Notes: ___________________]

Exercise: [___________ ▼]  ← autocomplete from exercise history

Last time (2026-06-04):
  Set 1: 8 reps @ 135 lbs
  Set 2: 8 reps @ 135 lbs
  Set 3: 7 reps @ 135 lbs

Log a set:
  Reps: [___]   Weight (lbs): [_____]   [Add Set]

Logged this session:
  Set 1: 8 reps @ 140 lbs
  Set 2: 8 reps @ 140 lbs

[+ Add another exercise]   [Finish Session]
```

After "Finish Session": show progressive overload recommendation for each exercise logged.

**History view (per exercise):**
- Line chart: max weight per session over time
- Table: all sessions with sets

---

### TUI (`tui/workouts.py` — Textual)

Screen layout — active session:
```
┌─ Workout Session: 2026-06-11 ─────────────────┐
│ Exercise: bench press                          │
│ Last session (2026-06-04): 8×135, 8×135, 7×135│
├───────────────────────────────────────────────┤
│ Set 1: 8 reps @ 140 lbs   ✓                   │
│ Set 2: 8 reps @ 140 lbs   ✓                   │
│ > Set 3: reps [__] @ weight [___] [Log]        │
├───────────────────────────────────────────────┤
│ [N] Next exercise  [D] Done  [Notes: _______]  │
└───────────────────────────────────────────────┘
```

- Tab cycles between reps/weight fields
- Enter logs the set and moves to the next set row
- `n` moves to a new exercise (prompts for name with autocomplete)
- `d` finishes the session and prints progressive overload suggestions

---

## API Endpoints (FastAPI `api.py`)

All routes are thin wrappers — they call `habits.py` / `workouts.py` and return the result.

### Habits
```
GET    /habits                     → list all habits
POST   /habits                     → add habit {name}
DELETE /habits/{id}                → delete habit
GET    /habits/{id}/completions    → completions for last N days
POST   /habits/{id}/toggle         → toggle {date}
```

### Workouts
```
GET    /exercises                  → list exercises
POST   /sessions                   → create session {date, notes}
GET    /sessions/{id}              → session detail with sets
POST   /sessions/{id}/sets         → add set {exercise_name, reps, weight_lbs}
GET    /exercises/{id}/history     → set history for exercise
GET    /exercises/{id}/suggestion  → progressive overload suggestion
```

---

## Build Order

1. `db.py` — pool, ensure_database_exists, ensure_tables
2. `habits.py` — all habit functions + tests
3. `workouts.py` — all workout functions + tests
4. `api.py` — add all routes (habits + workouts)
5. `web/app.py` — Streamlit UI, habits page first, then workouts
6. `tui/app.py` + `tui/habits.py` + `tui/workouts.py` — Textual TUI
7. Update `pyproject.toml` with new deps
8. Update `CLAUDE.md` with new run commands
