import pytest


@pytest.fixture
def app_client():
    from fastapi.testclient import TestClient
    from api import app
    return TestClient(app)
