"""Tests for OAuth provider implementation.

Tests authorization code grant flow, client registration, and token issuance.
"""

import pytest
from database import init_db
from oauth_provider import VocabularyOAuthProvider

ACCESS_TOKEN_EXPIRY = 3600
REFRESH_TOKEN_EXPIRY = 30 * 24 * 3600


@pytest.fixture()
def db_path(tmp_path):
    """Initialize a temporary SQLite database for OAuth provider testing.

    Args:
        tmp_path: pytest temporary directory fixture.

    Yields:
        str: Path to the initialized test database.
    """
    path = str(tmp_path / "test_oauth.db")
    init_db(path)
    return path


@pytest.fixture()
def provider(db_path):
    """Create a VocabularyOAuthProvider instance for testing.

    Args:
        db_path: Path to the test database.

    Yields:
        VocabularyOAuthProvider: Configured OAuth provider instance.
    """
    return VocabularyOAuthProvider(
        db_path=db_path,
        secret="test-secret-key-for-jwt-signing",
        issuer_url="https://mcp.example.com",
    )


@pytest.fixture()
def sample_client_metadata():
    """Create sample OAuth client metadata for registration testing.

    Yields:
        OAuthClientInformationFull: Pre-configured client metadata.
    """
    from mcp.shared.auth import OAuthClientInformationFull

    return OAuthClientInformationFull(
        redirect_uris=["http://localhost:3000/callback"],
        client_name="Test Client",
        token_endpoint_auth_method="client_secret_post",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
    )


class TestClientRegistration:
    @pytest.mark.asyncio
    async def test_register_and_get_client(self, provider, sample_client_metadata):
        """Test OAuth client registration and retrieval."""
        await provider.register_client(sample_client_metadata)
        assert sample_client_metadata.client_id is not None
        assert sample_client_metadata.client_secret is not None
        retrieved = await provider.get_client(sample_client_metadata.client_id)
        assert retrieved is not None
        assert retrieved.client_id == sample_client_metadata.client_id
        assert retrieved.client_name == "Test Client"

    @pytest.mark.asyncio
    async def test_get_nonexistent_client(self, provider):
        """Test that retrieving nonexistent client returns None."""
        result = await provider.get_client("nonexistent")
        assert result is None


class TestAuthorizationCodeFlow:
    @pytest.mark.asyncio
    async def test_authorize_returns_login_url(self, provider, sample_client_metadata):
        """Test authorization endpoint returns login page URL."""
        from mcp.server.auth.provider import AuthorizationParams

        await provider.register_client(sample_client_metadata)
        params = AuthorizationParams(
            state="test-state",
            scopes=["read"],
            code_challenge="test-challenge",
            redirect_uri="http://localhost:3000/callback",
            redirect_uri_provided_explicitly=True,
        )
        url = await provider.authorize(sample_client_metadata, params)
        assert "/authorize/submit" in url
        assert "auth_params" in url

    @pytest.mark.asyncio
    async def test_complete_auth_and_exchange_code(self, provider, sample_client_metadata):
        """Test complete authorization code flow from authorization to token exchange.

        Verifies authorization code generation, loading, and single-use consumption.
        """
        from mcp.server.auth.provider import AuthorizationParams

        await provider.register_client(sample_client_metadata)
        params = AuthorizationParams(
            state="test-state",
            scopes=None,
            code_challenge="test-challenge",
            redirect_uri="http://localhost:3000/callback",
            redirect_uri_provided_explicitly=True,
        )
        await provider.authorize(sample_client_metadata, params)
        redirect_url = provider.complete_authorization(sample_client_metadata, params)
        assert "code=" in redirect_url
        from urllib.parse import parse_qs, urlparse

        code = parse_qs(urlparse(redirect_url).query)["code"][0]
        auth_code = await provider.load_authorization_code(sample_client_metadata, code)
        assert auth_code is not None
        assert auth_code.code == code
        token = await provider.exchange_authorization_code(sample_client_metadata, auth_code)
        assert token.access_token is not None
        assert token.refresh_token is not None
        assert token.token_type == "Bearer"
        assert token.expires_in == ACCESS_TOKEN_EXPIRY
        # Code consumed (single-use)
        assert await provider.load_authorization_code(sample_client_metadata, code) is None


class TestTokenVerification:
    @pytest.mark.asyncio
    async def test_load_valid_access_token(self, provider, sample_client_metadata):
        """Test loading and verifying valid access tokens."""
        from mcp.server.auth.provider import AuthorizationParams

        await provider.register_client(sample_client_metadata)
        params = AuthorizationParams(
            state=None,
            scopes=None,
            code_challenge="ch",
            redirect_uri="http://localhost:3000/callback",
            redirect_uri_provided_explicitly=True,
        )
        await provider.authorize(sample_client_metadata, params)
        redirect_url = provider.complete_authorization(sample_client_metadata, params)
        from urllib.parse import parse_qs, urlparse

        code = parse_qs(urlparse(redirect_url).query)["code"][0]
        auth_code = await provider.load_authorization_code(sample_client_metadata, code)
        token = await provider.exchange_authorization_code(sample_client_metadata, auth_code)
        access_info = await provider.load_access_token(token.access_token)
        assert access_info is not None
        assert access_info.client_id == sample_client_metadata.client_id

    @pytest.mark.asyncio
    async def test_load_invalid_access_token(self, provider):
        """Test that invalid access tokens return None."""
        result = await provider.load_access_token("invalid-token")
        assert result is None


class TestRefreshTokenFlow:
    @pytest.mark.asyncio
    async def test_refresh_token_exchange(self, provider, sample_client_metadata):
        """Test refresh token exchange and rotation.

        Verifies that old refresh token is rotated out after exchange.
        """
        from mcp.server.auth.provider import AuthorizationParams

        await provider.register_client(sample_client_metadata)
        params = AuthorizationParams(
            state=None,
            scopes=None,
            code_challenge="ch",
            redirect_uri="http://localhost:3000/callback",
            redirect_uri_provided_explicitly=True,
        )
        await provider.authorize(sample_client_metadata, params)
        redirect_url = provider.complete_authorization(sample_client_metadata, params)
        from urllib.parse import parse_qs, urlparse

        code = parse_qs(urlparse(redirect_url).query)["code"][0]
        auth_code = await provider.load_authorization_code(sample_client_metadata, code)
        token = await provider.exchange_authorization_code(sample_client_metadata, auth_code)
        rt = await provider.load_refresh_token(sample_client_metadata, token.refresh_token)
        assert rt is not None
        new_token = await provider.exchange_refresh_token(sample_client_metadata, rt, [])
        assert new_token.access_token is not None
        assert new_token.refresh_token is not None
        # Old refresh token rotated
        assert (
            await provider.load_refresh_token(sample_client_metadata, token.refresh_token) is None
        )


class TestTokenRevocation:
    @pytest.mark.asyncio
    async def test_revoke_access_token(self, provider, sample_client_metadata):
        """Test token revocation and blocklist enforcement."""
        from mcp.server.auth.provider import AuthorizationParams

        await provider.register_client(sample_client_metadata)
        params = AuthorizationParams(
            state=None,
            scopes=None,
            code_challenge="ch",
            redirect_uri="http://localhost:3000/callback",
            redirect_uri_provided_explicitly=True,
        )
        await provider.authorize(sample_client_metadata, params)
        redirect_url = provider.complete_authorization(sample_client_metadata, params)
        from urllib.parse import parse_qs, urlparse

        code = parse_qs(urlparse(redirect_url).query)["code"][0]
        auth_code = await provider.load_authorization_code(sample_client_metadata, code)
        token = await provider.exchange_authorization_code(sample_client_metadata, auth_code)
        access_info = await provider.load_access_token(token.access_token)
        assert access_info is not None
        await provider.revoke_token(access_info)
        assert await provider.load_access_token(token.access_token) is None
