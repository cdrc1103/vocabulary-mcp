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


class TestGetDueWordsWithCreatedAfter:
    def test_includes_word_created_today(self):
        """Words created today are included when created_after is today."""
        db.insert_word("bonjour", "hello", None, "French")
        today = date.today().isoformat()
        due = db.get_due_words(created_after=today)
        assert len(due) == 1

    def test_excludes_word_when_filter_is_tomorrow(self):
        """Words created today are excluded when created_after is tomorrow."""
        db.insert_word("bonjour", "hello", None, "French")
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        due = db.get_due_words(created_after=tomorrow)
        assert len(due) == 0

    def test_no_filter_returns_all_due(self):
        """Calling get_due_words() with no argument preserves existing behaviour."""
        db.insert_word("bonjour", "hello", None, "French")
        due = db.get_due_words()
        assert len(due) == 1


class TestSessions:
    def test_get_or_create_session_creates_new(self):
        """Test get_or_create_session inserts and returns a new session."""
        session = db.get_or_create_session("Japanese N5", "2026-06-20")
        assert session["name"] == "Japanese N5"
        assert session["date"] == "2026-06-20"
        assert isinstance(session["id"], int)

    def test_get_or_create_session_returns_existing(self):
        """Test get_or_create_session returns the same row on duplicate name."""
        s1 = db.get_or_create_session("Japanese N5", "2026-06-20")
        s2 = db.get_or_create_session("Japanese N5", "2026-06-21")  # different date ignored
        assert s1["id"] == s2["id"]
        assert s2["date"] == "2026-06-20"  # original date preserved

    def test_get_or_create_session_defaults_date_to_today(self):
        """Test get_or_create_session uses today when no date given."""
        from datetime import date

        session = db.get_or_create_session("No Date Session")
        assert session["date"] == date.today().isoformat()

    def test_get_sessions_ordered_by_date_desc(self):
        """Test get_sessions returns sessions most recent first."""
        db.get_or_create_session("Old", "2026-06-18")
        db.get_or_create_session("New", "2026-06-20")
        sessions = db.get_sessions()
        names = [s["name"] for s in sessions]
        assert names.index("New") < names.index("Old")

    def test_get_sessions_includes_misc(self):
        """Test get_sessions returns the auto-seeded misc session."""
        sessions = db.get_sessions()
        assert any(s["name"] == "misc" for s in sessions)

    def test_insert_word_with_session_name(self):
        """Test insert_word assigns word to named session."""
        word = db.insert_word("bonjour", "hello", None, "fr", session_name="French 1")
        assert word["session_name"] == "French 1"
        assert isinstance(word["session_id"], int)

    def test_insert_word_defaults_to_misc(self):
        """Test insert_word assigns to misc when no session_name given."""
        word = db.insert_word("hola", "hello", None, "es")
        assert word["session_name"] == "misc"

    def test_get_words_filtered_by_session_id(self):
        """Test get_words returns only words in the given session."""
        s = db.get_or_create_session("Spanish 1", "2026-06-20")
        db.insert_word("hola", "hello", None, "es", session_name="Spanish 1")
        db.insert_word("adiós", "goodbye", None, "es")  # goes to misc
        result = db.get_words(language=None, limit=100, offset=0, session_id=s["id"])
        assert result["total"] == 1
        assert result["words"][0]["word"] == "hola"

    def test_get_words_includes_session_name(self):
        """Test get_words includes session_name in each word dict."""
        db.insert_word("ciao", "hi", None, "it", session_name="Italian 1")
        result = db.get_words(language=None, limit=100, offset=0)
        words_by_name = {w["word"]: w for w in result["words"]}
        assert words_by_name["ciao"]["session_name"] == "Italian 1"

    def test_get_due_words_filtered_by_session_id(self):
        """Test get_due_words returns only words in the given session."""
        s = db.get_or_create_session("French 1", "2026-06-20")
        db.insert_word("bonjour", "hello", None, "fr", session_name="French 1")
        db.insert_word("au revoir", "goodbye", None, "fr")  # misc
        due = db.get_due_words(session_id=s["id"])
        words = [w["word"] for w in due]
        assert "bonjour" in words
        assert "au revoir" not in words

    def test_get_due_words_includes_session_name(self):
        """Test get_due_words includes session_name in each word dict."""
        db.insert_word("merci", "thank you", None, "fr", session_name="French 1")
        due = db.get_due_words()
        word = next(w for w in due if w["word"] == "merci")
        assert word["session_name"] == "French 1"

    def test_init_db_is_idempotent(self):
        """Test init_db can be called multiple times without error."""
        db.init_db()
        db.init_db()  # should not raise

    def test_existing_words_migrated_to_misc(self):
        """Test that words with NULL session_id are assigned to misc on init_db."""
        import sqlite3

        import database as db_module

        # Insert a word directly bypassing session logic
        conn = sqlite3.connect(db_module.DATABASE_PATH)
        conn.execute(
            "INSERT INTO vocabulary (word, definition, language) VALUES ('raw', 'raw', 'en')"
        )
        conn.commit()
        conn.close()
        db.init_db()  # re-run migration
        result = db.get_words(language=None, limit=100, offset=0)
        raw = next(w for w in result["words"] if w["word"] == "raw")
        assert raw["session_name"] == "misc"

    def test_bulk_insert_assigns_session_name(self):
        """Test insert_words_bulk assigns session to all words."""
        result = db.insert_words_bulk(
            [
                {"word": "x", "definition": "x", "language": "en", "session_name": "Session A"},
                {"word": "y", "definition": "y", "language": "en", "session_name": "Session A"},
            ]
        )
        assert len(result["inserted"]) == 2
        assert all(w["session_name"] == "Session A" for w in result["inserted"])

    def test_bulk_insert_mixed_sessions(self):
        """Test insert_words_bulk handles words with different session names."""
        result = db.insert_words_bulk(
            [
                {"word": "x", "definition": "x", "language": "en", "session_name": "Sess A"},
                {"word": "y", "definition": "y", "language": "en", "session_name": "Sess B"},
            ]
        )
        inserted_by_word = {w["word"]: w for w in result["inserted"]}
        assert inserted_by_word["x"]["session_name"] == "Sess A"
        assert inserted_by_word["y"]["session_name"] == "Sess B"


class TestDeleteWordsBySession:
    def test_returns_word_count_when_session_has_words(self):
        """Test delete_words_by_session returns count of deleted words."""
        db.insert_word("hola", "hello", None, "es", session_name="Spanish 1")
        db.insert_word("adios", "goodbye", None, "es", session_name="Spanish 1")
        session = db.get_or_create_session("Spanish 1")
        result = db.delete_words_by_session(session["id"])
        assert result == 2

    def test_returns_zero_when_session_has_no_words(self):
        """Test delete_words_by_session returns 0 when session exists with no words."""
        session = db.get_or_create_session("Empty Session")
        result = db.delete_words_by_session(session["id"])
        assert result == 0

    def test_returns_none_when_session_not_found(self):
        """Test delete_words_by_session returns None for unknown session_id."""
        result = db.delete_words_by_session(9999)
        assert result is None

    def test_words_are_removed_after_delete(self):
        """Test vocabulary words no longer exist after session delete."""
        db.insert_word("hola", "hello", None, "es", session_name="Spanish 1")
        session = db.get_or_create_session("Spanish 1")
        db.delete_words_by_session(session["id"])
        words = db.get_words(language=None, limit=100, offset=0)["words"]
        assert not any(w["word"] == "hola" for w in words)

    def test_session_record_is_removed_after_delete(self):
        """Test session record no longer exists after delete."""
        session = db.get_or_create_session("To Delete")
        db.delete_words_by_session(session["id"])
        sessions = db.get_sessions()
        assert not any(s["name"] == "To Delete" for s in sessions)

    def test_only_deletes_words_in_target_session(self):
        """Test words in other sessions are unaffected by delete."""
        db.insert_word("hola", "hello", None, "es", session_name="Spanish 1")
        db.insert_word("bonjour", "hello", None, "fr", session_name="French 1")
        spanish = db.get_or_create_session("Spanish 1")
        db.delete_words_by_session(spanish["id"])
        words = db.get_words(language=None, limit=100, offset=0)["words"]
        assert any(w["word"] == "bonjour" for w in words)
        assert not any(w["word"] == "hola" for w in words)
