"""Database operations for Heisig hanzi integration.

Provides SQLite access for the primitive registry, card-primitive links, and
the hanzi upsert flow. General vocabulary CRUD lives in database.general.
"""

import sqlite3
from datetime import UTC, date, datetime

from database.general import _attach_primitives, get_connection, get_or_create_session


def _upsert_primitive(
    conn: sqlite3.Connection, component: str, keyword: str, note: str | None
) -> int:
    """Insert or reuse a primitive within an open connection (first-write-wins).

    On first insert, assigns the next rank and stores the keyword. If the
    component already exists, the keyword is never changed; ``note`` is filled
    only when the stored note is currently NULL.

    Args:
        conn: Open SQLite connection.
        component: The primitive's shape/character (unique key).
        keyword: The fixed keyword for this component.
        note: Optional gloss; only applied if no note is stored yet.

    Returns:
        The primitive's row id.
    """
    row = conn.execute(
        "SELECT id, note FROM primitives WHERE component = ?", (component,)
    ).fetchone()
    if row is None:
        next_rank = conn.execute("SELECT COALESCE(MAX(rank), 0) + 1 FROM primitives").fetchone()[0]
        cur = conn.execute(
            "INSERT INTO primitives (component, keyword, note, rank) VALUES (?, ?, ?, ?)",
            (component, keyword, note, next_rank),
        )
        return cur.lastrowid
    if note is not None and row["note"] is None:
        conn.execute("UPDATE primitives SET note = ? WHERE id = ?", (note, row["id"]))
    return row["id"]


def upsert_primitive(component: str, keyword: str, note: str | None = None) -> dict:
    """Insert or reuse a primitive (first-write-wins) and return its row.

    Args:
        component: The primitive's shape/character (unique key).
        keyword: The fixed keyword for this component.
        note: Optional gloss; applied only if no note is stored yet.

    Returns:
        Dict with id, component, keyword, note, rank.
    """
    with get_connection() as conn:
        prim_id = _upsert_primitive(conn, component, keyword, note)
        row = conn.execute("SELECT * FROM primitives WHERE id = ?", (prim_id,)).fetchone()
    return dict(row)


def get_primitives() -> list[dict]:
    """Return all primitives ordered by rank (introduction order).

    Returns:
        List of dicts with id, component, keyword, note, rank.
    """
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM primitives ORDER BY rank").fetchall()
    return [dict(r) for r in rows]


def replace_card_primitives(conn: sqlite3.Connection, vocabulary_id: int, refs: list[dict]) -> None:
    """Rewrite a card's primitive links (upserting each referenced primitive first).

    Existing links for the card are deleted and replaced with the given refs,
    preserving their order via ``position``.

    Args:
        conn: Open SQLite connection inside the caller's transaction.
        vocabulary_id: The card whose links are being replaced.
        refs: List of dicts with component, keyword, note, position.
    """
    conn.execute("DELETE FROM card_primitives WHERE vocabulary_id = ?", (vocabulary_id,))
    for ref in refs:
        prim_id = _upsert_primitive(conn, ref["component"], ref["keyword"], ref.get("note"))
        conn.execute(
            "INSERT INTO card_primitives (vocabulary_id, primitive_id, position) VALUES (?, ?, ?)",
            (vocabulary_id, prim_id, ref["position"]),
        )


def _fetch_card(conn: sqlite3.Connection, vocab_id: int) -> dict:
    """Fetch one card joined with its session name and primitive list.

    Args:
        conn: Open SQLite connection.
        vocab_id: The card id to fetch.

    Returns:
        Card dict including session_name and an ordered primitives list.
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
    card = dict(row)
    _attach_primitives(conn, [card])
    return card


def upsert_hanzi(
    word: str,
    keyword: str,
    pinyin: str,
    tone: int,
    story: str,
    primitives: list[dict],
    definition: str | None = None,
    example: str | None = None,
    session_name: str | None = None,
) -> dict:
    """Create or enrich a Heisig hanzi card, matching an existing card by word alone.

    Applies the six upsert policies: match by word; normalize language to
    "Chinese" on create; first-write-wins on the primitive registry; on enrich
    touch only Heisig fields (never SM-2, definition, example, or session); do
    not clobber a story when story_edited=1; report created/enriched/unchanged.

    Args:
        word: The hanzi character.
        keyword: Single Heisig keyword.
        pinyin: Pinyin with tone mark (e.g. "míng").
        tone: Tone number 1-5 (5 = neutral).
        story: Mnemonic story with the tone cue baked in.
        primitives: List of dicts with component, keyword, note, position.
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
                     keyword, pinyin, tone, story, story_edited)
                VALUES (?, ?, ?, 'Chinese', ?, ?, ?, ?, ?, ?, ?, 0)
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
                    story,
                ),
            )
            vocab_id = cur.lastrowid
            replace_card_primitives(conn, vocab_id, primitives)
            return {"status": "created", "card": _fetch_card(conn, vocab_id)}

        existing = dict(existing)
        vocab_id = existing["id"]
        effective_story = existing["story"] if existing["story_edited"] else story

        current_prims = conn.execute(
            "SELECT primitive_id, position FROM card_primitives WHERE vocabulary_id = ? ORDER BY position",
            (vocab_id,),
        ).fetchall()
        # Resolve incoming refs to (primitive_id, position) to detect no-op without mutating.
        incoming_ids = []
        for ref in primitives:
            existing_prim = conn.execute(
                "SELECT id FROM primitives WHERE component = ?", (ref["component"],)
            ).fetchone()
            incoming_ids.append((existing_prim["id"] if existing_prim else None, ref["position"]))
        prims_unchanged = all(pid is not None for pid, _ in incoming_ids) and (
            [(r["primitive_id"], r["position"]) for r in current_prims] == incoming_ids
        )
        fields_unchanged = (
            existing["keyword"] == keyword
            and existing["pinyin"] == pinyin
            and existing["tone"] == tone
            and existing["story"] == effective_story
        )
        if fields_unchanged and prims_unchanged:
            return {"status": "unchanged", "card": _fetch_card(conn, vocab_id)}

        conn.execute(
            "UPDATE vocabulary SET keyword = ?, pinyin = ?, tone = ?, story = ? WHERE id = ?",
            (keyword, pinyin, tone, effective_story, vocab_id),
        )
        replace_card_primitives(conn, vocab_id, primitives)
        return {"status": "enriched", "card": _fetch_card(conn, vocab_id)}
