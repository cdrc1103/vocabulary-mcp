"""Integration tests for vocabulary API endpoints.

Tests all CRUD endpoints, authentication, pagination, and error handling.
"""

import time

import jwt
import models_heisig
import pytest
from pydantic import ValidationError

from tests.conftest import AUTH_HEADERS, TEST_API_KEY, TEST_PASSWORD

WORD_PAYLOAD = {
    "word": "bonjour",
    "definition": "hello",
    "example": "Bonjour, monde!",
    "language": "French",
}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAuth:
    def test_missing_key_returns_401(self, client):
        """Test that requests without API key return 401 Unauthorized."""
        r = client.get("/vocabulary")
        assert r.status_code == 401

    def test_wrong_key_returns_401(self, client):
        """Test that requests with invalid API key return 401 Unauthorized."""
        r = client.get("/vocabulary", headers={"X-API-Key": "wrong"})
        assert r.status_code == 401

    def test_correct_key_passes(self, client):
        """Test that requests with valid API key return 200 OK."""
        r = client.get("/vocabulary", headers=AUTH_HEADERS)
        assert r.status_code == 200

    def test_health_requires_no_auth(self, client):
        """Test that health check endpoint does not require authentication."""
        r = client.get("/health")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


class TestLogin:
    def test_correct_password_returns_token(self, client):
        """Test login endpoint returns valid bearer token for correct password."""
        r = client.post("/auth/login", json={"password": TEST_PASSWORD})
        assert r.status_code == 200
        body = r.json()
        assert "token" in body
        assert body["token_type"] == "bearer"

    def test_wrong_password_returns_401(self, client):
        """Test login endpoint returns 401 for incorrect password."""
        r = client.post("/auth/login", json={"password": "wrong"})
        assert r.status_code == 401

    def test_missing_body_returns_422(self, client):
        """Test login endpoint returns 422 for missing password field."""
        r = client.post("/auth/login", json={})
        assert r.status_code == 422

    def test_login_requires_no_api_key(self, client):
        """Test that login endpoint does not require X-API-Key header."""
        r = client.post("/auth/login", json={"password": TEST_PASSWORD})
        assert r.status_code == 200

    def test_token_is_valid_jwt(self, client):
        """Test that returned token is a valid JWT signed with API key."""
        r = client.post("/auth/login", json={"password": TEST_PASSWORD})
        token = r.json()["token"]
        payload = jwt.decode(token, TEST_API_KEY, algorithms=["HS256"])
        assert payload["sub"] == "pwa"


class TestJWTAuth:
    def _get_token(self, client) -> str:
        """Helper to obtain a valid JWT token via login endpoint."""
        return client.post("/auth/login", json={"password": TEST_PASSWORD}).json()["token"]

    def test_valid_jwt_grants_access(self, client):
        """Test that valid JWT in Authorization header grants access."""
        token = self._get_token(client)
        r = client.get("/vocabulary", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_invalid_jwt_returns_401(self, client):
        """Test that malformed JWT returns 401 Unauthorized."""
        r = client.get("/vocabulary", headers={"Authorization": "Bearer garbage"})
        assert r.status_code == 401

    def test_expired_jwt_returns_401(self, client):
        """Test that expired JWT returns 401 Unauthorized."""
        payload = {"sub": "pwa", "exp": int(time.time()) - 1}
        expired_token = jwt.encode(payload, TEST_API_KEY, algorithm="HS256")
        r = client.get("/vocabulary", headers={"Authorization": f"Bearer {expired_token}"})
        assert r.status_code == 401

    def test_bearer_prefix_required(self, client):
        """Test that Authorization header requires 'Bearer' prefix."""
        token = self._get_token(client)
        r = client.get("/vocabulary", headers={"Authorization": token})
        assert r.status_code == 401

    def test_both_auth_methods_work_on_same_endpoint(self, client):
        """Test that both API key and JWT authentication work on same endpoint."""
        token = self._get_token(client)
        r_jwt = client.get("/vocabulary", headers={"Authorization": f"Bearer {token}"})
        r_key = client.get("/vocabulary", headers=AUTH_HEADERS)
        assert r_jwt.status_code == 200
        assert r_key.status_code == 200


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_returns_ok(self, client):
        """Test that health check endpoint returns ok status."""
        assert client.get("/health").json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /vocabulary
# ---------------------------------------------------------------------------


class TestAddVocabulary:
    def test_creates_word_returns_201(self, client):
        """Test creating a new vocabulary word returns 201 with word data."""
        r = client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        assert r.status_code == 201
        data = r.json()
        assert data["word"] == "bonjour"
        assert data["language"] == "French"
        assert "id" in data

    def test_missing_required_fields_returns_422(self, client):
        """Test creating word without required fields returns 422."""
        r = client.post("/vocabulary", json={"word": "oops"}, headers=AUTH_HEADERS)
        assert r.status_code == 422

    def test_optional_example_defaults_to_none(self, client):
        """Test that example field defaults to None when not provided."""
        r = client.post(
            "/vocabulary",
            json={"word": "ciao", "definition": "bye"},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 201
        assert r.json()["example"] is None

    def test_optional_language_defaults_to_unknown(self, client):
        """Test that language field defaults to 'unknown' when not provided."""
        r = client.post(
            "/vocabulary",
            json={"word": "hi", "definition": "greeting"},
            headers=AUTH_HEADERS,
        )
        assert r.json()["language"] == "unknown"


# ---------------------------------------------------------------------------
# GET /vocabulary
# ---------------------------------------------------------------------------


class TestListVocabulary:
    def test_empty_list(self, client):
        """Test listing vocabulary returns empty list when no words exist."""
        r = client.get("/vocabulary", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert r.json() == {"total": 0, "words": []}

    def test_returns_added_words(self, client):
        """Test listing vocabulary returns previously added words."""
        client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        r = client.get("/vocabulary", headers=AUTH_HEADERS)
        assert r.json()["total"] == 1

    def test_language_filter(self, client):
        """Test filtering vocabulary by language parameter."""
        client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        client.post(
            "/vocabulary",
            json={"word": "hola", "definition": "hi", "language": "Spanish"},
            headers=AUTH_HEADERS,
        )
        r = client.get("/vocabulary?language=French", headers=AUTH_HEADERS)
        body = r.json()
        assert body["total"] == 1
        assert body["words"][0]["language"] == "French"

    def test_pagination(self, client):
        """Test pagination with limit and offset parameters."""
        for i in range(5):
            client.post(
                "/vocabulary",
                json={"word": f"w{i}", "definition": "d"},
                headers=AUTH_HEADERS,
            )
        r = client.get("/vocabulary?limit=2&offset=0", headers=AUTH_HEADERS)
        body = r.json()
        assert len(body["words"]) == 2
        assert body["total"] == 5

    def test_limit_out_of_range_returns_422(self, client):
        """Test that limit of 0 or less returns 422 validation error."""
        r = client.get("/vocabulary?limit=0", headers=AUTH_HEADERS)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /vocabulary/due
# ---------------------------------------------------------------------------


class TestDueVocabulary:
    def test_newly_added_word_is_due(self, client):
        """Test that newly added word is immediately due for review."""
        client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        r = client.get("/vocabulary/due", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_created_after_today_includes_new_word(self, client):
        """Words added today appear when created_after is today."""
        from datetime import date

        client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        today = date.today().isoformat()
        r = client.get(f"/vocabulary/due?created_after={today}", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_created_after_tomorrow_excludes_new_word(self, client):
        """Words added today are excluded when created_after is tomorrow."""
        from datetime import date, timedelta

        client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        r = client.get(f"/vocabulary/due?created_after={tomorrow}", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert len(r.json()) == 0


# ---------------------------------------------------------------------------
# PATCH /vocabulary/{id}/review
# ---------------------------------------------------------------------------


class TestSubmitReview:
    def _add_word(self, client):
        """Helper to add a word and return its ID."""
        r = client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        return r.json()["id"]

    def test_passing_review_advances_schedule(self, client):
        """Test submitting a passing review advances SM-2 schedule."""
        wid = self._add_word(client)
        r = client.patch(f"/vocabulary/{wid}/review", json={"quality": 4}, headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert r.json()["repetitions"] == 1

    def test_failing_review_resets(self, client):
        """Test submitting a failing review resets SM-2 schedule."""
        wid = self._add_word(client)
        client.patch(f"/vocabulary/{wid}/review", json={"quality": 5}, headers=AUTH_HEADERS)
        r = client.patch(f"/vocabulary/{wid}/review", json={"quality": 0}, headers=AUTH_HEADERS)
        assert r.json()["repetitions"] == 0
        assert r.json()["interval"] == 1

    def test_not_found_returns_404(self, client):
        """Test reviewing non-existent word returns 404."""
        r = client.patch("/vocabulary/9999/review", json={"quality": 4}, headers=AUTH_HEADERS)
        assert r.status_code == 404

    def test_quality_above_5_returns_422(self, client):
        """Test that quality score above 5 returns 422 validation error."""
        wid = self._add_word(client)
        r = client.patch(f"/vocabulary/{wid}/review", json={"quality": 6}, headers=AUTH_HEADERS)
        assert r.status_code == 422

    def test_quality_below_0_returns_422(self, client):
        """Test that negative quality score returns 422 validation error."""
        wid = self._add_word(client)
        r = client.patch(f"/vocabulary/{wid}/review", json={"quality": -1}, headers=AUTH_HEADERS)
        assert r.status_code == 422


BULK_PAYLOAD = {
    "words": [
        {"word": "bonjour", "definition": "hello", "language": "French"},
        {
            "word": "merci",
            "definition": "thanks",
            "example": "Merci beaucoup.",
            "language": "French",
        },
        {"word": "oui", "definition": "yes", "language": "French"},
    ]
}


# ---------------------------------------------------------------------------
# POST /vocabulary/bulk
# ---------------------------------------------------------------------------


class TestBulkAddVocabulary:
    def test_bulk_creates_words_returns_201(self, client):
        """Test bulk creating multiple vocabulary words returns 201."""
        r = client.post("/vocabulary/bulk", json=BULK_PAYLOAD, headers=AUTH_HEADERS)
        assert r.status_code == 201
        body = r.json()
        assert len(body["inserted"]) == 3
        assert body["skipped_count"] == 0

    def test_bulk_skips_duplicates(self, client):
        """Test bulk operation skips words that already exist in database."""
        client.post(
            "/vocabulary",
            json={"word": "bonjour", "definition": "hello", "language": "French"},
            headers=AUTH_HEADERS,
        )
        r = client.post("/vocabulary/bulk", json=BULK_PAYLOAD, headers=AUTH_HEADERS)
        assert r.status_code == 201
        body = r.json()
        assert len(body["inserted"]) == 2
        assert body["skipped_count"] == 1

    def test_bulk_empty_list_returns_422(self, client):
        """Test bulk endpoint returns 422 when word list is empty."""
        r = client.post("/vocabulary/bulk", json={"words": []}, headers=AUTH_HEADERS)
        assert r.status_code == 422

    def test_bulk_over_50_returns_422(self, client):
        """Test bulk endpoint returns 422 when word count exceeds 50."""
        words = [{"word": f"w{i}", "definition": "d"} for i in range(51)]
        r = client.post("/vocabulary/bulk", json={"words": words}, headers=AUTH_HEADERS)
        assert r.status_code == 422

    def test_bulk_missing_required_fields_returns_422(self, client):
        """Test bulk endpoint returns 422 when word missing required fields."""
        r = client.post(
            "/vocabulary/bulk", json={"words": [{"word": "oops"}]}, headers=AUTH_HEADERS
        )
        assert r.status_code == 422

    def test_bulk_inserted_words_have_all_fields(self, client):
        """Test inserted words from bulk operation have correct default fields."""
        r = client.post("/vocabulary/bulk", json=BULK_PAYLOAD, headers=AUTH_HEADERS)
        word = r.json()["inserted"][0]
        assert "id" in word
        assert "created_at" in word
        assert "next_review" in word
        assert "interval" in word
        assert word["interval"] == 1
        assert word["ease_factor"] == 2.5
        assert word["repetitions"] == 0

    def test_bulk_requires_auth(self, client):
        """Test that bulk endpoint requires authentication."""
        r = client.post("/vocabulary/bulk", json=BULK_PAYLOAD)
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /vocabulary/{id}
# ---------------------------------------------------------------------------


class TestDeleteVocabulary:
    def test_deletes_existing_word_returns_204(self, client):
        """Test deleting existing vocabulary word returns 204 No Content."""
        r = client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        wid = r.json()["id"]
        r = client.delete(f"/vocabulary/{wid}", headers=AUTH_HEADERS)
        assert r.status_code == 204

    def test_deleted_word_no_longer_listed(self, client):
        """Test that deleted word no longer appears in vocabulary list."""
        r = client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        wid = r.json()["id"]
        client.delete(f"/vocabulary/{wid}", headers=AUTH_HEADERS)
        assert client.get("/vocabulary", headers=AUTH_HEADERS).json()["total"] == 0

    def test_not_found_returns_404(self, client):
        """Test deleting non-existent word returns 404."""
        r = client.delete("/vocabulary/9999", headers=AUTH_HEADERS)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /sessions
# ---------------------------------------------------------------------------


class TestListSessions:
    def test_returns_empty_list_on_fresh_db(self, client):
        """Test GET /sessions returns at least the seeded misc session."""
        r = client.get("/sessions", headers=AUTH_HEADERS)
        assert r.status_code == 200
        sessions = r.json()
        assert isinstance(sessions, list)
        assert any(s["name"] == "misc" for s in sessions)

    def test_returns_created_sessions(self, client):
        """Test GET /sessions includes sessions created via POST /vocabulary."""
        client.post(
            "/vocabulary",
            json={
                "word": "bonjour",
                "definition": "hello",
                "language": "fr",
                "session_name": "French 101",
            },
            headers=AUTH_HEADERS,
        )
        r = client.get("/sessions", headers=AUTH_HEADERS)
        assert r.status_code == 200
        names = [s["name"] for s in r.json()]
        assert "French 101" in names

    def test_session_has_required_fields(self, client):
        """Test session objects include id, name, date, created_at."""
        r = client.get("/sessions", headers=AUTH_HEADERS)
        session = r.json()[0]
        assert "id" in session
        assert "name" in session
        assert "date" in session
        assert "created_at" in session

    def test_requires_auth(self, client):
        """Test GET /sessions requires API key."""
        r = client.get("/sessions")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# POST /vocabulary with session_name
# ---------------------------------------------------------------------------


class TestAddVocabularyWithSession:
    def test_session_name_accepted(self, client):
        """Test POST /vocabulary accepts optional session_name."""
        r = client.post(
            "/vocabulary",
            json={"word": "hola", "definition": "hello", "session_name": "Spanish 1"},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 201
        body = r.json()
        assert body["session_name"] == "Spanish 1"
        assert isinstance(body["session_id"], int)

    def test_no_session_name_defaults_to_misc(self, client):
        """Test POST /vocabulary without session_name assigns to misc."""
        r = client.post(
            "/vocabulary", json={"word": "ciao", "definition": "hi"}, headers=AUTH_HEADERS
        )
        assert r.status_code == 201
        assert r.json()["session_name"] == "misc"


# ---------------------------------------------------------------------------
# GET /vocabulary?session_id=
# ---------------------------------------------------------------------------


class TestListVocabularySessionFilter:
    def test_session_id_filters_words(self, client):
        """Test GET /vocabulary?session_id= returns only words in that session."""
        client.post(
            "/vocabulary",
            json={"word": "hola", "definition": "hello", "session_name": "Spanish 1"},
            headers=AUTH_HEADERS,
        )
        client.post(
            "/vocabulary",
            json={"word": "bonjour", "definition": "hello", "session_name": "French 1"},
            headers=AUTH_HEADERS,
        )
        sessions_r = client.get("/sessions", headers=AUTH_HEADERS)
        spanish = next(s for s in sessions_r.json() if s["name"] == "Spanish 1")

        r = client.get(f"/vocabulary?session_id={spanish['id']}", headers=AUTH_HEADERS)
        assert r.status_code == 200
        words = r.json()["words"]
        assert len(words) == 1
        assert words[0]["word"] == "hola"


# ---------------------------------------------------------------------------
# GET /vocabulary/due?session_id=
# ---------------------------------------------------------------------------


class TestDueVocabularySessionFilter:
    def test_session_id_filters_due_words(self, client):
        """Test GET /vocabulary/due?session_id= returns only due words in that session."""
        client.post(
            "/vocabulary",
            json={"word": "hola", "definition": "hello", "session_name": "Spanish 1"},
            headers=AUTH_HEADERS,
        )
        client.post(
            "/vocabulary",
            json={"word": "bonjour", "definition": "hello", "session_name": "French 1"},
            headers=AUTH_HEADERS,
        )
        sessions_r = client.get("/sessions", headers=AUTH_HEADERS)
        spanish = next(s for s in sessions_r.json() if s["name"] == "Spanish 1")

        r = client.get(f"/vocabulary/due?session_id={spanish['id']}", headers=AUTH_HEADERS)
        assert r.status_code == 200
        words = r.json()
        assert len(words) == 1
        assert words[0]["word"] == "hola"
        assert words[0]["session_name"] == "Spanish 1"


# ---------------------------------------------------------------------------
# PATCH /vocabulary/{id}  (content update)
# ---------------------------------------------------------------------------


class TestUpdateVocabulary:
    """Tests for PATCH /vocabulary/{id} — content-only update endpoint."""

    def _add_word(self, client, word="bonjour", definition="hello", language="French"):
        """Helper to insert a vocabulary word and return its id."""
        r = client.post(
            "/vocabulary",
            json={"word": word, "definition": definition, "language": language},
            headers=AUTH_HEADERS,
        )
        return r.json()["id"]

    def test_update_content_returns_200_with_new_values(self, client):
        """Test PATCH /vocabulary/{id} updates word, definition, example and returns 200."""
        wid = self._add_word(client)
        r = client.patch(
            f"/vocabulary/{wid}",
            json={"word": "salut", "definition": "hi there", "example": "Salut!"},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["word"] == "salut"
        assert body["definition"] == "hi there"
        assert body["example"] == "Salut!"

    def test_update_preserves_sm2_state(self, client):
        """Test PATCH /vocabulary/{id} does not change SM-2 scheduling fields."""
        wid = self._add_word(client)
        client.patch(f"/vocabulary/{wid}/review", json={"quality": 5}, headers=AUTH_HEADERS)
        before = client.get("/vocabulary", headers=AUTH_HEADERS).json()["words"][0]

        r = client.patch(
            f"/vocabulary/{wid}",
            json={"word": "salut", "definition": "hi", "example": None},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        updated = r.json()
        assert updated["interval"] == before["interval"]
        assert updated["ease_factor"] == before["ease_factor"]
        assert updated["repetitions"] == before["repetitions"]
        assert updated["next_review"] == before["next_review"]

    def test_update_not_found_returns_404(self, client):
        """Test PATCH /vocabulary/{id} with unknown id returns 404."""
        r = client.patch(
            "/vocabulary/9999",
            json={"word": "x", "definition": "y", "example": None},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 404

    def test_update_duplicate_word_language_returns_409(self, client):
        """Test PATCH that creates a word+language collision with existing entry returns 409."""
        self._add_word(client, word="bonjour", language="French")
        wid2 = self._add_word(client, word="merci", language="French")
        r = client.patch(
            f"/vocabulary/{wid2}",
            json={"word": "bonjour", "definition": "thanks", "example": None},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 409

    def test_update_clears_example_when_none(self, client):
        """Test PATCH with example=None clears a previously set example."""
        wid = self._add_word(client)
        client.patch(
            f"/vocabulary/{wid}",
            json={"word": "bonjour", "definition": "hello", "example": "Bonjour!"},
            headers=AUTH_HEADERS,
        )
        r = client.patch(
            f"/vocabulary/{wid}",
            json={"word": "bonjour", "definition": "hello", "example": None},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        assert r.json()["example"] is None

    def test_update_requires_auth(self, client):
        """Test PATCH /vocabulary/{id} requires API key or JWT."""
        wid = self._add_word(client)
        r = client.patch(
            f"/vocabulary/{wid}",
            json={"word": "x", "definition": "y", "example": None},
        )
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /vocabulary/session/{session_id}
# ---------------------------------------------------------------------------


class TestDeleteVocabularySession:
    """Tests for DELETE /vocabulary/session/{session_id}."""

    def _create_session_with_words(self, client, session_name: str, words: list[dict]) -> int:
        """Helper: create words under a named session, return session id.

        Args:
            client: TestClient instance.
            session_name: Name of the session to create.
            words: List of word dictionaries with word, definition, etc.

        Returns:
            The session ID of the created session.
        """
        for w in words:
            client.post(
                "/vocabulary",
                json={**w, "session_name": session_name},
                headers=AUTH_HEADERS,
            )
        sessions = client.get("/sessions", headers=AUTH_HEADERS).json()
        return next(s["id"] for s in sessions if s["name"] == session_name)

    def test_returns_200_with_deleted_word_count(self, client):
        """Test DELETE returns 200 and correct deleted_words count."""
        sid = self._create_session_with_words(
            client,
            "Spanish 1",
            [{"word": "hola", "definition": "hi"}, {"word": "adios", "definition": "bye"}],
        )
        r = client.delete(f"/vocabulary/session/{sid}", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert r.json() == {"deleted_words": 2}

    def test_returns_200_with_zero_when_session_empty(self, client):
        """Test DELETE returns deleted_words=0 when session has no words."""
        r = client.post(
            "/vocabulary",
            json={"word": "hola", "definition": "hi", "session_name": "Empty Session"},
            headers=AUTH_HEADERS,
        )
        wid = r.json()["id"]
        client.delete(f"/vocabulary/{wid}", headers=AUTH_HEADERS)
        sessions = client.get("/sessions", headers=AUTH_HEADERS).json()
        sid = next(s["id"] for s in sessions if s["name"] == "Empty Session")
        r = client.delete(f"/vocabulary/session/{sid}", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert r.json() == {"deleted_words": 0}

    def test_returns_404_for_unknown_session_id(self, client):
        """Test DELETE returns 404 for non-existent session_id."""
        r = client.delete("/vocabulary/session/9999", headers=AUTH_HEADERS)
        assert r.status_code == 404

    def test_words_absent_from_vocabulary_after_delete(self, client):
        """Test words no longer appear in GET /vocabulary after session delete."""
        sid = self._create_session_with_words(
            client, "Spanish 1", [{"word": "hola", "definition": "hi"}]
        )
        client.delete(f"/vocabulary/session/{sid}", headers=AUTH_HEADERS)
        words = client.get("/vocabulary", headers=AUTH_HEADERS).json()["words"]
        assert not any(w["word"] == "hola" for w in words)

    def test_session_absent_from_sessions_after_delete(self, client):
        """Test session no longer appears in GET /sessions after delete."""
        sid = self._create_session_with_words(
            client, "Spanish 1", [{"word": "hola", "definition": "hi"}]
        )
        client.delete(f"/vocabulary/session/{sid}", headers=AUTH_HEADERS)
        sessions = client.get("/sessions", headers=AUTH_HEADERS).json()
        assert not any(s["name"] == "Spanish 1" for s in sessions)

    def test_requires_auth(self, client):
        """Test DELETE /vocabulary/session/{id} requires authentication."""
        r = client.delete("/vocabulary/session/1")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Heisig Models Validation
# ---------------------------------------------------------------------------


class TestPrimitivesEndpoints:
    """Tests for GET/POST /primitives endpoints."""

    def test_post_creates_primitive(self, client):
        """POST /primitives registers a primitive with rank 1."""
        r = client.post(
            "/primitives", headers=AUTH_HEADERS, json={"component": "日", "keyword": "sun"}
        )
        assert r.status_code == 201
        assert r.json()["keyword"] == "sun"
        assert r.json()["rank"] == 1

    def test_post_is_first_write_wins(self, client):
        """POST /primitives never overwrites an existing keyword."""
        client.post("/primitives", headers=AUTH_HEADERS, json={"component": "日", "keyword": "sun"})
        r = client.post(
            "/primitives", headers=AUTH_HEADERS, json={"component": "日", "keyword": "day"}
        )
        assert r.json()["keyword"] == "sun"

    def test_get_lists_primitives(self, client):
        """GET /primitives returns the registry."""
        client.post("/primitives", headers=AUTH_HEADERS, json={"component": "日", "keyword": "sun"})
        r = client.get("/primitives", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert [p["component"] for p in r.json()] == ["日"]


# ---------------------------------------------------------------------------
# Heisig Models Validation
# ---------------------------------------------------------------------------


class TestHeisigModels:
    """Tests for Heisig pydantic model validation."""

    def test_hanzi_upsert_valid(self):
        """A well-formed HanziUpsert validates and keeps its primitives."""
        m = models_heisig.HanziUpsert(
            word="明",
            keyword="bright",
            pinyin="míng",
            tone=2,
            story="s",
            primitives=[{"component": "日", "keyword": "sun", "position": 0}],
        )
        assert m.tone == 2
        assert m.primitives[0].component == "日"

    def test_tone_out_of_range_rejected(self):
        """tone outside 1..5 fails validation."""
        with pytest.raises(ValidationError):
            models_heisig.HanziUpsert(word="x", keyword="k", pinyin="p", tone=6, story="s")

    def test_negative_position_rejected(self):
        """A negative primitive position fails validation."""
        with pytest.raises(ValidationError):
            models_heisig.PrimitiveRef(component="日", keyword="sun", position=-1)

    def test_bulk_limits_enforced(self):
        """HanziBulkUpsert rejects an empty card list."""
        with pytest.raises(ValidationError):
            models_heisig.HanziBulkUpsert(cards=[])


# ---------------------------------------------------------------------------
# POST /vocabulary/hanzi/bulk
# ---------------------------------------------------------------------------


class TestHanziBulkUpsert:
    """Tests for POST /vocabulary/hanzi/bulk endpoint."""

    def test_creates_new_hanzi(self, client):
        """New hanzi are created and counted."""
        r = client.post(
            "/vocabulary/hanzi/bulk",
            headers=AUTH_HEADERS,
            json={
                "cards": [
                    {
                        "word": "明",
                        "keyword": "bright",
                        "pinyin": "míng",
                        "tone": 2,
                        "story": "sun and moon rise → bright",
                        "primitives": [
                            {"component": "日", "keyword": "sun", "position": 0},
                            {"component": "月", "keyword": "moon", "position": 1},
                        ],
                    }
                ]
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["created"] == 1 and body["enriched"] == 0
        assert body["cards"][0]["language"] == "Chinese"
        assert [p["keyword"] for p in body["cards"][0]["primitives"]] == ["sun", "moon"]

    def test_second_call_enriches_then_unchanged(self, client):
        """Re-posting the same payload reports enriched=0, unchanged=1."""
        payload = {
            "cards": [
                {
                    "word": "好",
                    "keyword": "good",
                    "pinyin": "hǎo",
                    "tone": 3,
                    "story": "woman and child → good",
                    "primitives": [],
                }
            ]
        }
        client.post("/vocabulary/hanzi/bulk", headers=AUTH_HEADERS, json=payload)
        r = client.post("/vocabulary/hanzi/bulk", headers=AUTH_HEADERS, json=payload)
        body = r.json()
        assert body["created"] == 0
        assert body["unchanged"] == 1

    def test_session_name_applies_to_new_cards(self, client):
        """Top-level session_name is used for newly created cards."""
        r = client.post(
            "/vocabulary/hanzi/bulk",
            headers=AUTH_HEADERS,
            json={
                "session_name": "HSK 1",
                "cards": [
                    {
                        "word": "人",
                        "keyword": "person",
                        "pinyin": "rén",
                        "tone": 2,
                        "story": "a person strides",
                        "primitives": [],
                    }
                ],
            },
        )
        assert r.json()["cards"][0]["session_name"] == "HSK 1"
