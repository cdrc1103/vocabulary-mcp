"""Pytest fixtures for backend API tests.

Provides test client, sample data, and database fixtures for all backend tests.
"""

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
    """Provide an isolated in-memory test database for each test.

    Patches the global DATABASE_PATH to a fresh temporary SQLite database
    and initializes it. Ensures test isolation by giving each test its own
    database instance.

    Args:
        monkeypatch: Pytest fixture for runtime patching.
        tmp_path: Pytest fixture providing a temporary directory.

    Returns:
        str: Path to the temporary SQLite database file.
    """
    db_path = str(tmp_path / "test.db")
    import database as db_module

    monkeypatch.setattr(db_module, "DATABASE_PATH", db_path)
    db_module.init_db()
    return db_path


@pytest.fixture()
def client(tmp_db):
    """Provide a FastAPI TestClient with isolated database.

    Creates a TestClient connected to the FastAPI app using an isolated
    test database. This allows for end-to-end testing of API endpoints
    without affecting persistent data.

    Args:
        tmp_db: Fixture providing isolated temporary database.

    Yields:
        TestClient: FastAPI test client ready for making requests.
    """
    from main import app

    with TestClient(app) as c:
        yield c
