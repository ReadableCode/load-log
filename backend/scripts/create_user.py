# %%
"""Insert a user into load_log.users with a bcrypt password hash.

Run AFTER the users table exists (alembic migration 0002). The auth service
reads this table to validate credentials and issue JWTs.

Run:
    cd backend && uv run python scripts/create_user.py --username jason --password 'hunter2'

Reads the POSTGRES_* env vars (same ones config.py / db.py use). Writes a single
row via parameterized SQL — no other mutation. If the username already exists
(UNIQUE violation) it reports and exits non-zero rather than overwriting.
"""
# %%
# Imports #

import argparse
import os
import sys

import bcrypt
import psycopg2

# allow `uv run python scripts/create_user.py` from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# %%
# Config #

POSTGRES_URL = os.environ.get("POSTGRES_URL", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "load_log")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")


# %%
# Create #


def create_user(username: str, password: str) -> None:
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = psycopg2.connect(
        host=POSTGRES_URL,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO load_log.users (username, password_hash)
                VALUES (%s, %s)
                RETURNING id;
                """,
                (username, password_hash),
            )
            new_id = cur.fetchone()[0]
        print(f"Created user '{username}' (id={new_id}).")
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        print(f"User '{username}' already exists. Nothing changed.", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


# %%
# Main #


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a load_log user.")
    parser.add_argument("--username", required=True, help="Login username")
    parser.add_argument("--password", required=True, help="Plaintext password (bcrypt-hashed before storage)")
    args = parser.parse_args()
    create_user(args.username, args.password)


if __name__ == "__main__":
    main()
