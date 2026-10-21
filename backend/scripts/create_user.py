# %%
"""Insert a user into load_log.users with an argon2id password hash.

Converges the schema first (bootstrap.apply_schema, a no-op once it is current),
like every other way of starting load-log. The web app only converges when its
page is first opened, so without this the first account on a fresh database
would fail on a missing load_log.users. Login reads this table over the app's
superuser connection (postgrest-auth library) to verify credentials and mint
JWTs. The hash comes from the same library: argon2id is the standard;
pre-existing bcrypt rows keep verifying and get rehashed on the next successful
login.

Run:
    cd backend && uv run python scripts/create_user.py --username jason --password 'hunter2'

Reads the POSTGRES_* env vars (same ones config.py uses, including the repo
.env it loads). Besides the schema convergence it writes a single row via
parameterized SQL, no other mutation. If the username already exists (UNIQUE
violation) it reports and exits non-zero rather than overwriting.
"""

# %%
# Imports #

import argparse
import os
import sys

import postgrest_auth
import psycopg2

# allow `uv run python scripts/create_user.py` from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import bootstrap  # noqa: E402  (side effect: config loads the repo .env)

# %%
# Config #

POSTGRES_URL = os.environ.get("POSTGRES_URL", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "apps")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")


# %%
# Create #


def create_user(username: str, password: str) -> None:
    password_hash = postgrest_auth.hash_password(password)

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
    parser.add_argument(
        "--password",
        required=True,
        help="Plaintext password (argon2id-hashed before storage)",
    )
    args = parser.parse_args()
    bootstrap.apply_schema()
    create_user(args.username, args.password)


if __name__ == "__main__":
    main()
