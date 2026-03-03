"""Unit tests for database CRUD operations."""

from datetime import date, timedelta

import database as db
import pytest


@pytest.fixture(autouse=True)
def _fresh_db(tmp_db):
    """Ensure every test in this module uses an isolated database."""


class TestInsertWord:
    def test_returns_dict_with_all_fields(self):
        result = db.insert_word("bonjour", "hello", "Bonjour, monde!", "French")
        assert result["word"] == "bonjour"
        assert result["definition"] == "hello"
        assert result["example"] == "Bonjour, monde!"
        assert result["language"] == "French"
        assert isinstance(result["id"], int)
        assert result["interval"] == 1
        assert result["ease_factor"] == 2.5
        assert result["repetitions"] == 0

    def test_next_review_is_today(self):
        result = db.insert_word("ciao", "bye", None, "Italian")
        assert result["next_review"] == date.today().isoformat()

    def test_example_can_be_none(self):
        result = db.insert_word("hola", "hi", None, "Spanish")
        assert result["example"] is None

    def test_ids_are_unique(self):
        r1 = db.insert_word("a", "a", None, "en")
        r2 = db.insert_word("b", "b", None, "en")
        assert r1["id"] != r2["id"]


class TestGetWords:
    def test_empty_db_returns_zero_total(self):
        result = db.get_words(language=None, limit=100, offset=0)
        assert result["total"] == 0
        assert result["words"] == []

    def test_returns_inserted_words(self):
        db.insert_word("chat", "cat", None, "French")
        db.insert_word("chien", "dog", None, "French")
        result = db.get_words(language=None, limit=100, offset=0)
        assert result["total"] == 2

    def test_language_filter(self):
        db.insert_word("chat", "cat", None, "French")
        db.insert_word("gato", "cat", None, "Spanish")
        fr = db.get_words(language="French", limit=100, offset=0)
        assert fr["total"] == 1
        assert fr["words"][0]["word"] == "chat"

    def test_pagination_limit(self):
        for i in range(5):
            db.insert_word(f"word{i}", "def", None, "en")
        result = db.get_words(language=None, limit=2, offset=0)
        assert len(result["words"]) == 2
        assert result["total"] == 5

    def test_pagination_offset(self):
        for i in range(5):
            db.insert_word(f"word{i}", "def", None, "en")
        result = db.get_words(language=None, limit=10, offset=3)
        assert len(result["words"]) == 2


class TestGetDueWords:
    def test_returns_word_due_today(self):
        db.insert_word("aujourd'hui", "today", None, "French")
        due = db.get_due_words()
        assert len(due) == 1

    def test_excludes_future_words(self):
        w = db.insert_word("demain", "tomorrow", None, "French")
        # Manually push next_review to tomorrow
        future = (date.today() + timedelta(days=1)).isoformat()
        import sqlite3

        conn = sqlite3.connect(db.DATABASE_PATH)
        conn.execute("UPDATE vocabulary SET next_review = ? WHERE id = ?", (future, w["id"]))
        conn.commit()
        conn.close()
        due = db.get_due_words()
        assert due == []

    def test_includes_overdue_words(self):
        w = db.insert_word("hier", "yesterday", None, "French")
        past = (date.today() - timedelta(days=5)).isoformat()
        import sqlite3

        conn = sqlite3.connect(db.DATABASE_PATH)
        conn.execute("UPDATE vocabulary SET next_review = ? WHERE id = ?", (past, w["id"]))
        conn.commit()
        conn.close()
        due = db.get_due_words()
        assert len(due) == 1


class TestReviewWord:
    def test_passing_review_advances_schedule(self):
        w = db.insert_word("merci", "thank you", None, "French")
        result = db.review_word(w["id"], quality=4)
        assert result is not None
        assert result["repetitions"] == 1
        assert result["next_review"] > date.today().isoformat()

    def test_failing_review_resets_schedule(self):
        # First pass a review to advance state
        w = db.insert_word("oui", "yes", None, "French")
        db.review_word(w["id"], quality=5)
        # Now fail it
        result = db.review_word(w["id"], quality=1)
        assert result["repetitions"] == 0
        assert result["interval"] == 1

    def test_not_found_returns_none(self):
        result = db.review_word(word_id=9999, quality=4)
        assert result is None


class TestDeleteWord:
    def test_deletes_existing_word(self):
        w = db.insert_word("au revoir", "goodbye", None, "French")
        assert db.delete_word(w["id"]) is True
        # Confirm gone
        result = db.get_words(language=None, limit=100, offset=0)
        assert result["total"] == 0

    def test_nonexistent_returns_false(self):
        assert db.delete_word(9999) is False
