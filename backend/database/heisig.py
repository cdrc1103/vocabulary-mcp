"""Database operations for Heisig hanzi integration.

Provides SQLite access for the hanzi upsert flow. General vocabulary CRUD
lives in database.general.
"""

import sqlite3
from datetime import UTC, date, datetime

from database.general import get_connection, get_or_create_session


def _fetch_card(conn: sqlite3.Connection, vocab_id: int) -> dict:
    """Fetch one card joined with its session name.

    Args:
        conn: Open SQLite connection.
        vocab_id: The card id to fetch.

    Returns:
        Card dict including session_name.
    """
    row = conn.execute(
        """
        SELECT v.*, s.name AS session_name
        FROM vocabulary v
        LEFT JOIN sessions s ON v.session_id = s.id
        WHERE v.id = ?
        """,
        (vocab_id,),
    ).fetchone()
    return dict(row)


def upsert_hanzi(
    word: str,
    keyword: str,
    pinyin: str,
    tone: int,
    definition: str | None = None,
    example: str | None = None,
    session_name: str | None = None,
) -> dict:
    """Create or enrich a Heisig hanzi card, matching an existing card by word alone.

    Applies the upsert policies: match by word; normalize language to
    "Chinese" on create; on enrich touch only keyword/pinyin/tone (never
    SM-2, definition, example, or session); report created/enriched/unchanged.

    Args:
        word: The hanzi character.
        keyword: Single Heisig keyword.
        pinyin: Pinyin with tone mark (e.g. "míng").
        tone: Tone number 1-5 (5 = neutral).
        definition: Meaning/usage for a new card; ignored on enrich. Defaults to keyword.
        example: Optional usage sentence for a new card; ignored on enrich.
        session_name: Session for a new card only; never moves an existing card.

    Returns:
        Dict with "status" ("created"|"enriched"|"unchanged") and "card".
    """
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM vocabulary WHERE word = ?", (word,)).fetchone()

        if existing is None:
            created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            next_review = date.today().isoformat()
            session = get_or_create_session(session_name or "misc")
            cur = conn.execute(
                """
                INSERT INTO vocabulary
                    (word, definition, example, language, created_at, next_review, session_id,
                     keyword, pinyin, tone)
                VALUES (?, ?, ?, 'Chinese', ?, ?, ?, ?, ?, ?)
                """,
                (
                    word,
                    definition or keyword,
                    example,
                    created_at,
                    next_review,
                    session["id"],
                    keyword,
                    pinyin,
                    tone,
                ),
            )
            vocab_id = cur.lastrowid
            return {"status": "created", "card": _fetch_card(conn, vocab_id)}

        existing = dict(existing)
        vocab_id = existing["id"]
        fields_unchanged = (
            existing["keyword"] == keyword
            and existing["pinyin"] == pinyin
            and existing["tone"] == tone
        )
        if fields_unchanged:
            return {"status": "unchanged", "card": _fetch_card(conn, vocab_id)}

        conn.execute(
            "UPDATE vocabulary SET keyword = ?, pinyin = ?, tone = ? WHERE id = ?",
            (keyword, pinyin, tone, vocab_id),
        )
        return {"status": "enriched", "card": _fetch_card(conn, vocab_id)}
