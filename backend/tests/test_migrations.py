"""Tests for the PRAGMA user_version migration runner and Heisig schema."""

import sqlite3

import database.general as db


def _columns(conn, table):
    """Return the set of column names for a given table.

    Args:
        conn: Open SQLite connection.
        table: Table name to inspect.

    Returns:
        Set of column name strings.
    """
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _tables(conn):
    """Return the set of table names in the database.

    Args:
        conn: Open SQLite connection.

    Returns:
        Set of table name strings.
    """
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


class TestMigrations:
    """Tests for the versioned migration runner and Heisig schema."""

    def test_fresh_db_reaches_latest_version(self, tmp_db):
        """A fresh DB ends at the latest user_version."""
        with db.get_connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            assert version == len(db.MIGRATIONS)

    def test_vocabulary_has_hanzi_columns(self, tmp_db):
        """vocabulary keeps keyword, pinyin, tone for hanzi cards."""
        with db.get_connection() as conn:
            cols = _columns(conn, "vocabulary")
        assert {"keyword", "pinyin", "tone"} <= cols

    def test_story_and_story_edited_columns_dropped(self, tmp_db):
        """story and story_edited no longer exist on a fresh DB."""
        with db.get_connection() as conn:
            cols = _columns(conn, "vocabulary")
        assert "story" not in cols
        assert "story_edited" not in cols

    def test_primitive_tables_removed(self, tmp_db):
        """primitives and card_primitives tables no longer exist."""
        with db.get_connection() as conn:
            names = _tables(conn)
        assert "primitives" not in names
        assert "card_primitives" not in names

    def test_migrations_are_idempotent(self, tmp_db):
        """Running init_db again does not error or change version."""
        db.init_db()
        db.init_db()
        with db.get_connection() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)

    def test_legacy_db_upgrades_without_error(self, tmp_path, monkeypatch):
        """A pre-migration DB (only baseline tables, user_version 0) upgrades cleanly."""
        legacy = str(tmp_path / "legacy.db")
        conn = sqlite3.connect(legacy)
        conn.executescript(
            "CREATE TABLE sessions (id INTEGER PRIMARY KEY, name TEXT UNIQUE, date TEXT, created_at TEXT);"
            "CREATE TABLE vocabulary (id INTEGER PRIMARY KEY, word TEXT, definition TEXT, example TEXT, "
            "language TEXT, created_at TEXT, interval INTEGER, ease_factor REAL, repetitions INTEGER, "
            "next_review TEXT, session_id INTEGER);"
        )
        conn.commit()
        conn.close()
        monkeypatch.setattr(db, "DATABASE_PATH", legacy)
        db.init_db()
        with db.get_connection() as conn:
            cols = _columns(conn, "vocabulary")
            assert "keyword" in cols
            assert "story" not in cols
            assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)

    def test_v3_db_with_story_data_upgrades_and_keeps_hanzi_fields(self, tmp_path, monkeypatch):
        """A DB already on v3 (with primitives/story) upgrades to v4, drops story,
        and keeps keyword/pinyin/tone for existing hanzi cards."""
        legacy = str(tmp_path / "v3.db")
        monkeypatch.setattr(db, "DATABASE_PATH", legacy)
        full_migrations = db.MIGRATIONS
        monkeypatch.setattr(db, "MIGRATIONS", full_migrations[:3])
        db.init_db()
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO vocabulary (word, definition, language, keyword, pinyin, tone, story) "
                "VALUES ('明', 'bright', 'Chinese', 'bright', 'míng', 2, 'sun and moon')"
            )
        monkeypatch.setattr(db, "MIGRATIONS", full_migrations)
        db.init_db()
        with db.get_connection() as conn:
            cols = _columns(conn, "vocabulary")
            assert "story" not in cols
            row = conn.execute(
                "SELECT keyword, pinyin, tone FROM vocabulary WHERE word = '明'"
            ).fetchone()
            assert tuple(row) == ("bright", "míng", 2)
