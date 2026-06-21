# Feature Specs

---

## Feature 1: Daily Habit Tracker

### Habit tracker — what it does

The user defines habits they want to do every day (e.g., "10,000 steps", "30 pushups"). For each habit, the app renders a GitHub-style contribution heatmap showing the last 52 weeks. The user can check off any day — past, today, or future — with a single click/keypress.

---

### Habit data functions (`api_client.py`)

All data access is HTTP to PostgREST with a Bearer JWT — every function takes the
`token` as its first argument. There is no SQL in the app.

```python
def get_all_habits(token) -> list[dict]
    # GET /habits → [{id, name, created_at}, ...]

def add_habit(token, name: str) -> dict
    # POST /habits → the new row

def delete_habit(token, habit_id: int) -> None
    # DELETE /habits?id=eq.<id> (cascades to completions)

def get_completions(token, habit_id: int, days: int = 365) -> list[date]
    # GET /habit_completions filtered to the last `days` days → sorted dates

def toggle_completion(token, habit_id: int, target_date: date) -> bool
    # If (habit_id, target_date) exists: DELETE it, return False
    # If not: POST it, return True

def get_current_streak(token, habit_id: int, today=None) -> int
    # Consecutive completed days ending today
```

---

### Web UI — habits (`web/app.py` — Streamlit)

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

### TUI — habits (`tui/habits.py` — Textual)

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

### Workout tracker — what it does

The user logs a workout session set by set. They pick an exercise name (autocompleted from history), then enter sets one at a time: reps and weight. After each set they can add another or move to the next exercise. The app always shows the last time they did that exercise so they know what to beat. Session notes are optional. After saving, the app shows whether to go up in weight next time.

---

### Workout data functions (`api_client.py`)

Same as habits: HTTP to PostgREST, `token` first arg. Operations PostgREST can't
do server-side (next `set_number`, renumber-after-delete, volume aggregation,
"most recent prior date") are composed client-side from small ordered reads.

```python
def get_all_exercises(token) -> list[dict]
    # [{id, name}, ...] sorted by name

def get_or_create_exercise(token, name: str) -> dict
    # Case-insensitive lookup (ilike), POST if not found.

def add_set(token, workout_date, exercise_id, reps, weight_lbs) -> dict
    # Derives next set_number within (date, exercise) from a read, then POSTs.

def delete_set(token, set_id: int) -> None
    # DELETE, then renumber survivors so visible set_number stays 1..N.

def update_set(token, set_id, reps, weight_lbs) -> dict | None
    # PATCH reps/weight; returns the updated row or None.

def get_sets_for_date(token, workout_date) -> list[dict]
    # [{id, exercise_name, exercise_id, set_number, reps, weight_lbs}, ...]
    # (joins the exercise name via a PostgREST embedded resource)

def get_last_workout_for_exercise(token, exercise_id, before_date=None) -> list[dict]
    # Sets from the most recent prior date that included this exercise.

def get_exercise_history(token, exercise_id, limit_days=365) -> pd.DataFrame
def get_volume_by_date(token, days=365) -> dict[date, float]   # drives the volume heatmap
def get_workout_dates(token, days=365) -> list[date]
def suggest_next_weight(token, exercise_id, current_date) -> float | None
```

---

### Web UI — workouts (`web/app.py` — Streamlit)

**Volume heatmap** at the top (GitHub-style, 52 × 7). Color shade is graded by
total daily volume (`reps × weight` summed across all sets that day) using
quartile thresholds against the user's own range. Click a cell → that date
becomes the active workout date.

**Day editor** below the heatmap, for the picked date:

```text
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

**Editing / deleting logged sets** — the day's sets are shown in an
`st.data_editor` (not a static dataframe). Tab through cells to edit reps
or weight inline (Enter or click-out commits the change to the DB); click
the trash icon on a row to delete it. `exercise_name` and `set_number` are
read-only — they're identity columns. Deleting a middle set renumbers the
rest so the visible numbering stays 1..N.

**History view (per exercise):**

- Line chart: max weight per `workout_date` over time
- Table: all logged sets with dates

---

### TUI — workouts (`tui/workouts.py` — Textual)

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

**Editing / deleting logged sets** — every row in "Sets logged on selected
date" has explicit `Edit` and `Delete` buttons:

- `Delete` removes that row immediately and renumbers the remaining sets
  for that (date, exercise) so the visible 1..N stays sequential.
- `Edit` pre-fills the form with that row's reps/weight, swaps the form
  title to "Editing set #N", changes the green button to "Save changes",
  and shows a yellow "Cancel edit" button. Enter on either field saves the
  edit; Cancel discards it. After save (or cancel) the form returns to the
  normal add-mode prefill.

---

## Data Access (PostgREST)

There is no custom API. `api_client.py` calls PostgREST directly; PostgREST
exposes each table at the schema root (paths are NOT prefixed with `/load_log`
because `load_log` is the default schema). Every request carries
`Authorization: Bearer <jwt>` and Postgres enforces access via `load_log_user`.

```text
# Auth (shared service)
POST   https://auth.tinkernet.me/token        {schema, username, password} → {token}

# Data (PostgREST), with Authorization: Bearer <token>
GET    /habits?select=*                        list habits
POST   /habits                                 add habit {name}
DELETE /habits?id=eq.<id>                       delete habit (cascades)
GET    /habit_completions?habit_id=eq.<id>&completed_date=gte.<date>
POST   /habit_completions                       mark a day  {habit_id, completed_date}
DELETE /habit_completions?habit_id=eq.<id>&completed_date=eq.<date>

GET    /exercises?select=id,name&order=name.asc
POST   /exercises                               {name}
GET    /workout_sets?workout_date=eq.<date>&select=...,exercises(name)
POST   /workout_sets                            {workout_date, exercise_id, set_number, reps, weight_lbs}
PATCH  /workout_sets?id=eq.<id>                  {reps, weight_lbs}
DELETE /workout_sets?id=eq.<id>
```

Composite behaviors (next `set_number`, renumber-after-delete, volume totals,
"most recent prior date", progressive-overload suggestion) are assembled in
`api_client.py` from these primitives.

---

## Status

The PostgREST migration is complete:

1. ✅ `api_client.py` — shared PostgREST + auth HTTP client (web and TUI).
2. ✅ `web/app.py` — Streamlit with a login gate and clickable Altair heatmaps
   (habit completion + workout volume), per-set prefill, all data via PostgREST.
3. ✅ `tui/` — Textual screens (clickable heatmaps, Enter-to-log form); logs in
   from `LOAD_LOG_USERNAME`/`LOAD_LOG_PASSWORD` and uses the same client.
4. ✅ `alembic/` — `0001` idempotent baseline + `0002` users table; applied on
   startup by `docker-entrypoint.sh`.
5. ✅ Shared `auth` service (`../postgrest-auth/`) + `postgrest` added to
   `docker_compose_projects.yaml`; SWAG confs for `pgrest`/`auth`.
6. ✅ `scripts/create_user.py` (seed users) and `scripts/backup_to_files.py`
   (CSV/Parquet backup) remain as direct-DB ops tools.

Removed with the migration: the old direct-Postgres data layer (`db.py`,
`habits.py`, `workouts.py`), the unused FastAPI surface (`api.py`), their tests,
and the legacy `migrate_drop_sessions.py` script.
