"""Tests for OAuth database operations.

Tests client registration, authorization code storage, and token management.
"""

import json

import pytest
from database import (
    delete_auth_code,
    delete_expired_auth_codes,
    delete_expired_refresh_tokens,
    delete_refresh_token,
    get_auth_code,
    get_client,
    get_refresh_token,
    init_db,
    is_token_revoked,
    save_auth_code,
    save_client,
    save_refresh_token,
    save_revoked_token,
)


@pytest.fixture()
def db_path(tmp_path):
    """Initialize a temporary SQLite database for OAuth testing.

    Args:
        tmp_path: pytest temporary directory fixture.

    Yields:
        str: Path to the initialized test database.
    """
    path = str(tmp_path / "test_oauth.db")
    init_db(path)
    return path


class TestClientCRUD:
    def test_save_and_get_client(self, db_path):
        """Test saving and retrieving client registration."""
        client_info = {
            "client_id": "test-client-123",
            "client_secret": "secret-abc",
            "redirect_uris": ["http://localhost:3000/callback"],
            "client_name": "Test Client",
        }
        save_client(db_path, "test-client-123", "secret-abc", json.dumps(client_info))
        result = get_client(db_path, "test-client-123")
        assert result is not None
        assert result["client_id"] == "test-client-123"
        assert result["client_secret"] == "secret-abc"
        parsed = json.loads(result["client_info_json"])
        assert parsed["client_name"] == "Test Client"

    def test_get_nonexistent_client(self, db_path):
        """Test that querying nonexistent client returns None."""
        result = get_client(db_path, "nonexistent")
        assert result is None


class TestAuthCodeCRUD:
    def test_save_and_get_auth_code(self, db_path):
        """Test saving and retrieving authorization codes."""
        save_auth_code(
            db_path,
            code="code-123",
            client_id="client-1",
            code_challenge="challenge-abc",
            redirect_uri="http://localhost:3000/callback",
            redirect_uri_provided_explicitly=True,
            scopes_json='["read"]',
            expires_at=9999999999.0,
            resource=None,
        )
        result = get_auth_code(db_path, "code-123")
        assert result is not None
        assert result["client_id"] == "client-1"
        assert result["code_challenge"] == "challenge-abc"

    def test_get_nonexistent_auth_code(self, db_path):
        """Test that querying nonexistent auth code returns None."""
        assert get_auth_code(db_path, "nonexistent") is None

    def test_delete_auth_code(self, db_path):
        """Test deletion of authorization codes."""
        save_auth_code(
            db_path,
            code="code-del",
            client_id="client-1",
            code_challenge="ch",
            redirect_uri="http://localhost/cb",
            redirect_uri_provided_explicitly=True,
            scopes_json="[]",
            expires_at=9999999999.0,
            resource=None,
        )
        delete_auth_code(db_path, "code-del")
        assert get_auth_code(db_path, "code-del") is None

    def test_delete_expired_auth_codes(self, db_path):
        """Test cleanup of expired authorization codes while keeping valid ones."""
        save_auth_code(
            db_path,
            code="expired",
            client_id="c1",
            code_challenge="ch",
            redirect_uri="http://localhost/cb",
            redirect_uri_provided_explicitly=True,
            scopes_json="[]",
            expires_at=1.0,
            resource=None,
        )
        save_auth_code(
            db_path,
            code="valid",
            client_id="c1",
            code_challenge="ch",
            redirect_uri="http://localhost/cb",
            redirect_uri_provided_explicitly=True,
            scopes_json="[]",
            expires_at=9999999999.0,
            resource=None,
        )
        delete_expired_auth_codes(db_path)
        assert get_auth_code(db_path, "expired") is None
        assert get_auth_code(db_path, "valid") is not None


class TestRefreshTokenCRUD:
    def test_save_and_get_refresh_token(self, db_path):
        """Test saving and retrieving refresh tokens."""
        save_refresh_token(
            db_path,
            token="rt-123",
            client_id="client-1",
            scopes_json='["read"]',
            expires_at=9999999999,
        )
        result = get_refresh_token(db_path, "rt-123")
        assert result is not None
        assert result["client_id"] == "client-1"

    def test_get_nonexistent_refresh_token(self, db_path):
        """Test that querying nonexistent refresh token returns None."""
        assert get_refresh_token(db_path, "nonexistent") is None

    def test_delete_refresh_token(self, db_path):
        """Test deletion of refresh tokens."""
        save_refresh_token(db_path, "rt-del", "c1", "[]", 9999999999)
        delete_refresh_token(db_path, "rt-del")
        assert get_refresh_token(db_path, "rt-del") is None

    def test_delete_expired_refresh_tokens(self, db_path):
        """Test cleanup of expired refresh tokens while keeping valid ones."""
        save_refresh_token(db_path, "expired", "c1", "[]", 1)
        save_refresh_token(db_path, "valid", "c1", "[]", 9999999999)
        delete_expired_refresh_tokens(db_path)
        assert get_refresh_token(db_path, "expired") is None
        assert get_refresh_token(db_path, "valid") is not None


class TestRevokedTokens:
    def test_save_and_check_revoked(self, db_path):
        """Test marking and checking revoked tokens."""
        assert not is_token_revoked(db_path, "jti-123")
        save_revoked_token(db_path, "jti-123")
        assert is_token_revoked(db_path, "jti-123")

    def test_not_revoked(self, db_path):
        """Test that unrevoked tokens are not marked as revoked."""
        assert not is_token_revoked(db_path, "jti-never")
