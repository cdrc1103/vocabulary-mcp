"""Tests for the PRAGMA user_version migration runner and Heisig schema."""

import sqlite3

import database as db


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
    """Tests for the versioned migration runner and Heisig schema additions."""

    def test_fresh_db_reaches_latest_version(self, tmp_db):
        """A fresh DB ends at the latest user_version with all Heisig objects."""
        with db.get_connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            assert version == len(db.MIGRATIONS)

    def test_vocabulary_has_heisig_columns(self, tmp_db):
        """vocabulary gains keyword, pinyin, tone, story, story_edited."""
        with db.get_connection() as conn:
            cols = _columns(conn, "vocabulary")
        assert {"keyword", "pinyin", "tone", "story", "story_edited"} <= cols

    def test_primitive_tables_exist(self, tmp_db):
        """primitives and card_primitives tables are created."""
        with db.get_connection() as conn:
            names = _tables(conn)
        assert {"primitives", "card_primitives"} <= names

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
            assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)
