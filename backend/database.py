import os
import sqlite3
from datetime import UTC, date, datetime, timedelta

"""Database operations for vocabulary management.

Provides SQLite database access for vocabulary words, including CRUD operations,
SRS (SM-2) calculations, and spaced repetition scheduling. Database is initialized
on app startup and persists vocabulary with review intervals.
"""

DATABASE_PATH = os.getenv("DATABASE_PATH", "./vocab.db")


def get_connection() -> sqlite3.Connection:
    """Open a connection to the SQLite database.

    Returns:
        sqlite3.Connection: Database connection with Row factory enabled.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize SQLite database and create vocabulary table if missing.

    Creates the vocabulary table with columns for word metadata and SM-2 algorithm state.
    Called during application startup via lifespan context manager.
    """
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vocabulary (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                word        TEXT NOT NULL,
                definition  TEXT NOT NULL,
                example     TEXT,
                language    TEXT DEFAULT 'unknown',
                created_at  TEXT DEFAULT (datetime('now')),

                interval        INTEGER DEFAULT 1,
                ease_factor     REAL DEFAULT 2.5,
                repetitions     INTEGER DEFAULT 0,
                next_review     TEXT DEFAULT (date('now'))
            )
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uix_word_language
            ON vocabulary (word, language)
        """)


def apply_sm2(interval: int, ease: float, reps: int, quality: int):
    """Apply SM-2 spaced repetition algorithm to calculate next interval and ease factor.

    SM-2 (SuperMemo 2) is an algorithm for optimizing review intervals based on
    response quality. Higher quality scores increase ease factor and interval.

    Args:
        interval: Current review interval in days.
        ease: Current ease factor (difficulty multiplier).
        reps: Number of successful repetitions.
        quality: Quality score from review (0-5, where 3+ is passing).

    Returns:
        Tuple of (new_interval, new_ease, new_reps) for the updated SM-2 state.
    """
    if quality < 3:
        return 1, ease, 0
    else:
        if reps == 0:
            new_interval = 1
        elif reps == 1:
            new_interval = 6
        else:
            new_interval = round(interval * ease)

        new_ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        new_ease = max(1.3, new_ease)
        return new_interval, new_ease, reps + 1


def insert_word(word: str, definition: str, example: str | None, language: str) -> dict:
    """Insert a new vocabulary word with SRS metadata.

    Args:
        word: The vocabulary word.
        definition: Definition of the word.
        example: Optional example sentence.
        language: Language code or name.

    Returns:
        Dictionary with word data including id, created_at, and SM-2 fields.
    """
    # Compute defaults in Python so we can return them without a second SELECT.
    created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    next_review = date.today().isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO vocabulary (word, definition, example, language, created_at, next_review)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (word, definition, example, language, created_at, next_review),
        )
    return {
        "id": cursor.lastrowid,
        "word": word,
        "definition": definition,
        "example": example,
        "language": language,
        "created_at": created_at,
        "next_review": next_review,
        "interval": 1,
        "ease_factor": 2.5,
        "repetitions": 0,
    }


def insert_words_bulk(words: list[dict]) -> dict:
    """Insert multiple vocabulary words in a single transaction.

    Uses INSERT OR IGNORE to skip duplicates (word + language combinations).
    Useful for bulk imports where some words may already exist.

    Args:
        words: List of dictionaries with word, definition, example, language keys.

    Returns:
        Dictionary with 'inserted' list of created VocabularyResponse objects and
        'skipped_count' for duplicate entries not inserted.
    """
    if not words:
        return {"inserted": [], "skipped_count": 0}

    created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    next_review = date.today().isoformat()

    with get_connection() as conn:
        inserted = []
        for w in words:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO vocabulary
                    (word, definition, example, language, created_at, next_review)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    w["word"],
                    w["definition"],
                    w.get("example"),
                    w.get("language", "unknown"),
                    created_at,
                    next_review,
                ),
            )
            if cursor.rowcount > 0:
                inserted.append(
                    {
                        "id": cursor.lastrowid,
                        "word": w["word"],
                        "definition": w["definition"],
                        "example": w.get("example"),
                        "language": w.get("language", "unknown"),
                        "created_at": created_at,
                        "next_review": next_review,
                        "interval": 1,
                        "ease_factor": 2.5,
                        "repetitions": 0,
                    }
                )

    return {"inserted": inserted, "skipped_count": len(words) - len(inserted)}


def get_words(language: str | None, limit: int, offset: int) -> dict:
    """Retrieve paginated vocabulary words.

    Args:
        language: Optional filter by language code. If None, returns all words.
        limit: Max number of results (typically 100).
        offset: Number of results to skip for pagination.

    Returns:
        Dictionary with 'total' count and 'words' list of vocabulary dicts.
    """
    where = "WHERE language = ?" if language else ""
    count_params = (language,) if language else ()
    page_params = (language, limit, offset) if language else (limit, offset)
    with get_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM vocabulary {where}", count_params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM vocabulary {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            page_params,
        ).fetchall()
    return {"total": total, "words": [dict(r) for r in rows]}


def get_due_words() -> list[dict]:
    """Retrieve words with next_review <= now (due for study).

    Returns:
        List of vocabulary dicts for words ready to review, ordered by next_review date.
    """
    today = date.today().isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM vocabulary WHERE next_review <= ? ORDER BY next_review ASC",
            (today,),
        ).fetchall()
        return [dict(r) for r in rows]


def review_word(word_id: int, quality: int) -> dict | None:
    """Submit a review for a word and update SM-2 algorithm state.

    Applies the SM-2 algorithm to calculate new interval, ease factor, and
    repetition count. Updates next_review date based on new interval.

    Args:
        word_id: ID of the word being reviewed.
        quality: SM-2 quality score (0-5, where 3+ is passing).

    Returns:
        Updated vocabulary dict with new SM-2 state, or None if word_id not found.
    """
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM vocabulary WHERE id = ?", (word_id,)).fetchone()
        if row is None:
            return None

        row = dict(row)
        new_interval, new_ease, new_reps = apply_sm2(
            row["interval"], row["ease_factor"], row["repetitions"], quality
        )
        next_review = (date.today() + timedelta(days=new_interval)).isoformat()

        conn.execute(
            """
            UPDATE vocabulary
            SET interval = ?, ease_factor = ?, repetitions = ?, next_review = ?
            WHERE id = ?
            """,
            (new_interval, new_ease, new_reps, next_review, word_id),
        )

    # Return merged dict from the pre-fetch + computed SM-2 values — no second SELECT needed.
    return {
        **row,
        "interval": new_interval,
        "ease_factor": new_ease,
        "repetitions": new_reps,
        "next_review": next_review,
    }


def delete_word(word_id: int) -> bool:
    """Delete a vocabulary word by ID.

    Args:
        word_id: ID of the word to delete.

    Returns:
        True if word was deleted, False if word_id not found.
    """
    with get_connection() as conn:
        result = conn.execute("DELETE FROM vocabulary WHERE id = ?", (word_id,))
        return result.rowcount > 0
