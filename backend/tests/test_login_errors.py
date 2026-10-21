# %%
"""How each client reports a failed login (web form message, TUI exit).

Bad credentials and a missing JWT secret go through the real login path; only
the lockout is faked, since tripping it for real takes five failed logins.
Read-only: a rejected login writes nothing, and the startup schema bootstrap
both clients run is stubbed out so these tests never converge anything.
"""

# %%
# Imports #

import os

import postgrest_auth
import pytest
from streamlit.testing.v1 import AppTest

import api_client
import bootstrap
import config
from tui import app as tui_app

# %%
# Helpers #

WEB_APP = os.path.join(os.path.dirname(api_client.__file__), "web", "app.py")


@pytest.fixture(autouse=True)
def no_bootstrap(monkeypatch):
    monkeypatch.setattr(bootstrap, "bootstrap_best_effort", lambda: None)


def _submit_web_login(username: str, password: str) -> list[str]:
    at = AppTest.from_file(WEB_APP, default_timeout=30).run()
    at.text_input[0].input(username)
    at.text_input[1].input(password)
    at.button[0].click().run()
    assert not at.exception, at.exception
    return [e.value for e in at.error]


# %%
# Web #


def test_web_shows_invalid_credentials():
    errors = _submit_web_login("not-a-real-web-user", "not-the-password")
    assert errors == ["Invalid username or password."]


def test_web_shows_the_lockout_message(monkeypatch):
    def locked(*args, **kwargs):
        raise postgrest_auth.LoginLocked(150)

    monkeypatch.setattr(api_client, "login", locked)
    errors = _submit_web_login("anyone", "anything")
    assert errors == ["too many attempts — locked for 3 more minute(s)"]


def test_web_shows_unavailable_when_the_secret_is_missing(monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET", "")
    errors = _submit_web_login("anyone", "anything")
    assert errors == ["Login is unavailable. Try again shortly."]


# %%
# TUI #


def test_tui_exits_with_the_cause(monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET", "")
    monkeypatch.setenv("LOAD_LOG_USERNAME", "anyone")
    monkeypatch.setenv("LOAD_LOG_PASSWORD", "anything")
    with pytest.raises(SystemExit) as exc:
        tui_app.main()
    assert str(exc.value) == (
        "Login failed: POSTGREST_JWT_SECRET (or JWT_SECRET) is not set"
    )
