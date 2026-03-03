"""Integration tests for the Vocabulary API endpoints."""

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
        r = client.get("/vocabulary")
        assert r.status_code == 401

    def test_wrong_key_returns_401(self, client):
        r = client.get("/vocabulary", headers={"X-API-Key": "wrong"})
        assert r.status_code == 401

    def test_correct_key_passes(self, client):
        r = client.get("/vocabulary", headers=AUTH_HEADERS)
        assert r.status_code == 200

    def test_health_requires_no_auth(self, client):
        r = client.get("/health")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


class TestLogin:
    def test_correct_password_returns_token(self, client):
        r = client.post("/auth/login", json={"password": TEST_PASSWORD})
        assert r.status_code == 200
        body = r.json()
        assert "token" in body
        assert body["token_type"] == "bearer"

    def test_wrong_password_returns_401(self, client):
        r = client.post("/auth/login", json={"password": "wrong"})
        assert r.status_code == 401

    def test_missing_body_returns_422(self, client):
        r = client.post("/auth/login", json={})
        assert r.status_code == 422

    def test_login_requires_no_api_key(self, client):
        # Must be callable without X-API-Key
        r = client.post("/auth/login", json={"password": TEST_PASSWORD})
        assert r.status_code == 200

    def test_token_is_valid_jwt(self, client):
        r = client.post("/auth/login", json={"password": TEST_PASSWORD})
        token = r.json()["token"]
        payload = jwt.decode(token, TEST_API_KEY, algorithms=["HS256"])
        assert payload["sub"] == "pwa"


class TestJWTAuth:
    def _get_token(self, client) -> str:
        return client.post("/auth/login", json={"password": TEST_PASSWORD}).json()["token"]

    def test_valid_jwt_grants_access(self, client):
        token = self._get_token(client)
        r = client.get("/vocabulary", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_invalid_jwt_returns_401(self, client):
        r = client.get("/vocabulary", headers={"Authorization": "Bearer garbage"})
        assert r.status_code == 401

    def test_expired_jwt_returns_401(self, client):
        payload = {"sub": "pwa", "exp": int(time.time()) - 1}
        expired_token = jwt.encode(payload, TEST_API_KEY, algorithm="HS256")
        r = client.get("/vocabulary", headers={"Authorization": f"Bearer {expired_token}"})
        assert r.status_code == 401

    def test_bearer_prefix_required(self, client):
        token = self._get_token(client)
        r = client.get("/vocabulary", headers={"Authorization": token})
        assert r.status_code == 401

    def test_both_auth_methods_work_on_same_endpoint(self, client):
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
        assert client.get("/health").json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /vocabulary
# ---------------------------------------------------------------------------


class TestAddVocabulary:
    def test_creates_word_returns_201(self, client):
        r = client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        assert r.status_code == 201
        data = r.json()
        assert data["word"] == "bonjour"
        assert data["language"] == "French"
        assert "id" in data

    def test_missing_required_fields_returns_422(self, client):
        r = client.post("/vocabulary", json={"word": "oops"}, headers=AUTH_HEADERS)
        assert r.status_code == 422

    def test_optional_example_defaults_to_none(self, client):
        r = client.post(
            "/vocabulary",
            json={"word": "ciao", "definition": "bye"},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 201
        assert r.json()["example"] is None

    def test_optional_language_defaults_to_unknown(self, client):
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
        r = client.get("/vocabulary", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert r.json() == {"total": 0, "words": []}

    def test_returns_added_words(self, client):
        client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        r = client.get("/vocabulary", headers=AUTH_HEADERS)
        assert r.json()["total"] == 1

    def test_language_filter(self, client):
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
        r = client.get("/vocabulary?limit=0", headers=AUTH_HEADERS)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /vocabulary/due
# ---------------------------------------------------------------------------


class TestDueVocabulary:
    def test_newly_added_word_is_due(self, client):
        client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        r = client.get("/vocabulary/due", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert len(r.json()) == 1


# ---------------------------------------------------------------------------
# PATCH /vocabulary/{id}/review
# ---------------------------------------------------------------------------


class TestSubmitReview:
    def _add_word(self, client):
        r = client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        return r.json()["id"]

    def test_passing_review_advances_schedule(self, client):
        wid = self._add_word(client)
        r = client.patch(f"/vocabulary/{wid}/review", json={"quality": 4}, headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert r.json()["repetitions"] == 1

    def test_failing_review_resets(self, client):
        wid = self._add_word(client)
        client.patch(f"/vocabulary/{wid}/review", json={"quality": 5}, headers=AUTH_HEADERS)
        r = client.patch(f"/vocabulary/{wid}/review", json={"quality": 0}, headers=AUTH_HEADERS)
        assert r.json()["repetitions"] == 0
        assert r.json()["interval"] == 1

    def test_not_found_returns_404(self, client):
        r = client.patch("/vocabulary/9999/review", json={"quality": 4}, headers=AUTH_HEADERS)
        assert r.status_code == 404

    def test_quality_above_5_returns_422(self, client):
        wid = self._add_word(client)
        r = client.patch(f"/vocabulary/{wid}/review", json={"quality": 6}, headers=AUTH_HEADERS)
        assert r.status_code == 422

    def test_quality_below_0_returns_422(self, client):
        wid = self._add_word(client)
        r = client.patch(f"/vocabulary/{wid}/review", json={"quality": -1}, headers=AUTH_HEADERS)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /vocabulary/{id}
# ---------------------------------------------------------------------------


class TestDeleteVocabulary:
    def test_deletes_existing_word_returns_204(self, client):
        r = client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        wid = r.json()["id"]
        r = client.delete(f"/vocabulary/{wid}", headers=AUTH_HEADERS)
        assert r.status_code == 204

    def test_deleted_word_no_longer_listed(self, client):
        r = client.post("/vocabulary", json=WORD_PAYLOAD, headers=AUTH_HEADERS)
        wid = r.json()["id"]
        client.delete(f"/vocabulary/{wid}", headers=AUTH_HEADERS)
        assert client.get("/vocabulary", headers=AUTH_HEADERS).json()["total"] == 0

    def test_not_found_returns_404(self, client):
        r = client.delete("/vocabulary/9999", headers=AUTH_HEADERS)
        assert r.status_code == 404
