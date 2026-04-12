"""Tests for MCP server tools.

Tests vocabulary management tools and error handling.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

# conftest sets env vars before this import
import server as srv

# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


class TestToolRegistration:
    def test_add_vocabulary_tool_registered(self):
        """Test that add_vocabulary tool is registered with MCP server."""
        tools = asyncio.run(srv.mcp.list_tools())
        assert any(t.name == "add_vocabulary" for t in tools)

    def test_schema_requires_word_and_definition(self):
        """Test that word and definition are required parameters."""
        tools = asyncio.run(srv.mcp.list_tools())
        tool = next(t for t in tools if t.name == "add_vocabulary")
        assert "word" in tool.inputSchema["required"]
        assert "definition" in tool.inputSchema["required"]

    def test_schema_optional_fields_present(self):
        """Test that optional fields (example, language) are in schema."""
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
        """Test add_vocabulary returns message containing the word."""
        fake = _make_response(201, {"word": "bonjour", "next_review": "2026-03-10"})
        with patch.object(srv._http_client, "post", new=AsyncMock(return_value=fake)):
            result = asyncio.run(srv.add_vocabulary("bonjour", "hello"))
        assert "bonjour" in result

    def test_includes_next_review_date(self):
        """Test response includes next review date for SRS scheduling."""
        fake = _make_response(201, {"word": "ciao", "next_review": "2026-03-10"})
        with patch.object(srv._http_client, "post", new=AsyncMock(return_value=fake)):
            result = asyncio.run(srv.add_vocabulary("ciao", "bye"))
        assert "2026-03-10" in result

    def test_forwards_optional_example(self):
        """Test optional example parameter is forwarded to backend."""
        fake = _make_response(201, {"word": "merci", "next_review": "2026-03-10"})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.add_vocabulary("merci", "thanks", example="Merci beaucoup."))
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["example"] == "Merci beaucoup."

    def test_forwards_optional_language(self):
        """Test optional language parameter is forwarded to backend."""
        fake = _make_response(201, {"word": "oui", "next_review": "2026-03-10"})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.add_vocabulary("oui", "yes", language="French"))
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["language"] == "French"

    def test_uses_correct_api_key_header(self):
        """Test API key is included in request headers."""
        fake = _make_response(201, {"word": "test", "next_review": "2026-03-10"})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.add_vocabulary("test", "d"))
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["X-API-Key"] == "test-key"

    def test_none_example_not_forwarded(self):
        """Test None example is not included in request body."""
        fake = _make_response(201, {"word": "hi", "next_review": "2026-03-10"})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.add_vocabulary("hi", "greeting"))
        _, kwargs = mock_post.call_args
        assert "example" not in kwargs["json"]

    def test_none_language_not_forwarded(self):
        """Test None language is not included in request body."""
        fake = _make_response(201, {"word": "hi", "next_review": "2026-03-10"})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.add_vocabulary("hi", "greeting"))
        _, kwargs = mock_post.call_args
        assert "language" not in kwargs["json"]


class TestAddVocabularyErrors:
    def test_http_error_returns_error_message(self):
        """Test HTTP error responses are converted to error messages."""
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
        """Test network errors are gracefully converted to error messages."""
        with patch.object(
            srv._http_client,
            "post",
            new=AsyncMock(side_effect=Exception("connection refused")),
        ):
            result = asyncio.run(srv.add_vocabulary("x", "y"))
        assert "Failed" in result


class TestBulkToolRegistration:
    def test_bulk_add_vocabulary_tool_registered(self):
        """Test that bulk_add_vocabulary tool is registered with MCP server."""
        tools = asyncio.run(srv.mcp.list_tools())
        assert any(t.name == "bulk_add_vocabulary" for t in tools)

    def test_bulk_schema_requires_words(self):
        """Test that words array with word and definition are required."""
        tools = asyncio.run(srv.mcp.list_tools())
        tool = next(t for t in tools if t.name == "bulk_add_vocabulary")
        schema = tool.inputSchema
        assert "words" in schema["required"]
        items = schema["properties"]["words"]["items"]
        # FastMCP may inline properties or use a $ref into $defs
        if "properties" in items:
            word_props = items["properties"]
        else:
            ref = items["$ref"].split("/")[-1]
            word_props = schema["$defs"][ref]["properties"]
        assert "word" in word_props
        assert "definition" in word_props
        # word and definition should be required in the item schema
        if "required" in items:
            item_required = items["required"]
        else:
            ref = items["$ref"].split("/")[-1]
            item_required = schema["$defs"][ref].get("required", [])
        assert "word" in item_required
        assert "definition" in item_required


class TestBulkAddVocabularySuccess:
    def test_returns_summary_message(self):
        """Test bulk add returns summary message with insertion count."""
        fake = _make_response(201, {"inserted": [{"word": "a"}, {"word": "b"}], "skipped_count": 0})
        with patch.object(srv._http_client, "post", new=AsyncMock(return_value=fake)):
            result = asyncio.run(
                srv.bulk_add_vocabulary(
                    [
                        {"word": "a", "definition": "a"},
                        {"word": "b", "definition": "b"},
                    ]
                )
            )
        assert "2" in result
        assert "Saved" in result

    def test_reports_skipped_duplicates(self):
        """Test bulk add reports duplicates/skipped words."""
        fake = _make_response(201, {"inserted": [{"word": "b"}], "skipped_count": 1})
        with patch.object(srv._http_client, "post", new=AsyncMock(return_value=fake)):
            result = asyncio.run(
                srv.bulk_add_vocabulary(
                    [
                        {"word": "a", "definition": "a"},
                        {"word": "b", "definition": "b"},
                    ]
                )
            )
        assert "1" in result and ("skip" in result.lower() or "duplicate" in result.lower())

    def test_calls_bulk_endpoint(self):
        """Test bulk add calls /vocabulary/bulk endpoint."""
        fake = _make_response(201, {"inserted": [], "skipped_count": 0})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.bulk_add_vocabulary([{"word": "x", "definition": "y"}]))
        args, kwargs = mock_post.call_args
        assert "/vocabulary/bulk" in args[0]

    def test_uses_correct_api_key_header(self):
        """Test API key is included in bulk endpoint request."""
        fake = _make_response(201, {"inserted": [], "skipped_count": 0})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.bulk_add_vocabulary([{"word": "x", "definition": "y"}]))
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["X-API-Key"] == "test-key"


class TestBulkAddVocabularyErrors:
    def test_http_error_returns_error_message(self):
        """Test bulk add HTTP errors are converted to error messages."""
        error_resp = _make_response(422, {"detail": "too many words"})
        with patch.object(
            srv._http_client,
            "post",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError("err", request=MagicMock(), response=error_resp)
            ),
        ):
            result = asyncio.run(srv.bulk_add_vocabulary([{"word": "x", "definition": "y"}]))
        assert "Failed" in result
        assert "422" in result

    def test_network_error_returns_error_message(self):
        """Test bulk add network errors are gracefully converted."""
        with patch.object(
            srv._http_client,
            "post",
            new=AsyncMock(side_effect=Exception("connection refused")),
        ):
            result = asyncio.run(srv.bulk_add_vocabulary([{"word": "x", "definition": "y"}]))
        assert "Failed" in result


# ---------------------------------------------------------------------------
# HTTP auth middleware (covered by test_server_integration.py)
# ---------------------------------------------------------------------------
