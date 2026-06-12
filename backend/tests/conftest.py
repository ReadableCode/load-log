# %%
# Imports #

import os

import pytest

# %%
# Test isolation #
#
# Force every test to use a dedicated `load_log_test` database. This file is
# imported by pytest before anything else, so the override is in place before
# config.py's module-level POSTGRES_DB is read by db.py. This guarantees that
# even an accidental `pytest` against the production DB host cannot touch
# `load_log` tables.

os.environ["POSTGRES_DB"] = os.environ.get("LOAD_LOG_TEST_DB", "load_log_test")


@pytest.fixture
def app_client():
    from fastapi.testclient import TestClient

    from api import app

    return TestClient(app)
