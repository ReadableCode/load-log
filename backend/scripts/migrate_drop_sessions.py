# %%
# Imports #

import os
import sys
from datetime import datetime

# allow `uv run python scripts/migrate_drop_sessions.py` from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from db import get_conn, release_conn  # noqa: E402

# %%
# Migration #


def has_legacy_schema(cur) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'workout_sets'
          AND column_name = 'session_id';
        """
    )
    return cur.fetchone() is not None


def migrate() -> None:
    conn = get_conn()
    cur = conn.cursor()
    try:
        if not has_legacy_schema(cur):
            print("No legacy schema detected. Nothing to do.")
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_sets = f"workout_sets_backup_{ts}"
        backup_sessions = f"workout_sessions_backup_{ts}"

        # 1) Materialize a non-destructive backup of both tables.
        cur.execute(
            f'CREATE TABLE "{backup_sets}" AS SELECT * FROM workout_sets;'
        )
        cur.execute(
            f'CREATE TABLE "{backup_sessions}" AS SELECT * FROM workout_sessions;'
        )
        print(f"Backed up workout_sets → {backup_sets}")
        print(f"Backed up workout_sessions → {backup_sessions}")

        # 2) Build the new flat workout_sets table.
        cur.execute("ALTER TABLE workout_sets RENAME TO workout_sets_legacy;")
        cur.execute(
            """
            CREATE TABLE workout_sets (
                id            SERIAL PRIMARY KEY,
                workout_date  DATE NOT NULL DEFAULT CURRENT_DATE,
                exercise_id   INTEGER NOT NULL REFERENCES exercises(id),
                set_number    INTEGER NOT NULL,
                reps          INTEGER NOT NULL,
                weight_lbs    REAL NOT NULL
            );
            CREATE INDEX workout_sets_date_idx ON workout_sets (workout_date);
            """
        )

        # 3) Re-insert rows, deriving workout_date from the parent session.
        cur.execute(
            """
            INSERT INTO workout_sets (workout_date, exercise_id, set_number, reps, weight_lbs)
            SELECT s.session_date, l.exercise_id, l.set_number, l.reps, l.weight_lbs
            FROM workout_sets_legacy l
            JOIN workout_sessions s ON s.id = l.session_id
            ORDER BY s.session_date, l.exercise_id, l.set_number;
            """
        )
        rows = cur.rowcount
        print(f"Re-inserted {rows} rows into the new workout_sets.")

        # 4) Drop legacy structures only after the new table is populated.
        cur.execute("DROP TABLE workout_sets_legacy;")
        cur.execute("DROP TABLE workout_sessions;")

        conn.commit()
        print("Migration complete. Backups remain in place — drop them manually when satisfied.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        release_conn(conn)


if __name__ == "__main__":
    migrate()
