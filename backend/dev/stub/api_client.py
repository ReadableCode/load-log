# %%
# Stub api_client #

"""Fake api_client for previewing the web UI in a browser — no network, no auth.

Shadows the real src/api_client.py via PYTHONPATH ordering (this directory must
come first), so the app imports this module instead. Any username/password logs
in; data is deterministic synthetic history (seeded) for three exercises over
~180 days. Lives outside src/ on purpose so production code can never import it.

Run from backend/ (see dev/README.md):

    PYTHONPATH="dev/stub:src" uv run streamlit run src/web/app.py --server.port 8601
"""

import random
from datetime import date, timedelta

import pandas as pd

random.seed(7)

_EXERCISES = [
    {"id": 1, "name": "Bench Press"},
    {"id": 2, "name": "Squat"},
    {"id": 3, "name": "Deadlift"},
]

_TODAY = date.today()


def _gen_sets():
    rows = []
    sid = 1
    base = {1: 135.0, 2: 185.0, 3: 225.0}
    d = _TODAY - timedelta(days=180)
    while d <= _TODAY:
        if d.weekday() in (0, 2, 4):  # Mon/Wed/Fri
            for ex in _EXERCISES:
                progress = (d - (_TODAY - timedelta(days=180))).days / 180.0
                top = base[ex["id"]] * (1 + 0.25 * progress)
                for set_no in range(1, 4):
                    w = round((top - 5 * (set_no - 1)) / 2.5) * 2.5
                    reps = random.choice([5, 6, 8, 8, 10])
                    rows.append(
                        {
                            "id": sid,
                            "workout_date": d,
                            "exercise_id": ex["id"],
                            "exercise_name": ex["name"],
                            "set_number": set_no,
                            "reps": reps,
                            "weight_lbs": w + random.choice([-5, 0, 0, 5]),
                        }
                    )
                    sid += 1
        d += timedelta(days=1)
    return rows


_SETS = _gen_sets()


def login(username, password):
    return "stub-jwt"


def get_all_habits(token):
    return [{"id": 1, "name": "Lift", "created_at": "2026-01-01"}]


def get_current_streak(token, habit_id, today=None):
    return 4


def get_completions(token, habit_id, days=365):
    return sorted({s["workout_date"] for s in _SETS})


def toggle_completion(token, habit_id, target_date):
    return True


def add_habit(token, name):
    return {}


def delete_habit(token, habit_id):
    pass


def get_all_exercises(token):
    return _EXERCISES


def get_or_create_exercise(token, name):
    for e in _EXERCISES:
        if e["name"].lower() == name.lower():
            return e
    return _EXERCISES[0]


def get_last_workout_for_exercise(token, exercise_id, before_date=None):
    dates = sorted(
        {
            s["workout_date"]
            for s in _SETS
            if s["exercise_id"] == exercise_id
            and (before_date is None or s["workout_date"] < before_date)
        }
    )
    if not dates:
        return []
    last = dates[-1]
    return [
        {
            "set_number": s["set_number"],
            "reps": s["reps"],
            "weight_lbs": s["weight_lbs"],
            "workout_date": last,
        }
        for s in _SETS
        if s["exercise_id"] == exercise_id and s["workout_date"] == last
    ]


def get_sets_for_date(token, workout_date):
    day = [dict(s) for s in _SETS if s["workout_date"] == workout_date]
    return sorted(day, key=lambda s: (s["exercise_id"], s["set_number"]))


def add_set(token, workout_date, exercise_id, reps, weight_lbs):
    # Mutate _SETS so the preview behaves like the real app (edits persist
    # across Streamlit reruns until the server restarts).
    ex = next((e for e in _EXERCISES if e["id"] == exercise_id), _EXERCISES[0])
    nums = [
        s["set_number"]
        for s in _SETS
        if s["workout_date"] == workout_date and s["exercise_id"] == exercise_id
    ]
    row = {
        "id": max((s["id"] for s in _SETS), default=0) + 1,
        "workout_date": workout_date,
        "exercise_id": exercise_id,
        "exercise_name": ex["name"],
        "set_number": max(nums, default=0) + 1,
        "reps": reps,
        "weight_lbs": weight_lbs,
    }
    _SETS.append(row)
    return dict(row)


def delete_set(token, set_id):
    _SETS[:] = [s for s in _SETS if s["id"] != set_id]


def update_set(token, set_id, reps, weight_lbs):
    for s in _SETS:
        if s["id"] == set_id:
            s["reps"] = reps
            s["weight_lbs"] = weight_lbs
            return dict(s)
    return None


def get_exercise_history(token, exercise_id, limit_days=365):
    rows = [
        {
            "id": s["id"],
            "workout_date": s["workout_date"],
            "set_number": s["set_number"],
            "reps": s["reps"],
            "weight_lbs": s["weight_lbs"],
        }
        for s in _SETS
        if s["exercise_id"] == exercise_id
    ]
    df = pd.DataFrame(
        rows, columns=["id", "workout_date", "set_number", "reps", "weight_lbs"]
    )
    if not df.empty:
        df["workout_date"] = pd.to_datetime(df["workout_date"])
    return df


def get_volume_by_date(token, days=365):
    totals = {}
    for s in _SETS:
        d = s["workout_date"]
        totals[d] = totals.get(d, 0.0) + s["reps"] * s["weight_lbs"]
    return totals


def suggest_next_weight(token, exercise_id, current_date):
    return 5.0 + max(
        (s["weight_lbs"] for s in _SETS if s["exercise_id"] == exercise_id), default=0
    )
