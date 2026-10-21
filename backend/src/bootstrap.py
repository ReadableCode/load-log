# %%
"""App-owned DB bootstrap — the fleet pattern (Solitaire_Associations is the
reference implementation).

Runs from the app's own startup path, never the docker entrypoint (I6). That
distinction is the whole point: an entrypoint migration only fires when the
container starts, so a bare `streamlit run`, the TUI on a laptop, or a test run
would all execute code against a schema nobody converged. Every way of starting
load-log now goes through here.

Converges the `load_log` schema inside the shared `apps` database, version-gated
on `load_log.deploy_meta`, so it is a no-op on every boot after the first. Only
additive, idempotent statements live in the SQL files (I7). Failures are logged
and the app serves anyway — the next boot retries.

This replaced Alembic at SCHEMA_VERSION 1. Bump SCHEMA_VERSION when you add a
numbered file to SCHEMA_FILES.
"""

# %%
# Imports #

import logging
import os

import psycopg2

import config

# %%
# Config #

log = logging.getLogger("load_log.bootstrap")

SCHEMA_FILES = ("02_schema.sql", "03_secure_users.sql")
SCHEMA_VERSION = 1


def _find_deploy_dir() -> str:
    """Locate deploy/ by walking up from this file.

    A fixed number of os.path.dirname() calls does not work: in the repo this
    file is at backend/src/bootstrap.py with deploy/ three levels up, but the
    image flattens backend/ away (src/ lands at /app/src, deploy/ at
    /app/deploy) so it is two. Searching for the marker file gets both right,
    and any future move as well.
    """
    cur = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        candidate = os.path.join(cur, "deploy")
        if os.path.isfile(os.path.join(candidate, SCHEMA_FILES[0])):
            return candidate
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    raise RuntimeError(
        f"could not locate deploy/{SCHEMA_FILES[0]} above {os.path.abspath(__file__)}"
    )


# The app role PostgREST SET ROLEs into, from the JWT's `role` claim. NOLOGIN and
# passwordless (I3) — the database is the security boundary, not the app.
#
# postgrest_authenticator and web_anon are deliberately NOT created here. They
# are cluster-wide, shared by every app on this instance, and created by the
# postgres-cluster-roles service in the Docker repo (Docker/postgres/cluster_roles.sql).
# Bootstrap asserts they exist and fails loudly if they do not.
ROLE_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'load_log_user') THEN
        CREATE ROLE load_log_user NOLOGIN;
    END IF;
END $$;
GRANT load_log_user TO postgrest_authenticator;
"""


# %%
# Helpers #


def db_configured() -> bool:
    """True when the POSTGRES_* env is complete enough to attempt a connection.

    The superuser connection is one of the three permitted direct-to-Postgres
    paths (I2). Application data still moves only over PostgREST.
    """
    return bool(
        config.POSTGRES_USER and config.POSTGRES_PASSWORD and config.POSTGRES_DB
    )


def superuser_dsn() -> str:
    return (
        f"host={config.POSTGRES_URL} port={config.POSTGRES_PORT} "
        f"dbname={config.POSTGRES_DB} user={config.POSTGRES_USER} "
        f"password={config.POSTGRES_PASSWORD}"
    )


def _applied_version(cur) -> int | None:
    cur.execute("""SELECT 1 FROM information_schema.tables
           WHERE table_schema = 'load_log' AND table_name = 'deploy_meta'""")
    if cur.fetchone() is None:
        return None
    cur.execute("SELECT version FROM load_log.deploy_meta LIMIT 1")
    row = cur.fetchone()
    return row[0] if row else None


# %%
# Apply #


def apply_schema(force: bool = False) -> bool:
    """Converge the schema. Returns True when something was applied."""
    if not db_configured():
        log.warning("POSTGRES_* env missing — skipping schema bootstrap")
        return False

    conn = psycopg2.connect(superuser_dsn(), connect_timeout=10)
    try:
        with conn.cursor() as cur:
            if not force and _applied_version(cur) == SCHEMA_VERSION:
                log.info(
                    "schema already at version %s — nothing to apply", SCHEMA_VERSION
                )
                return False

            for role in ("postgrest_authenticator", "web_anon"):
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
                if cur.fetchone() is None:
                    raise RuntimeError(
                        f"cluster role {role!r} missing: compose.yaml creates it on Postgres's first start; "
                        "with your own Postgres, create it first (see compose.external.yaml). On the author's "
                        "server the Docker repo's postgres-cluster-roles service creates it "
                        "(Docker/postgres/cluster_roles.sql)"
                    )

            cur.execute(ROLE_SQL)
            deploy_dir = _find_deploy_dir()
            for name in SCHEMA_FILES:
                log.info("applying %s", name)
                with open(os.path.join(deploy_dir, name), "r", encoding="utf-8") as f:
                    cur.execute(f.read())

            cur.execute("""CREATE TABLE IF NOT EXISTS load_log.deploy_meta (
                       version integer NOT NULL,
                       applied_at timestamptz NOT NULL DEFAULT now()
                   )""")
            cur.execute("DELETE FROM load_log.deploy_meta")
            cur.execute(
                "INSERT INTO load_log.deploy_meta (version) VALUES (%s)",
                (SCHEMA_VERSION,),
            )
        conn.commit()

        # PostgREST caches the schema and only reloads on NOTIFY. Without this, a
        # boot that adds a column leaves the cache stale and PostgREST 400s
        # (PGRST204) any request naming it. NOTIFY fires on commit, so it needs
        # its own committed transaction after the DDL has landed.
        with conn.cursor() as cur:
            cur.execute("NOTIFY pgrst, 'reload schema'")
        conn.commit()
    finally:
        conn.close()

    log.info("schema converged to version %s", SCHEMA_VERSION)
    return True


def bootstrap_best_effort() -> None:
    """Converge, but never let a schema problem stop the app from serving.

    A database that is briefly unreachable at boot should not take the UI down;
    the next boot retries. Real data access still fails loudly (I8) — this only
    swallows the convergence step.
    """
    try:
        apply_schema()
    except Exception:
        log.exception("schema bootstrap failed — serving anyway, will retry next boot")


# %%
# Main #


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s"
    )
    apply_schema()
