"""Tests for MCP server tools.

Tests vocabulary management tools and error handling.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

# conftest sets env vars before this import
import server as srv

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(status_code: int, json_body: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_body,
        request=httpx.Request("POST", "http://test-backend/vocabulary"),
    )


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
