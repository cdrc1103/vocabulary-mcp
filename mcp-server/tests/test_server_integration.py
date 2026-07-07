"""Integration tests for MCP server.

Tests end-to-end OAuth flows and vocabulary API integration.
"""

import os

# Set env vars BEFORE importing server modules
os.environ["MCP_SECRET"] = "integration-test-secret-32bytes!"
os.environ["VOCAB_API_KEY"] = "test-api-key"
os.environ["ISSUER_URL"] = "http://localhost:8080"

import pytest
from starlette.testclient import TestClient


@pytest.fixture()
def client(tmp_path):
    """Create test HTTP client for MCP server integration testing.

    Reloads server modules to pick up test environment variables.

    Args:
        tmp_path: pytest temporary directory fixture.

    Yields:
        TestClient: Starlette test client for the MCP HTTP server.
    """
    os.environ["DATABASE_PATH"] = str(tmp_path / "test_oauth.db")

    import importlib

    import database
    import oauth_provider
    import server

    importlib.reload(database)
    importlib.reload(oauth_provider)
    importlib.reload(server)

    return TestClient(server.mcp.streamable_http_app())


class TestHealthEndpoint:
    def test_health_no_auth_required(self, client):
        """Test health endpoint is accessible without authentication."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestOAuthMetadata:
    def test_well_known_oauth_metadata(self, client):
        """Test OAuth authorization server metadata is correctly advertised."""
        response = client.get("/.well-known/oauth-authorization-server")
        assert response.status_code == 200
        data = response.json()
        assert "authorization_endpoint" in data
        assert "token_endpoint" in data
        assert "registration_endpoint" in data
        assert data["code_challenge_methods_supported"] == ["S256"]

    def test_protected_resource_metadata(self, client):
        """Test protected resource metadata is available for clients."""
        # FastMCP may serve this at a path derived from resource_server_url;
        # try the standard path first, fall back to the issuer-suffixed variant.
        response = client.get("/.well-known/oauth-protected-resource")
        if response.status_code == 404:
            response = client.get("/.well-known/oauth-protected-resource/http://localhost:8080")
        assert response.status_code == 200
        data = response.json()
        assert "resource" in data
        assert "authorization_servers" in data


class TestDCR:
    def test_register_client(self, client):
        """Test Dynamic Client Registration (DCR) endpoint."""
        response = client.post(
            "/register",
            json={
                "redirect_uris": ["http://localhost:3000/callback"],
                "client_name": "Test MCP Client",
                "token_endpoint_auth_method": "client_secret_post",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "client_id" in data
        assert "client_secret" in data


class TestMCPEndpointRequiresAuth:
    def test_mcp_endpoint_returns_401_without_token(self, client):
        """Test MCP endpoint requires authentication."""
        response = client.get("/mcp")
        # FastMCP may return 401 or 403 for unauthenticated requests
        assert response.status_code in (401, 403)


class TestLoginPage:
    def test_login_page_renders(self, client):
        """Test login page renders at authorization submission endpoint."""
        response = client.get("/authorize/submit?auth_params=test-nonce")
        assert response.status_code == 200
        assert "Password" in response.text
        assert "Sign In" in response.text
