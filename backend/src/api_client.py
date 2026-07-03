# %%
# Imports #

import os
from datetime import date, timedelta

import pandas as pd
import requests

# %%
# Config #

# Shared PostgREST client used by BOTH the Streamlit web app and the TUI. Every
# client gets a JWT from the auth service (login) and sends it as a Bearer token
# on each request — Postgres is never hit directly. Tables are exposed at the
# schema root (e.g. /workout_sets) because PGRST_DB_SCHEMAS=load_log makes
# load_log the default schema — paths are NOT prefixed with /load_log.
POSTGREST_URL = os.environ.get("POSTGREST_URL", "https://pgrest.tinkernet.me").rstrip("/")
AUTH_URL = os.environ.get("AUTH_URL", "https://auth.tinkernet.me").rstrip("/")

# load-log's Postgres schema. The shared auth service maps this to the
# load_log_user role in the JWT it issues.
APP_SCHEMA = os.environ.get("APP_SCHEMA", "load_log")

# Network timeout (seconds) for every HTTP call.
TIMEOUT = 15


# %%
# Auth #


def login(username: str, password: str) -> str:
    """Exchange credentials for a JWT via the auth service. Returns the token.

    Raises requests.HTTPError on bad credentials (the auth service returns 401).
    """
    resp = requests.post(
        f"{AUTH_URL}/token",
        json={"schema": APP_SCHEMA, "username": username, "password": password},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["token"]


# %%
# HTTP helpers #


def _headers(token: str, *, write: bool = False) -> dict:
    """Auth header for every PostgREST call. On writes, ask PostgREST to return
    the affected rows so callers get the inserted/updated representation back."""
    headers = {"Authorization": f"Bearer {token}"}
    if write:
        headers["Prefer"] = "return=representation"
        headers["Content-Type"] = "application/json"
    return headers


def _get(token: str, table: str, params: dict) -> list[dict]:
    resp = requests.get(
        f"{POSTGREST_URL}/{table}",
        headers=_headers(token),
        params=params,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _post(token: str, table: str, body, params: dict | None = None) -> list[dict]:
    resp = requests.post(
        f"{POSTGREST_URL}/{table}",
        headers=_headers(token, write=True),
        params=params or {},
        json=body,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json() if resp.content else []


def _patch(token: str, table: str, params: dict, body: dict) -> list[dict]:
    resp = requests.patch(
        f"{POSTGREST_URL}/{table}",
        headers=_headers(token, write=True),
        params=params,
        json=body,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json() if resp.content else []


def _delete(token: str, table: str, params: dict) -> list[dict]:
    resp = requests.delete(
        f"{POSTGREST_URL}/{table}",
        headers=_headers(token, write=True),
        params=params,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json() if resp.content else []


# %%
# Habits CRUD (mirrors habits.py) #


def get_all_habits(token: str) -> list[dict]:
    return _get(
        token,
        "habits",
        {"select": "id,name,created_at", "order": "created_at.asc,id.asc"},
    )


def add_habit(token: str, name: str) -> dict:
    rows = _post(
        token,
        "habits",
        {"name": name},
        params={"select": "id,name,created_at"},
    )
    return rows[0] if rows else {}


def delete_habit(token: str, habit_id: int) -> None:
    _delete(token, "habits", {"id": f"eq.{habit_id}"})


# %%
# Completions (mirrors habits.py) #


def get_completions(token: str, habit_id: int, days: int = 365) -> list[date]:
    cutoff = date.today() - timedelta(days=days)
    rows = _get(
        token,
        "habit_completions",
        {
            "select": "completed_date",
            "habit_id": f"eq.{habit_id}",
            "completed_date": f"gte.{cutoff.isoformat()}",
            "order": "completed_date.asc",
        },
    )
    return [date.fromisoformat(r["completed_date"]) for r in rows]


def toggle_completion(token: str, habit_id: int, target_date: date) -> bool:
    """Toggle a completion. Returns True if now completed, False if removed.

    Mirrors habits.toggle_completion: delete-if-present, else insert.
    """
    deleted = _delete(
        token,
        "habit_completions",
        {
            "habit_id": f"eq.{habit_id}",
            "completed_date": f"eq.{target_date.isoformat()}",
            "select": "id",
        },
    )
    if deleted:
        return False
    _post(
        token,
        "habit_completions",
        {"habit_id": habit_id, "completed_date": target_date.isoformat()},
    )
    return True


def get_current_streak(token: str, habit_id: int, today: date | None = None) -> int:
    """Consecutive completed days ending today (or yesterday if today not done).

    Mirrors habits.get_current_streak but sources completions over HTTP.
    """
    completions = set(get_completions(token, habit_id, days=400))
    if today is None:
        today = date.today()
    if today not in completions and (today - timedelta(days=1)) not in completions:
        return 0
    cursor = today if today in completions else today - timedelta(days=1)
    streak = 0
    while cursor in completions:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


# %%
# Exercises (mirrors workouts.py) #


def get_all_exercises(token: str) -> list[dict]:
    return _get(token, "exercises", {"select": "id,name", "order": "name.asc"})


def get_or_create_exercise(token: str, name: str) -> dict:
    """Case-insensitive lookup, insert if missing. Mirrors workouts.get_or_create_exercise."""
    normalized = name.strip()
    # PostgREST `ilike` is case-insensitive; escape nothing fancy — exercise
    # names are plain words. Match the whole string (no wildcards).
    existing = _get(
        token,
        "exercises",
        {"select": "id,name", "name": f"ilike.{normalized}", "limit": "1"},
    )
    if existing:
        return existing[0]
    rows = _post(
        token, "exercises", {"name": normalized}, params={"select": "id,name"}
    )
    return rows[0] if rows else {}


# %%
# Sets (mirrors workouts.py) #


def add_set(
    token: str,
    workout_date: date,
    exercise_id: int,
    reps: int,
    weight_lbs: float,
) -> dict:
    """Append one set, auto-assigning set_number as next within (date, exercise).

    Mirrors workouts.add_set. The next set_number is derived client-side from a
    read of the existing sets, then inserted.
    """
    existing = _get(
        token,
        "workout_sets",
        {
            "select": "set_number",
            "workout_date": f"eq.{workout_date.isoformat()}",
            "exercise_id": f"eq.{exercise_id}",
            "order": "set_number.desc",
            "limit": "1",
        },
    )
    next_num = (existing[0]["set_number"] if existing else 0) + 1
    rows = _post(
        token,
        "workout_sets",
        {
            "workout_date": workout_date.isoformat(),
            "exercise_id": exercise_id,
            "set_number": next_num,
            "reps": reps,
            "weight_lbs": weight_lbs,
        },
    )
    return rows[0] if rows else {}


def delete_set(token: str, set_id: int) -> None:
    """Delete a set and renumber the survivors so the visible 1..N stays
    sequential. Mirrors workouts.delete_set (the renumber is done client-side
    here since PostgREST has no window-function UPDATE)."""
    target = _get(
        token,
        "workout_sets",
        {
            "select": "workout_date,exercise_id",
            "id": f"eq.{set_id}",
            "limit": "1",
        },
    )
    if not target:
        return
    workout_date = target[0]["workout_date"]
    exercise_id = target[0]["exercise_id"]

    _delete(token, "workout_sets", {"id": f"eq.{set_id}"})

    survivors = _get(
        token,
        "workout_sets",
        {
            "select": "id,set_number",
            "workout_date": f"eq.{workout_date}",
            "exercise_id": f"eq.{exercise_id}",
            "order": "set_number.asc,id.asc",
        },
    )
    for new_num, row in enumerate(survivors, start=1):
        if row["set_number"] != new_num:
            _patch(
                token,
                "workout_sets",
                {"id": f"eq.{row['id']}"},
                {"set_number": new_num},
            )


def update_set(
    token: str, set_id: int, reps: int, weight_lbs: float
) -> dict | None:
    """Patch reps/weight on an existing set. Mirrors workouts.update_set."""
    rows = _patch(
        token,
        "workout_sets",
        {"id": f"eq.{set_id}"},
        {"reps": reps, "weight_lbs": weight_lbs},
    )
    return rows[0] if rows else None


def get_sets_for_date(token: str, workout_date: date) -> list[dict]:
    """Sets on a date, joined to exercise name. Mirrors workouts.get_sets_for_date.

    Uses a PostgREST embedded resource (exercises!inner) to pull the exercise
    name in one request, then flattens it to match the dict shape callers expect.
    """
    rows = _get(
        token,
        "workout_sets",
        {
            "select": "id,exercise_id,set_number,reps,weight_lbs,exercises(name)",
            "workout_date": f"eq.{workout_date.isoformat()}",
            "order": "exercise_id.asc,set_number.asc",
        },
    )
    return [
        {
            "id": r["id"],
            "exercise_name": (r.get("exercises") or {}).get("name"),
            "exercise_id": r["exercise_id"],
            "set_number": r["set_number"],
            "reps": r["reps"],
            "weight_lbs": r["weight_lbs"],
        }
        for r in rows
    ]


def get_last_workout_for_exercise(
    token: str, exercise_id: int, before_date: date | None = None
) -> list[dict]:
    """Sets from the most recent prior date that included this exercise.

    Mirrors workouts.get_last_workout_for_exercise. PostgREST can't do a
    correlated MAX subquery, so we find the latest date with a small ordered
    read, then fetch that day's sets.
    """
    params = {
        "select": "workout_date",
        "exercise_id": f"eq.{exercise_id}",
        "order": "workout_date.desc",
        "limit": "1",
    }
    if before_date is not None:
        params["workout_date"] = f"lt.{before_date.isoformat()}"
    latest = _get(token, "workout_sets", params)
    if not latest:
        return []
    last_date = latest[0]["workout_date"]

    rows = _get(
        token,
        "workout_sets",
        {
            "select": "set_number,reps,weight_lbs,workout_date",
            "workout_date": f"eq.{last_date}",
            "exercise_id": f"eq.{exercise_id}",
            "order": "set_number.asc",
        },
    )
    return [
        {
            "set_number": r["set_number"],
            "reps": r["reps"],
            "weight_lbs": r["weight_lbs"],
            "workout_date": date.fromisoformat(r["workout_date"]),
        }
        for r in rows
    ]


def get_exercise_history(
    token: str, exercise_id: int, limit_days: int = 365
) -> pd.DataFrame:
    """Per-set history for an exercise. Mirrors workouts.get_exercise_history."""
    cutoff = date.today() - timedelta(days=limit_days)
    rows = _get(
        token,
        "workout_sets",
        {
            "select": "id,workout_date,set_number,reps,weight_lbs",
            "exercise_id": f"eq.{exercise_id}",
            "workout_date": f"gte.{cutoff.isoformat()}",
            "order": "workout_date.asc,set_number.asc",
        },
    )
    df = pd.DataFrame(
        rows, columns=["id", "workout_date", "set_number", "reps", "weight_lbs"]
    )
    if not df.empty:
        df["workout_date"] = pd.to_datetime(df["workout_date"])
    return df


# %%
# Volume (mirrors workouts.py) #


def get_volume_by_date(token: str, days: int = 365) -> dict[date, float]:
    """{date: sum(reps * weight_lbs)} across the window.

    Mirrors workouts.get_volume_by_date. PostgREST has no GROUP BY without a DB
    view, so we pull the raw sets in the window and aggregate client-side.
    """
    cutoff = date.today() - timedelta(days=days)
    rows = _get(
        token,
        "workout_sets",
        {
            "select": "workout_date,reps,weight_lbs",
            "workout_date": f"gte.{cutoff.isoformat()}",
        },
    )
    totals: dict[date, float] = {}
    for r in rows:
        d = date.fromisoformat(r["workout_date"])
        totals[d] = totals.get(d, 0.0) + float(r["reps"]) * float(r["weight_lbs"])
    return totals


def get_workout_dates(token: str, days: int = 365) -> list[date]:
    """Distinct dates with logged sets, ascending. Mirrors workouts.get_workout_dates."""
    cutoff = date.today() - timedelta(days=days)
    rows = _get(
        token,
        "workout_sets",
        {
            "select": "workout_date",
            "workout_date": f"gte.{cutoff.isoformat()}",
            "order": "workout_date.asc",
        },
    )
    return sorted({date.fromisoformat(r["workout_date"]) for r in rows})


# %%
# Progressive Overload (mirrors workouts.py) #


def suggest_next_weight(
    token: str, exercise_id: int, current_date: date
) -> float | None:
    """Compare current_date's sets to the prior workout's for this exercise.

    Mirrors workouts.suggest_next_weight exactly, sourcing data over HTTP.
    """
    previous = get_last_workout_for_exercise(
        token, exercise_id, before_date=current_date
    )
    if not previous:
        return None

    prev_max_weight = max(s["weight_lbs"] for s in previous)

    current = [
        s
        for s in get_sets_for_date(token, current_date)
        if s["exercise_id"] == exercise_id
    ]
    if not current:
        return prev_max_weight

    prev_by_set = {s["set_number"]: s for s in previous}
    for s in current:
        prev = prev_by_set.get(s["set_number"])
        if prev is not None and s["reps"] < prev["reps"]:
            return prev_max_weight
    return round(prev_max_weight + 5.0, 2)
