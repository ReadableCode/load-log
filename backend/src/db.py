# %%
# Imports #

import psycopg2
from psycopg2 import pool
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from config import (
    POSTGRES_DB,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_URL,
    POSTGRES_USER,
)

# %%
# Pool #

_pool: pool.SimpleConnectionPool | None = None


def get_pool() -> pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            host=POSTGRES_URL,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            dbname=POSTGRES_DB,
            port=POSTGRES_PORT,
        )
    return _pool


def get_conn():
    return get_pool().getconn()


def release_conn(conn) -> None:
    get_pool().putconn(conn)


# %%
# Bootstrap #


def ensure_database_exists(dbname: str = POSTGRES_DB) -> None:
    conn = psycopg2.connect(
        host=POSTGRES_URL,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        dbname="postgres",
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    # Heal any glibc collation drift on the maintenance/template DBs before
    # we try to CREATE DATABASE (which copies from template1 and would fail
    # with a "collation version mismatch" if template1 is stale).
    cur.execute("ALTER DATABASE template1 REFRESH COLLATION VERSION;")
    cur.execute("ALTER DATABASE postgres  REFRESH COLLATION VERSION;")

    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (dbname,))
    if not cur.fetchone():
        cur.execute(f'CREATE DATABASE "{dbname}";')

    # Refresh the target DB too — covers the case where it was created earlier
    # under an older glibc and is now being opened by a newer one.
    cur.execute(f'ALTER DATABASE "{dbname}" REFRESH COLLATION VERSION;')

    cur.close()
    conn.close()


def ensure_tables() -> None:
    conn = get_conn()
    cur = conn.cursor()
    try:
        # NEVER drop tables here. If the schema has drifted (e.g. an old
        # `workout_sets.session_id` from before we collapsed sessions into a
        # date column), refuse to start and tell the caller to migrate
        # explicitly. Silent DROP TABLE in a bootstrap path is how user data
        # gets destroyed.
        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'workout_sets'
              AND column_name = 'session_id';
            """
        )
        if cur.fetchone():
            raise RuntimeError(
                "Legacy workout_sessions / workout_sets.session_id schema detected. "
                "Run backend/scripts/migrate_drop_sessions.py to migrate "
                "(it backs up workout_sets into workout_sets_backup_<timestamp>, "
                "rewrites the schema, and re-inserts the rows with a synthesized "
                "workout_date). Aborting startup to avoid data loss."
            )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS habits (
                id          SERIAL PRIMARY KEY,
                name        TEXT NOT NULL UNIQUE,
                created_at  DATE NOT NULL DEFAULT CURRENT_DATE
            );

            CREATE TABLE IF NOT EXISTS habit_completions (
                id              SERIAL PRIMARY KEY,
                habit_id        INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
                completed_date  DATE NOT NULL,
                UNIQUE (habit_id, completed_date)
            );

            CREATE TABLE IF NOT EXISTS exercises (
                id    SERIAL PRIMARY KEY,
                name  TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS workout_sets (
                id            SERIAL PRIMARY KEY,
                workout_date  DATE NOT NULL DEFAULT CURRENT_DATE,
                exercise_id   INTEGER NOT NULL REFERENCES exercises(id),
                set_number    INTEGER NOT NULL,
                reps          INTEGER NOT NULL,
                weight_lbs    REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS workout_sets_date_idx
                ON workout_sets (workout_date);
            """
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)


def bootstrap() -> None:
    ensure_database_exists()
    ensure_tables()


# %%
# Main #


if __name__ == "__main__":
    bootstrap()
    print(f"Database '{POSTGRES_DB}' and tables ensured.")
