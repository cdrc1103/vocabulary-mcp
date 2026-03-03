"""Unit and HTTP integration tests for the vocabulary MCP server."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# conftest sets env vars before this import
import server as srv
from starlette.testclient import TestClient

MCP_AUTH = {"Authorization": "Bearer test-mcp-secret"}


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


class TestToolRegistration:
    def test_add_vocabulary_tool_registered(self):
        tools = asyncio.run(srv.mcp.list_tools())
        assert any(t.name == "add_vocabulary" for t in tools)

    def test_schema_requires_word_and_definition(self):
        tools = asyncio.run(srv.mcp.list_tools())
        tool = next(t for t in tools if t.name == "add_vocabulary")
        assert "word" in tool.inputSchema["required"]
        assert "definition" in tool.inputSchema["required"]

    def test_schema_optional_fields_present(self):
        tools = asyncio.run(srv.mcp.list_tools())
        tool = next(t for t in tools if t.name == "add_vocabulary")
        props = tool.inputSchema["properties"]
        assert "example" in props
        assert "language" in props


# ---------------------------------------------------------------------------
# add_vocabulary function
# ---------------------------------------------------------------------------


def _make_response(status_code: int, json_body: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_body,
        request=httpx.Request("POST", "http://test-backend/vocabulary"),
    )


class TestAddVocabularySuccess:
    def test_returns_confirmation_message(self):
        fake = _make_response(201, {"word": "bonjour", "next_review": "2026-03-10"})
        with patch.object(srv._http_client, "post", new=AsyncMock(return_value=fake)):
            result = asyncio.run(srv.add_vocabulary("bonjour", "hello"))
        assert "bonjour" in result

    def test_includes_next_review_date(self):
        fake = _make_response(201, {"word": "ciao", "next_review": "2026-03-10"})
        with patch.object(srv._http_client, "post", new=AsyncMock(return_value=fake)):
            result = asyncio.run(srv.add_vocabulary("ciao", "bye"))
        assert "2026-03-10" in result

    def test_forwards_optional_example(self):
        fake = _make_response(201, {"word": "merci", "next_review": "2026-03-10"})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.add_vocabulary("merci", "thanks", example="Merci beaucoup."))
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["example"] == "Merci beaucoup."

    def test_forwards_optional_language(self):
        fake = _make_response(201, {"word": "oui", "next_review": "2026-03-10"})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.add_vocabulary("oui", "yes", language="French"))
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["language"] == "French"

    def test_uses_correct_api_key_header(self):
        fake = _make_response(201, {"word": "test", "next_review": "2026-03-10"})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.add_vocabulary("test", "d"))
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["X-API-Key"] == "test-key"

    def test_none_example_not_forwarded(self):
        fake = _make_response(201, {"word": "hi", "next_review": "2026-03-10"})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.add_vocabulary("hi", "greeting"))
        _, kwargs = mock_post.call_args
        assert "example" not in kwargs["json"]

    def test_none_language_not_forwarded(self):
        fake = _make_response(201, {"word": "hi", "next_review": "2026-03-10"})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.add_vocabulary("hi", "greeting"))
        _, kwargs = mock_post.call_args
        assert "language" not in kwargs["json"]


class TestAddVocabularyErrors:
    def test_http_error_returns_error_message(self):
        error_resp = _make_response(400, {"detail": "bad request"})
        with patch.object(
            srv._http_client,
            "post",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError("err", request=MagicMock(), response=error_resp)
            ),
        ):
            result = asyncio.run(srv.add_vocabulary("x", "y"))
        assert "Failed" in result
        assert "400" in result

    def test_network_error_returns_error_message(self):
        with patch.object(
            srv._http_client,
            "post",
            new=AsyncMock(side_effect=Exception("connection refused")),
        ):
            result = asyncio.run(srv.add_vocabulary("x", "y"))
        assert "Failed" in result


# ---------------------------------------------------------------------------
# HTTP auth middleware
# ---------------------------------------------------------------------------


class TestHTTPAuth:
    @pytest.fixture
    def client(self):
        return TestClient(srv.app, raise_server_exceptions=False)

    def test_health_no_auth_required(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_missing_auth_returns_401(self, client):
        r = client.post("/mcp")
        assert r.status_code == 401

    def test_wrong_token_returns_401(self, client):
        r = client.post("/mcp", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401

    def test_bearer_prefix_required(self, client):
        # Token without "Bearer " prefix should be rejected
        r = client.post("/mcp", headers={"Authorization": "test-mcp-secret"})
        assert r.status_code == 401

    def test_valid_token_passes_auth_layer(self, client):
        # Auth passes; MCP protocol rejects malformed body — but NOT 401
        r = client.post("/mcp", headers=MCP_AUTH)
        assert r.status_code != 401
