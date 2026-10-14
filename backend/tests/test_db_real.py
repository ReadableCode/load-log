# %%
"""Real-database conformance tests (I10).

These query the actual Postgres instance over the superuser connection. There is
deliberately no skip path: an unreachable database is a red test, never a green
one, because a suite that quietly skips is indistinguishable from a suite that
passes and tells you nothing.

Read-only. Nothing here creates, mutates, or drops anything — running the suite
against production is safe, and is the point.
"""

# %%
# Imports #

import psycopg2
import pytest

import bootstrap
import config

# %%
# Fixtures #


@pytest.fixture(scope="module")
def cur():
    assert bootstrap.db_configured(), (
        "POSTGRES_* env is not set. These tests hit a real database by design — "
        "point .env at the shared instance rather than skipping them."
    )
    conn = psycopg2.connect(bootstrap.superuser_dsn(), connect_timeout=10)
    conn.set_session(readonly=True)
    try:
        with conn.cursor() as c:
            yield c
    finally:
        conn.close()


# %%
# Schema shape #


def test_schema_exists(cur):
    cur.execute(
        "SELECT 1 FROM information_schema.schemata WHERE schema_name = 'load_log'"
    )
    assert cur.fetchone() is not None, "the load_log schema is missing"


@pytest.mark.parametrize(
    "table", ["habits", "habit_completions", "exercises", "workout_sets", "users"]
)
def test_table_exists(cur, table):
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'load_log' AND table_name = %s",
        (table,),
    )
    assert cur.fetchone() is not None, f"load_log.{table} is missing"


def test_users_has_the_standard_auth_shape(cur):
    """The shared postgrest-auth service selects role and disabled at login, and
    session validation compares a token's iat against password_changed_at. A
    missing column here breaks login for the whole app, so it is asserted rather
    than assumed."""
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'load_log' AND table_name = 'users'"
    )
    present = {row[0] for row in cur.fetchall()}
    expected = {
        "id",
        "username",
        "password_hash",
        "role",
        "display_name",
        "disabled",
        "created_at",
        "password_changed_at",
    }
    assert (
        expected <= present
    ), f"load_log.users is missing {sorted(expected - present)}"


def test_habits_has_sort_order(cur):
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'load_log' AND table_name = 'habits' "
        "AND column_name = 'sort_order'"
    )
    assert cur.fetchone() is not None


# %%
# Bootstrap bookkeeping #


def test_deploy_meta_is_stamped_at_the_current_version(cur):
    """Version-gating is what makes bootstrap a no-op on every boot after the
    first (I6). An unstamped database means it re-runs the SQL every start."""
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'load_log' AND table_name = 'deploy_meta'"
    )
    assert (
        cur.fetchone() is not None
    ), "load_log.deploy_meta is missing — the app has not bootstrapped this database"
    cur.execute("SELECT version FROM load_log.deploy_meta")
    rows = cur.fetchall()
    assert len(rows) == 1, f"deploy_meta should hold exactly one row, found {len(rows)}"
    assert rows[0][0] == bootstrap.SCHEMA_VERSION


# %%
# Security posture #


def test_credentials_are_unreachable_through_postgrest_roles(cur):
    """I4: load_log.users must have no grant to any PostgREST-facing role. This
    is the database-side half; test_postgrest_real.py checks it over HTTP."""
    cur.execute(
        "SELECT grantee, privilege_type FROM information_schema.role_table_grants "
        "WHERE table_schema = 'load_log' AND table_name = 'users' "
        "AND grantee IN ('load_log_user', 'web_anon')"
    )
    leaked = cur.fetchall()
    assert leaked == [], f"load_log.users is exposed to a PostgREST role: {leaked}"


def test_app_role_can_reach_the_data_tables(cur):
    """The mirror of the test above — revoking too much is just as broken as
    revoking too little, and shows up as a 401 on every request."""
    cur.execute(
        "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
        "WHERE table_schema = 'load_log' AND grantee = 'load_log_user'"
    )
    grants = {(t, p) for t, p in cur.fetchall()}
    for table in ("habits", "habit_completions", "exercises", "workout_sets"):
        for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            assert (table, priv) in grants, f"load_log_user lacks {priv} on {table}"


def test_app_role_cannot_log_in(cur):
    """I3: load_log_user is NOLOGIN and holds no password. PostgREST SET ROLEs
    into it from the JWT; a LOGIN role with a password would make the app the
    security boundary instead of the database."""
    cur.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname = 'load_log_user'")
    row = cur.fetchone()
    assert row is not None, "load_log_user role is missing"
    assert row[0] is False, "load_log_user must be NOLOGIN"


def test_cluster_roles_exist(cur):
    """Bootstrap asserts these rather than creating them — they are cluster-wide
    and created by the postgres-cluster-roles service in the Docker repo
    (Docker/postgres/cluster_roles.sql), which every app's bootstrap names in
    its error message."""
    cur.execute(
        "SELECT rolname FROM pg_roles WHERE rolname IN ('postgrest_authenticator', 'web_anon')"
    )
    assert {r[0] for r in cur.fetchall()} == {"postgrest_authenticator", "web_anon"}


# %%
# Sanity #


def test_connection_targets_the_shared_apps_database(cur):
    cur.execute("SELECT current_database()")
    assert cur.fetchone()[0] == config.POSTGRES_DB
