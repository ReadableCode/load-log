# %%
# Imports #

from datetime import date, timedelta

import pandas as pd

from db import get_conn, release_conn

# %%
# Exercises #


def get_all_exercises() -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, name FROM exercises ORDER BY name ASC;")
        return [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    finally:
        cur.close()
        release_conn(conn)


def get_or_create_exercise(name: str) -> dict:
    normalized = name.strip()
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, name FROM exercises WHERE LOWER(name) = LOWER(%s);",
            (normalized,),
        )
        row = cur.fetchone()
        if row:
            return {"id": row[0], "name": row[1]}
        cur.execute(
            "INSERT INTO exercises (name) VALUES (%s) RETURNING id, name;",
            (normalized,),
        )
        row = cur.fetchone()
        conn.commit()
        return {"id": row[0], "name": row[1]}
    finally:
        cur.close()
        release_conn(conn)


# %%
# Sets #


def add_set(
    workout_date: date,
    exercise_id: int,
    reps: int,
    weight_lbs: float,
) -> dict:
    """Append one set. Auto-assigns set_number as next within (date, exercise).
    Commits immediately so an interrupted session never loses logged sets.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COALESCE(MAX(set_number), 0) FROM workout_sets
            WHERE workout_date = %s AND exercise_id = %s;
            """,
            (workout_date, exercise_id),
        )
        next_num = (cur.fetchone()[0] or 0) + 1
        cur.execute(
            """
            INSERT INTO workout_sets
                (workout_date, exercise_id, set_number, reps, weight_lbs)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, workout_date, exercise_id, set_number, reps, weight_lbs;
            """,
            (workout_date, exercise_id, next_num, reps, weight_lbs),
        )
        row = cur.fetchone()
        conn.commit()
        return {
            "id": row[0],
            "workout_date": row[1],
            "exercise_id": row[2],
            "set_number": row[3],
            "reps": row[4],
            "weight_lbs": row[5],
        }
    finally:
        cur.close()
        release_conn(conn)


def delete_set(set_id: int) -> None:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM workout_sets WHERE id = %s;", (set_id,))
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)


def get_sets_for_date(workout_date: date) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT ws.id, e.name, ws.exercise_id, ws.set_number, ws.reps, ws.weight_lbs
            FROM workout_sets ws
            JOIN exercises e ON e.id = ws.exercise_id
            WHERE ws.workout_date = %s
            ORDER BY ws.exercise_id ASC, ws.set_number ASC;
            """,
            (workout_date,),
        )
        return [
            {
                "id": r[0],
                "exercise_name": r[1],
                "exercise_id": r[2],
                "set_number": r[3],
                "reps": r[4],
                "weight_lbs": r[5],
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        release_conn(conn)


def get_last_workout_for_exercise(
    exercise_id: int, before_date: date | None = None
) -> list[dict]:
    """Sets from the most recent prior date that included this exercise."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        if before_date is None:
            cur.execute(
                """
                SELECT MAX(workout_date) FROM workout_sets WHERE exercise_id = %s;
                """,
                (exercise_id,),
            )
        else:
            cur.execute(
                """
                SELECT MAX(workout_date) FROM workout_sets
                WHERE exercise_id = %s AND workout_date < %s;
                """,
                (exercise_id, before_date),
            )
        row = cur.fetchone()
        last_date = row[0] if row else None
        if last_date is None:
            return []

        cur.execute(
            """
            SELECT set_number, reps, weight_lbs, workout_date
            FROM workout_sets
            WHERE workout_date = %s AND exercise_id = %s
            ORDER BY set_number ASC;
            """,
            (last_date, exercise_id),
        )
        return [
            {
                "set_number": r[0],
                "reps": r[1],
                "weight_lbs": r[2],
                "workout_date": r[3],
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        release_conn(conn)


def get_exercise_history(exercise_id: int, limit_days: int = 365) -> pd.DataFrame:
    cutoff = date.today() - timedelta(days=limit_days)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT workout_date, set_number, reps, weight_lbs
            FROM workout_sets
            WHERE exercise_id = %s AND workout_date >= %s
            ORDER BY workout_date ASC, set_number ASC;
            """,
            (exercise_id, cutoff),
        )
        rows = cur.fetchall()
        return pd.DataFrame(
            rows, columns=["workout_date", "set_number", "reps", "weight_lbs"]
        )
    finally:
        cur.close()
        release_conn(conn)


# %%
# Volume #


def get_volume_by_date(days: int = 365) -> dict[date, float]:
    """{date: sum(reps * weight_lbs)} across all sets in the window."""
    cutoff = date.today() - timedelta(days=days)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT workout_date, COALESCE(SUM(reps * weight_lbs), 0)
            FROM workout_sets
            WHERE workout_date >= %s
            GROUP BY workout_date;
            """,
            (cutoff,),
        )
        return {r[0]: float(r[1]) for r in cur.fetchall()}
    finally:
        cur.close()
        release_conn(conn)


def get_workout_dates(days: int = 365) -> list[date]:
    """Distinct dates with logged sets, ascending."""
    cutoff = date.today() - timedelta(days=days)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT DISTINCT workout_date FROM workout_sets
            WHERE workout_date >= %s
            ORDER BY workout_date ASC;
            """,
            (cutoff,),
        )
        return [r[0] for r in cur.fetchall()]
    finally:
        cur.close()
        release_conn(conn)


# %%
# Progressive Overload #


def suggest_next_weight(exercise_id: int, current_date: date) -> float | None:
    """Compare current_date's sets to the prior workout's sets for this exercise.
    All reps met-or-beat → bump max weight by 5 lbs.
    Any rep regression  → hold previous max weight.
    No previous history → None.
    """
    previous = get_last_workout_for_exercise(exercise_id, before_date=current_date)
    if not previous:
        return None

    prev_max_weight = max(s["weight_lbs"] for s in previous)

    current = [
        s for s in get_sets_for_date(current_date) if s["exercise_id"] == exercise_id
    ]
    if not current:
        return prev_max_weight

    prev_by_set = {s["set_number"]: s for s in previous}
    for s in current:
        prev = prev_by_set.get(s["set_number"])
        if prev is not None and s["reps"] < prev["reps"]:
            return prev_max_weight
    return round(prev_max_weight + 5.0, 2)
