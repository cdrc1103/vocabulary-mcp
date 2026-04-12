"""Tests for database operations.

Tests CRUD operations, SRS calculations, and data persistence.
"""

from datetime import date, timedelta

import database as db
import pytest


@pytest.fixture(autouse=True)
def _fresh_db(tmp_db):
    """Ensure every test in this module uses an isolated database.

    This fixture is automatically used by all tests in this module to
    guarantee database isolation between test runs.

    Args:
        tmp_db: Fixture providing temporary test database.
    """


class TestInsertWord:
    def test_returns_dict_with_all_fields(self):
        """Test insert_word returns dictionary with all expected fields."""
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
        """Test that newly inserted word has next_review set to today."""
        result = db.insert_word("ciao", "bye", None, "Italian")
        assert result["next_review"] == date.today().isoformat()

    def test_example_can_be_none(self):
        """Test that example field can be None/optional."""
        result = db.insert_word("hola", "hi", None, "Spanish")
        assert result["example"] is None

    def test_ids_are_unique(self):
        """Test that each inserted word receives a unique ID."""
        r1 = db.insert_word("a", "a", None, "en")
        r2 = db.insert_word("b", "b", None, "en")
        assert r1["id"] != r2["id"]


class TestGetWords:
    def test_empty_db_returns_zero_total(self):
        """Test get_words returns empty list when database is empty."""
        result = db.get_words(language=None, limit=100, offset=0)
        assert result["total"] == 0
        assert result["words"] == []

    def test_returns_inserted_words(self):
        """Test get_words returns previously inserted vocabulary words."""
        db.insert_word("chat", "cat", None, "French")
        db.insert_word("chien", "dog", None, "French")
        result = db.get_words(language=None, limit=100, offset=0)
        assert result["total"] == 2

    def test_language_filter(self):
        """Test get_words filters by language parameter."""
        db.insert_word("chat", "cat", None, "French")
        db.insert_word("gato", "cat", None, "Spanish")
        fr = db.get_words(language="French", limit=100, offset=0)
        assert fr["total"] == 1
        assert fr["words"][0]["word"] == "chat"

    def test_pagination_limit(self):
        """Test get_words respects limit parameter for result size."""
        for i in range(5):
            db.insert_word(f"word{i}", "def", None, "en")
        result = db.get_words(language=None, limit=2, offset=0)
        assert len(result["words"]) == 2
        assert result["total"] == 5

    def test_pagination_offset(self):
        """Test get_words respects offset parameter for pagination."""
        for i in range(5):
            db.insert_word(f"word{i}", "def", None, "en")
        result = db.get_words(language=None, limit=10, offset=3)
        assert len(result["words"]) == 2


class TestGetDueWords:
    def test_returns_word_due_today(self):
        """Test get_due_words returns words scheduled for review today."""
        db.insert_word("aujourd'hui", "today", None, "French")
        due = db.get_due_words()
        assert len(due) == 1

    def test_excludes_future_words(self):
        """Test get_due_words excludes words scheduled for future dates."""
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
        """Test get_due_words includes words past their review date."""
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
        """Test review_word with good quality advances SM-2 schedule."""
        w = db.insert_word("merci", "thank you", None, "French")
        result = db.review_word(w["id"], quality=4)
        assert result is not None
        assert result["repetitions"] == 1
        assert result["next_review"] > date.today().isoformat()

    def test_failing_review_resets_schedule(self):
        """Test review_word with low quality resets SM-2 schedule."""
        # First pass a review to advance state
        w = db.insert_word("oui", "yes", None, "French")
        db.review_word(w["id"], quality=5)
        # Now fail it
        result = db.review_word(w["id"], quality=1)
        assert result["repetitions"] == 0
        assert result["interval"] == 1

    def test_not_found_returns_none(self):
        """Test review_word returns None for non-existent word."""
        result = db.review_word(word_id=9999, quality=4)
        assert result is None


class TestInsertWordsBulk:
    def test_inserts_multiple_words(self):
        """Test insert_words_bulk creates multiple words in single operation."""
        words = [
            {"word": "bonjour", "definition": "hello", "example": None, "language": "French"},
            {
                "word": "merci",
                "definition": "thanks",
                "example": "Merci beaucoup.",
                "language": "French",
            },
        ]
        result = db.insert_words_bulk(words)
        assert len(result["inserted"]) == 2
        assert result["skipped_count"] == 0
        assert result["inserted"][0]["word"] == "bonjour"
        assert result["inserted"][1]["word"] == "merci"

    def test_skips_duplicates(self):
        """Test insert_words_bulk skips words that already exist."""
        db.insert_word("bonjour", "hello", None, "French")
        words = [
            {"word": "bonjour", "definition": "hello again", "example": None, "language": "French"},
            {"word": "merci", "definition": "thanks", "example": None, "language": "French"},
        ]
        result = db.insert_words_bulk(words)
        assert len(result["inserted"]) == 1
        assert result["inserted"][0]["word"] == "merci"
        assert result["skipped_count"] == 1

    def test_skips_intra_batch_duplicates(self):
        """Test insert_words_bulk skips duplicates within the batch."""
        words = [
            {"word": "oui", "definition": "yes", "example": None, "language": "French"},
            {"word": "oui", "definition": "yes again", "example": None, "language": "French"},
        ]
        result = db.insert_words_bulk(words)
        assert len(result["inserted"]) == 1
        assert result["skipped_count"] == 1

    def test_empty_list_returns_empty(self):
        """Test insert_words_bulk handles empty word list."""
        result = db.insert_words_bulk([])
        assert result == {"inserted": [], "skipped_count": 0}

    def test_same_word_different_language_both_inserted(self):
        """Test insert_words_bulk allows same word with different languages."""
        words = [
            {"word": "chat", "definition": "cat", "example": None, "language": "French"},
            {"word": "chat", "definition": "to chat", "example": None, "language": "English"},
        ]
        result = db.insert_words_bulk(words)
        assert len(result["inserted"]) == 2
        assert result["skipped_count"] == 0

    def test_inserted_words_have_correct_defaults(self):
        """Test bulk inserted words have correct SM-2 defaults."""
        words = [{"word": "salut", "definition": "hi", "example": None, "language": "French"}]
        result = db.insert_words_bulk(words)
        row = result["inserted"][0]
        assert isinstance(row["id"], int)
        assert row["interval"] == 1
        assert row["ease_factor"] == 2.5
        assert row["repetitions"] == 0
        assert row["created_at"] is not None
        assert row["next_review"] == date.today().isoformat()


class TestDeleteWord:
    def test_deletes_existing_word(self):
        """Test delete_word removes word from database."""
        w = db.insert_word("au revoir", "goodbye", None, "French")
        assert db.delete_word(w["id"]) is True
        # Confirm gone
        result = db.get_words(language=None, limit=100, offset=0)
        assert result["total"] == 0

    def test_nonexistent_returns_false(self):
        """Test delete_word returns False for non-existent word."""
        assert db.delete_word(9999) is False
