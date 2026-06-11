# %%
# Imports #

from datetime import date

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
# Sessions #


def create_session(session_date: date | None = None, notes: str = "") -> dict:
    conn = get_conn()
    cur = conn.cursor()
    try:
        if session_date is None:
            cur.execute(
                "INSERT INTO workout_sessions (notes) VALUES (%s) RETURNING id, session_date, notes;",
                (notes,),
            )
        else:
            cur.execute(
                """
                INSERT INTO workout_sessions (session_date, notes)
                VALUES (%s, %s) RETURNING id, session_date, notes;
                """,
                (session_date, notes),
            )
        row = cur.fetchone()
        conn.commit()
        return {"id": row[0], "session_date": row[1], "notes": row[2] or ""}
    finally:
        cur.close()
        release_conn(conn)


def update_session_notes(session_id: int, notes: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE workout_sessions SET notes = %s WHERE id = %s;",
            (notes, session_id),
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)


def get_recent_sessions(limit: int = 10) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, session_date, notes FROM workout_sessions
            ORDER BY session_date DESC, id DESC LIMIT %s;
            """,
            (limit,),
        )
        return [
            {"id": r[0], "session_date": r[1], "notes": r[2] or ""}
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        release_conn(conn)


# %%
# Sets #


def add_set(
    session_id: int,
    exercise_id: int,
    set_number: int,
    reps: int,
    weight_lbs: float,
) -> dict:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO workout_sets (session_id, exercise_id, set_number, reps, weight_lbs)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, session_id, exercise_id, set_number, reps, weight_lbs;
            """,
            (session_id, exercise_id, set_number, reps, weight_lbs),
        )
        row = cur.fetchone()
        conn.commit()
        return {
            "id": row[0],
            "session_id": row[1],
            "exercise_id": row[2],
            "set_number": row[3],
            "reps": row[4],
            "weight_lbs": row[5],
        }
    finally:
        cur.close()
        release_conn(conn)


def get_session_sets(session_id: int) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT e.name, ws.exercise_id, ws.set_number, ws.reps, ws.weight_lbs
            FROM workout_sets ws
            JOIN exercises e ON e.id = ws.exercise_id
            WHERE ws.session_id = %s
            ORDER BY ws.exercise_id ASC, ws.set_number ASC;
            """,
            (session_id,),
        )
        return [
            {
                "exercise_name": r[0],
                "exercise_id": r[1],
                "set_number": r[2],
                "reps": r[3],
                "weight_lbs": r[4],
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        release_conn(conn)


def get_last_session_for_exercise(
    exercise_id: int, before_session_id: int | None = None
) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    try:
        if before_session_id is None:
            cur.execute(
                """
                SELECT session_id FROM workout_sets
                WHERE exercise_id = %s
                ORDER BY session_id DESC LIMIT 1;
                """,
                (exercise_id,),
            )
        else:
            cur.execute(
                """
                SELECT session_id FROM workout_sets
                WHERE exercise_id = %s AND session_id < %s
                ORDER BY session_id DESC LIMIT 1;
                """,
                (exercise_id, before_session_id),
            )
        row = cur.fetchone()
        if not row:
            return []
        last_session_id = row[0]

        cur.execute(
            """
            SELECT ws.set_number, ws.reps, ws.weight_lbs, s.session_date
            FROM workout_sets ws
            JOIN workout_sessions s ON s.id = ws.session_id
            WHERE ws.session_id = %s AND ws.exercise_id = %s
            ORDER BY ws.set_number ASC;
            """,
            (last_session_id, exercise_id),
        )
        return [
            {
                "set_number": r[0],
                "reps": r[1],
                "weight_lbs": r[2],
                "session_date": r[3],
                "session_id": last_session_id,
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        release_conn(conn)


def get_exercise_history(exercise_id: int, limit: int = 20) -> pd.DataFrame:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT s.session_date, ws.set_number, ws.reps, ws.weight_lbs
            FROM workout_sets ws
            JOIN workout_sessions s ON s.id = ws.session_id
            WHERE ws.exercise_id = %s
            ORDER BY s.session_date ASC, ws.set_number ASC
            LIMIT %s;
            """,
            (exercise_id, limit * 10),
        )
        rows = cur.fetchall()
        return pd.DataFrame(
            rows, columns=["session_date", "set_number", "reps", "weight_lbs"]
        )
    finally:
        cur.close()
        release_conn(conn)


# %%
# Progressive Overload #


def suggest_next_weight(exercise_id: int, current_session_id: int) -> float | None:
    """Suggest weight for next session based on current vs previous performance.

    Returns None if no previous history exists.
    All current reps >= previous reps: bump max weight by 5 lbs.
    Any current rep < previous rep: keep same weight as previous.
    """
    current = get_last_session_for_exercise(
        exercise_id, before_session_id=current_session_id + 1
    )
    # Filter to actually this session
    current = [s for s in current if s["session_id"] == current_session_id]
    previous = get_last_session_for_exercise(
        exercise_id, before_session_id=current_session_id
    )

    if not previous:
        return None

    prev_max_weight = max(s["weight_lbs"] for s in previous)

    if not current:
        return prev_max_weight

    prev_by_set = {s["set_number"]: s for s in previous}
    hit_all_targets = True
    for s in current:
        prev = prev_by_set.get(s["set_number"])
        if prev is None:
            continue
        if s["reps"] < prev["reps"]:
            hit_all_targets = False
            break

    if hit_all_targets:
        return round(prev_max_weight + 5.0, 2)
    return prev_max_weight
