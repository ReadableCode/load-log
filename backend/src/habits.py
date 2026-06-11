# %%
# Imports #

from datetime import date, timedelta

from db import get_conn, release_conn

# %%
# Habits CRUD #


def get_all_habits() -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, name, created_at FROM habits ORDER BY created_at ASC, id ASC;"
        )
        rows = cur.fetchall()
        return [
            {"id": r[0], "name": r[1], "created_at": r[2]} for r in rows
        ]
    finally:
        cur.close()
        release_conn(conn)


def add_habit(name: str) -> dict:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO habits (name) VALUES (%s) RETURNING id, name, created_at;",
            (name,),
        )
        row = cur.fetchone()
        conn.commit()
        return {"id": row[0], "name": row[1], "created_at": row[2]}
    finally:
        cur.close()
        release_conn(conn)


def delete_habit(habit_id: int) -> None:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM habits WHERE id = %s;", (habit_id,))
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)


# %%
# Completions #


def get_completions(habit_id: int, days: int = 365) -> list[date]:
    cutoff = date.today() - timedelta(days=days)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT completed_date FROM habit_completions
            WHERE habit_id = %s AND completed_date >= %s
            ORDER BY completed_date ASC;
            """,
            (habit_id, cutoff),
        )
        return [r[0] for r in cur.fetchall()]
    finally:
        cur.close()
        release_conn(conn)


def toggle_completion(habit_id: int, target_date: date) -> bool:
    """Toggle a completion. Returns True if now completed, False if removed."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM habit_completions WHERE habit_id = %s AND completed_date = %s RETURNING id;",
            (habit_id, target_date),
        )
        deleted = cur.fetchone()
        if deleted:
            conn.commit()
            return False
        cur.execute(
            "INSERT INTO habit_completions (habit_id, completed_date) VALUES (%s, %s);",
            (habit_id, target_date),
        )
        conn.commit()
        return True
    finally:
        cur.close()
        release_conn(conn)


def get_completion_counts(days: int = 7) -> dict[int, int]:
    cutoff = date.today() - timedelta(days=days)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT habit_id, COUNT(*) FROM habit_completions
            WHERE completed_date >= %s AND completed_date <= CURRENT_DATE
            GROUP BY habit_id;
            """,
            (cutoff,),
        )
        return {r[0]: r[1] for r in cur.fetchall()}
    finally:
        cur.close()
        release_conn(conn)


# %%
# Derived #


def get_current_streak(habit_id: int) -> int:
    """Consecutive completed days ending today (or yesterday if today not done)."""
    completions = set(get_completions(habit_id, days=400))
    today = date.today()
    if today not in completions and (today - timedelta(days=1)) not in completions:
        return 0
    cursor = today if today in completions else today - timedelta(days=1)
    streak = 0
    while cursor in completions:
        streak += 1
        cursor -= timedelta(days=1)
    return streak
