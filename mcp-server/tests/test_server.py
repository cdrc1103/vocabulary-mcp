"""Tests for MCP server tools.

Tests vocabulary management tools and error handling.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# conftest sets env vars before this import
import server as srv
from pydantic import ValidationError

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

# ---------------------------------------------------------------------------
# session_name forwarding
# ---------------------------------------------------------------------------


class TestAddVocabularySession:
    def test_session_name_forwarded_to_api(self):
        """Test add_vocabulary passes session_name in request body."""
        fake = _make_response(
            201,
            {
                "id": 1,
                "word": "hola",
                "definition": "hello",
                "language": "es",
                "created_at": "2026-06-20 10:00:00",
                "next_review": "2026-06-20",
                "interval": 1,
                "ease_factor": 2.5,
                "repetitions": 0,
                "session_id": 2,
                "session_name": "Spanish 1",
            },
        )
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(
                srv.add_vocabulary(word="hola", definition="hello", session_name="Spanish 1")
            )
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["session_name"] == "Spanish 1"

    def test_none_session_name_sent_as_none(self):
        """Test add_vocabulary sends session_name=None when not specified."""
        fake = _make_response(
            201,
            {
                "id": 1,
                "word": "x",
                "definition": "y",
                "language": "unknown",
                "created_at": "2026-06-20 10:00:00",
                "next_review": "2026-06-20",
                "interval": 1,
                "ease_factor": 2.5,
                "repetitions": 0,
                "session_id": 1,
                "session_name": "misc",
            },
        )
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.add_vocabulary(word="x", definition="y"))
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["session_name"] is None


class TestBulkAddVocabularySession:
    def test_session_name_injected_into_all_words(self):
        """Test bulk_add_vocabulary injects session_name into each word when provided."""
        fake = _make_response(201, {"inserted": [], "skipped_count": 0})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(
                srv.bulk_add_vocabulary(
                    words=[{"word": "a", "definition": "a"}, {"word": "b", "definition": "b"}],
                    session_name="Japanese N5",
                )
            )
        _, kwargs = mock_post.call_args
        sent_words = kwargs["json"]["words"]
        assert all(w["session_name"] == "Japanese N5" for w in sent_words)

    def test_no_session_name_sends_words_unchanged(self):
        """Test bulk_add_vocabulary sends words without injection when session_name is None."""
        fake = _make_response(201, {"inserted": [], "skipped_count": 0})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(
                srv.bulk_add_vocabulary(
                    words=[{"word": "a", "definition": "a", "session_name": "per-word-session"}]
                )
            )
        _, kwargs = mock_post.call_args
        sent_words = kwargs["json"]["words"]
        assert sent_words[0]["session_name"] == "per-word-session"

    def test_top_level_session_name_overrides_per_word_session_name(self):
        """Test bulk_add_vocabulary top-level session_name overrides per-word session_name."""
        fake = _make_response(201, {"inserted": [], "skipped_count": 0})
        mock_post = AsyncMock(return_value=fake)
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(
                srv.bulk_add_vocabulary(
                    words=[{"word": "a", "definition": "a", "session_name": "old-session"}],
                    session_name="new-session",
                )
            )
        _, kwargs = mock_post.call_args
        sent_words = kwargs["json"]["words"]
        assert sent_words[0]["session_name"] == "new-session"


# ---------------------------------------------------------------------------
# delete_session helpers
# ---------------------------------------------------------------------------


def _make_sessions_response(sessions: list[dict]) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        json=sessions,
        request=httpx.Request("GET", "http://test-backend/sessions"),
    )


def _make_delete_session_response(status_code: int, json_body: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_body,
        request=httpx.Request("DELETE", "http://test-backend/vocabulary/session/1"),
    )


_SESSIONS = [
    {"id": 1, "name": "Spanish 1", "date": "2026-06-28", "created_at": "2026-06-28 00:00:00"}
]


class TestDeleteSession:
    def test_delete_session_tool_is_registered(self):
        """Test that delete_session tool is registered with MCP server."""
        tools = asyncio.run(srv.mcp.list_tools())
        assert any(t.name == "delete_session" for t in tools)

    def test_returns_success_message_with_session_name_and_count(self):
        """Test delete_session returns message containing session name and deleted word count."""
        sessions_resp = _make_sessions_response(_SESSIONS)
        delete_resp = _make_delete_session_response(200, {"deleted_words": 3})
        with (
            patch.object(srv._http_client, "get", new=AsyncMock(return_value=sessions_resp)),
            patch.object(srv._http_client, "delete", new=AsyncMock(return_value=delete_resp)),
        ):
            result = asyncio.run(srv.delete_session("Spanish 1"))
        assert "Spanish 1" in result
        assert "3" in result
        assert "Deleted" in result

    def test_returns_not_found_when_session_name_absent(self):
        """Test delete_session returns not-found message when name not in GET /sessions."""
        sessions_resp = _make_sessions_response(_SESSIONS)
        with patch.object(srv._http_client, "get", new=AsyncMock(return_value=sessions_resp)):
            result = asyncio.run(srv.delete_session("French 1"))
        assert "not found" in result.lower()
        assert "French 1" in result

    def test_http_error_on_delete_returns_error_message(self):
        """Test delete_session returns error message on HTTP error from delete endpoint."""
        sessions_resp = _make_sessions_response(_SESSIONS)
        error_resp = _make_delete_session_response(500, {"detail": "server error"})
        with (
            patch.object(srv._http_client, "get", new=AsyncMock(return_value=sessions_resp)),
            patch.object(
                srv._http_client,
                "delete",
                new=AsyncMock(
                    side_effect=httpx.HTTPStatusError(
                        "err", request=MagicMock(), response=error_resp
                    )
                ),
            ),
        ):
            result = asyncio.run(srv.delete_session("Spanish 1"))
        assert "Failed" in result
        assert "500" in result

    def test_network_error_returns_error_message(self):
        """Test delete_session returns error message on network failure during GET /sessions."""
        with patch.object(
            srv._http_client, "get", new=AsyncMock(side_effect=Exception("connection refused"))
        ):
            result = asyncio.run(srv.delete_session("Spanish 1"))
        assert "Failed" in result


def _hanzi_bulk_response(created, enriched, unchanged) -> httpx.Response:
    """Build a fake /vocabulary/hanzi/bulk response."""
    return httpx.Response(
        status_code=201,
        json={"created": created, "enriched": enriched, "unchanged": unchanged, "cards": []},
        request=httpx.Request("POST", "http://test-backend/vocabulary/hanzi/bulk"),
    )


_CARD = {
    "hanzi": "明",
    "keyword": "bright",
    "pinyin": "míng",
    "tone": 2,
    "story": "sun and moon → bright",
    "primitives": [{"component": "日", "keyword": "sun", "position": 0}],
}


class TestAddHanzi:
    """Tests for the add_hanzi and list_primitives MCP tools."""

    def test_tool_registered(self):
        """add_hanzi and list_primitives tools are registered."""
        tools = asyncio.run(srv.mcp.list_tools())
        names = {t.name for t in tools}
        assert {"add_hanzi", "list_primitives"} <= names

    def test_posts_to_hanzi_bulk_endpoint(self):
        """add_hanzi calls the /vocabulary/hanzi/bulk endpoint."""
        mock_post = AsyncMock(return_value=_hanzi_bulk_response(1, 0, 0))
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.add_hanzi([_CARD]))
        args, _ = mock_post.call_args
        assert "/vocabulary/hanzi/bulk" in args[0]

    def test_report_mentions_created_and_enriched(self):
        """The returned message reports created/enriched/unchanged counts."""
        with patch.object(
            srv._http_client, "post", new=AsyncMock(return_value=_hanzi_bulk_response(3, 5, 2))
        ):
            result = asyncio.run(srv.add_hanzi([_CARD]))
        assert "3" in result and "5" in result and "2" in result

    def test_maps_hanzi_field_to_word(self):
        """The 'hanzi' field is sent to the backend as 'word'."""
        mock_post = AsyncMock(return_value=_hanzi_bulk_response(1, 0, 0))
        with patch.object(srv._http_client, "post", new=mock_post):
            asyncio.run(srv.add_hanzi([_CARD]))
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["cards"][0]["word"] == "明"

    def test_invalid_tone_returns_error_without_calling_backend(self):
        """Invalid input fails validation and never hits the backend."""
        mock_post = AsyncMock()
        bad = {**_CARD, "tone": 9}
        with patch.object(srv._http_client, "post", new=mock_post):
            result = asyncio.run(srv.add_hanzi([bad]))
        assert "Invalid" in result or "valid" in result.lower()
        mock_post.assert_not_called()

    def test_list_primitives_calls_get(self):
        """list_primitives fetches GET /primitives."""
        resp = httpx.Response(
            200,
            json=[{"id": 1, "component": "日", "keyword": "sun", "note": None, "rank": 1}],
            request=httpx.Request("GET", "http://test-backend/primitives"),
        )
        mock_get = AsyncMock(return_value=resp)
        with patch.object(srv._http_client, "get", new=mock_get):
            result = asyncio.run(srv.list_primitives())
        args, _ = mock_get.call_args
        assert "/primitives" in args[0]
        assert "日" in result and "sun" in result


class TestHanziInputModel:
    """Tests for HanziInput and PrimitiveRefInput Pydantic models."""

    def test_valid_hanzi_input(self):
        """A well-formed HanziInput validates."""
        m = srv.HanziInput(
            hanzi="明",
            keyword="bright",
            pinyin="míng",
            tone=2,
            story="s",
            primitives=[{"component": "日", "keyword": "sun", "position": 0}],
        )
        assert m.tone == 2

    def test_tone_out_of_range_rejected(self):
        """tone outside 1..5 raises ValidationError."""
        with pytest.raises(ValidationError):
            srv.HanziInput(hanzi="x", keyword="k", pinyin="p", tone=0, story="s")
