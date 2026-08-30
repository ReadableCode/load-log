# %%
"""Real-PostgREST conformance tests (I10).

Exercises the path the app actually uses: log in to the shared auth service for
a JWT, then read through PostgREST over HTTP. No mocks and no skip path — an
unreachable dependency is a red test.

Read-only. Every request here is a GET; nothing writes.
"""

# %%
# Imports #

import os

import pytest
import requests

import api_client

# %%
# Fixtures #

TIMEOUT = 15


@pytest.fixture(scope="module")
def token():
    username = os.environ.get("LOAD_LOG_USERNAME")
    password = os.environ.get("LOAD_LOG_PASSWORD")
    assert username and password, (
        "LOAD_LOG_USERNAME / LOAD_LOG_PASSWORD are not set. These tests log in for "
        "real by design — set them in .env rather than skipping."
    )
    return api_client.login(username, password)


# %%
# Auth #


def test_login_returns_a_jwt(token):
    """Three dot-separated segments is the shape, not the signature — verifying
    the signature would need the shared secret, which the app deliberately does
    not hold."""
    assert token.count(".") == 2, "auth service did not return a JWT"


def test_login_rejects_a_bad_password():
    with pytest.raises(requests.HTTPError) as exc:
        api_client.login("definitely-not-a-real-user", "definitely-not-the-password")
    # 401 unauthorized, or 429 if the service's brute-force lockout has tripped
    # from a previous run — both mean the credential was not accepted.
    assert exc.value.response.status_code in (401, 429)


# %%
# Data access #


@pytest.mark.parametrize(
    "table", ["habits", "habit_completions", "exercises", "workout_sets"]
)
def test_data_tables_are_readable(token, table):
    resp = requests.get(
        f"{api_client.POSTGREST_URL}/{table}?limit=1",
        headers=api_client._headers(token),
        timeout=TIMEOUT,
    )
    assert resp.status_code == 200, f"{table}: {resp.status_code} {resp.text[:200]}"
    assert isinstance(resp.json(), list)


def test_requests_pin_the_schema(token):
    """I9: the client must send Accept-Profile rather than relying on load_log
    being first in the server's PGRST_DB_SCHEMAS."""
    headers = api_client._headers(token)
    assert headers["Accept-Profile"] == api_client.APP_SCHEMA
    write_headers = api_client._headers(token, write=True)
    assert write_headers["Content-Profile"] == api_client.APP_SCHEMA


def test_habits_sort_order_is_exposed(token):
    """The column exists in the database (test_db_real) — this checks PostgREST's
    schema cache actually reloaded and serves it, which is the failure the
    NOTIFY at the end of bootstrap exists to prevent."""
    resp = requests.get(
        f"{api_client.POSTGREST_URL}/habits?select=id,name,sort_order&limit=1",
        headers=api_client._headers(token),
        timeout=TIMEOUT,
    )
    assert resp.status_code == 200, f"{resp.status_code} {resp.text[:200]}"


# %%
# Security posture #


def test_users_table_is_not_reachable_over_http(token):
    """I4: there must be no PostgREST path to a password hash, even with a valid
    JWT. The database-side revoke is checked in test_db_real.py; this is the one
    that would catch a grant sneaking back in."""
    resp = requests.get(
        f"{api_client.POSTGREST_URL}/users?limit=1",
        headers=api_client._headers(token),
        timeout=TIMEOUT,
    )
    assert (
        resp.status_code != 200
    ), f"load_log.users is readable through PostgREST: {resp.text[:200]}"
    assert "password_hash" not in resp.text


def test_anonymous_requests_get_nothing(token):
    """web_anon holds no grant on any load_log table, so an unauthenticated read
    must fail rather than return rows."""
    resp = requests.get(
        f"{api_client.POSTGREST_URL}/habits?limit=1",
        headers={"Accept-Profile": api_client.APP_SCHEMA},
        timeout=TIMEOUT,
    )
    assert resp.status_code != 200, f"habits readable anonymously: {resp.text[:200]}"
