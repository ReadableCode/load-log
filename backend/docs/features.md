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

```text
 Load Log

 Habits
 Daily tracker — pick a habit and view its heatmap.

╭───────────────────────────────────────────────╮
│ new habit name…                       [ Add ] │
╰───────────────────────────────────────────────╯
   ✓   30 pushups                  streak:   4d
   ✗   10,000 steps                streak:   0d
   ✓   60s plank                   streak:  12d

 ┃ a Add  enter View  space Toggle today  delete Delete  h Habits  w Workouts  q Quit
```

Design rules for the TUI (apply across both screens):

- **One bold title** at the top (the screen name only — no bracketed key hints).
- **One muted subtitle** under it explaining what to do.
- **No shortcuts in the title row.** The Footer at the very bottom is the
  source of truth for keyboard shortcuts AND is clickable, so duplicating
  the hints up top just adds noise and breaks visually in narrow terminals.
- Each habit is a single `ListView` row → arrow keys navigate, enter opens
  the heatmap detail screen, space toggles today, delete removes it.

---

## Feature 2: Workout Tracker

### What it does

The user logs a workout session set by set. They pick an exercise name (autocompleted from history), then enter sets one at a time: reps and weight. After each set they can add another or move to the next exercise. The app always shows the last time they did that exercise so they know what to beat. Session notes are optional. After saving, the app shows whether to go up in weight next time.

---

### `workouts.py` — functions

```python
def get_all_exercises() -> list[dict]
    # [{id, name}, ...] sorted by name

def get_or_create_exercise(name: str) -> dict
    # Case-insensitive lookup, INSERT if not found.

def add_set(workout_date: date, exercise_id: int, reps: int, weight_lbs: float) -> dict
    # Auto-assigns next set_number within (date, exercise).
    # Commits IMMEDIATELY so an interrupted workout never loses logged sets.

def delete_set(set_id: int) -> None

def get_sets_for_date(workout_date: date) -> list[dict]
    # [{id, exercise_name, exercise_id, set_number, reps, weight_lbs}, ...]

def get_last_workout_for_exercise(exercise_id: int, before_date: date | None = None) -> list[dict]
    # Sets from the most recent prior date that included this exercise.

def get_exercise_history(exercise_id: int, limit_days: int = 365) -> pd.DataFrame
    # [workout_date, set_number, reps, weight_lbs]

def get_volume_by_date(days: int = 365) -> dict[date, float]
    # {date: sum(reps * weight_lbs)} — drives the volume heatmap.

def get_workout_dates(days: int = 365) -> list[date]
    # Distinct dates that have any logged sets.

def suggest_next_weight(exercise_id: int, current_date: date) -> float | None
    # See logic in schema.md.
```

---

### Web UI (`web/app.py` — Streamlit)

**Volume heatmap** at the top (GitHub-style, 52 × 7). Color shade is graded by
total daily volume (`reps × weight` summed across all sets that day) using
quartile thresholds against the user's own range. Click a cell → that date
becomes the active workout date.

**Day editor** below the heatmap, for the picked date:

```
Selected: Thu Jun 11, 2026 — volume 4,320 lbs

New exercise: [___________]    Existing: [bench press ▼]

Last time (2026-06-04): 8×135, 8×135, 7×135

[ Reps  8  ]  [ Weight  140  ]  [ Log set ]

Sets logged on this day:
  bench press   set 1   8 reps   140 lbs
  bench press   set 2   8 reps   140 lbs

Progressive-overload suggestions:
  • bench press: next session try **145 lbs**
```

The Log set form auto-fills reps/weight from **today's last logged set** for
the picked exercise (so set 2/3/… reuse the values from set 1), falling back
to the previous workout for the first set of the day. Submits on Enter or
the button. Each submit commits a single INSERT and reruns the page so the
next set is one Enter away.

**History view (per exercise):**

- Line chart: max weight per `workout_date` over time
- Table: all logged sets with dates

---

### TUI (`tui/workouts.py` — Textual)

Same model as the Streamlit page: a volume heatmap drives date selection.

```text
 Load Log

 Workouts
 Click a day on the heatmap to pick it · enter on either field logs the set.

      Jun                  Jul
Mon  ■ ■ ■ ◉ ■ ■  ■ ■ ■ ■ ■ ■  ...
Tue  ■ ■ ■ ■ ■ ■  ■ ■ ■ ■ ■ ■
Wed  ■ ■ ■ ■ ■ ■  ■ ■ ■ ■ ■ ■
... (Mon-Sun × 18 weeks)

Selected: Thu Jun 11, 2026 • volume: 4,320 lbs

Exercise (enter or pick to start logging):
  [ bench press        ] [ Select ]
  bench press — last (2026-06-04): 8×135, 8×135, 7×135

Log a set — enter in either field submits:
  Reps:         [ 8   ]
  Weight (lbs): [ 140 ]
  [ Log set ]

Sets logged on selected date:
  bench press  set 1: 8 reps @ 140 lbs
  bench press  set 2: 8 reps @ 140 lbs
```

- Each input lives on its own row so both fields are always visible — no
  layout fight between two `Input` widgets in a narrow terminal.
- Click any heatmap cell → that date becomes selected; `t` jumps back to today.
- In **Reps**: Enter moves focus to **Weight** (if empty) or submits.
- In **Weight**: Enter submits the set.
- Each submit commits one INSERT, refreshes the heatmap volume tally, and
  **pre-fills** the next set's reps/weight from the set you just logged. So
  three sets of `8 × 140` is: type once, Enter, Enter, Enter.

---

## API Endpoints (FastAPI `api.py`)

All routes are thin wrappers — they call `habits.py` / `workouts.py` and return the result.

### Habits

```text
GET    /habits                     → list all habits
POST   /habits                     → add habit {name}
DELETE /habits/{id}                → delete habit
GET    /habits/{id}/completions    → completions for last N days
POST   /habits/{id}/toggle         → toggle {date}
```

### Workouts

```text
GET    /exercises                          → list exercises
GET    /workouts/volume?days=365           → {date: total_volume} for heatmap
GET    /workouts/{workout_date}            → sets logged on a date
POST   /workouts/{workout_date}/sets       → add set {exercise_name, reps, weight_lbs}
DELETE /sets/{set_id}                      → remove a logged set
GET    /exercises/{id}/history             → set history for exercise
GET    /exercises/{id}/suggestion?workout_date=YYYY-MM-DD
                                           → progressive overload suggestion
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
