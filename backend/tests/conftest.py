import os

# Must be set before any app module is imported
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("PWA_PASSWORD", "test-password")

import pytest
from fastapi.testclient import TestClient

TEST_API_KEY = "test-api-key"
TEST_PASSWORD = "test-password"
AUTH_HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture()
def tmp_db(monkeypatch, tmp_path):
    """Patch DATABASE_PATH to a fresh temp file for each test."""
    db_path = str(tmp_path / "test.db")
    import database as db_module

    monkeypatch.setattr(db_module, "DATABASE_PATH", db_path)
    db_module.init_db()
    return db_path


@pytest.fixture()
def client(tmp_db):
    """TestClient with a fresh isolated database."""
    from main import app

    with TestClient(app) as c:
        yield c
