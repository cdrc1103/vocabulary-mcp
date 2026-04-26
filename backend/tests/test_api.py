"""Integration tests for vocabulary API endpoints.

Tests all CRUD endpoints, authentication, pagination, and error handling.
"""

import time

import jwt

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
