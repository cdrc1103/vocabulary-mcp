"""Database operations for general vocabulary management.

Provides SQLite database access for vocabulary words and sessions, including CRUD
operations, SRS (SM-2) calculations, and spaced repetition scheduling. Sessions
allow grouping vocabulary by named study topics.

Heisig hanzi-specific operations (primitive registry, upsert_hanzi) live in
database.heisig.
"""

import os
import sqlite3
from datetime import UTC, date, datetime, timedelta

DATABASE_PATH = os.getenv("DATABASE_PATH", "./vocab.db")


def get_connection() -> sqlite3.Connection:
    """Open a connection to the SQLite database.

    Returns:
        sqlite3.Connection: Database connection with Row factory enabled.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_v1_baseline(conn: sqlite3.Connection) -> None:
    """Baseline schema (idempotent): sessions, vocabulary, unique index, misc seed.

    Written with IF NOT EXISTS / INSERT OR IGNORE so it is a no-op on databases
    created before the migration runner existed.

    Args:
        conn: Open SQLite connection inside the migration transaction.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL UNIQUE,
            date       TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
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
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(vocabulary)").fetchall()}
    if "session_id" not in existing_cols:
        conn.execute("ALTER TABLE vocabulary ADD COLUMN session_id INTEGER REFERENCES sessions(id)")
    today = date.today().isoformat()
    conn.execute("INSERT OR IGNORE INTO sessions (name, date) VALUES ('misc', ?)", (today,))
    conn.execute("""
        UPDATE vocabulary
        SET session_id = (SELECT id FROM sessions WHERE name = 'misc')
        WHERE session_id IS NULL
    """)


def _migrate_v2_heisig_columns(conn: sqlite3.Connection) -> None:
    """Add Heisig fields to vocabulary.

    Each ALTER TABLE is guarded by a column-existence check so the migration
    is idempotent and safe to re-run after a crash.

    Args:
        conn: Open SQLite connection inside the migration transaction.
    """
    existing = {r[1] for r in conn.execute("PRAGMA table_info(vocabulary)").fetchall()}
    for col, typedef in [
        ("keyword", "TEXT"),
        ("pinyin", "TEXT"),
        ("tone", "INTEGER"),
        ("story", "TEXT"),
        ("story_edited", "INTEGER DEFAULT 0"),
    ]:
        if col not in existing:
            conn.execute(f"ALTER TABLE vocabulary ADD COLUMN {col} {typedef}")


def _migrate_v3_primitive_tables(conn: sqlite3.Connection) -> None:
    """Create the primitives registry and the card_primitives join table.

    Uses IF NOT EXISTS so the migration is idempotent and safe to re-run
    after a crash.

    Args:
        conn: Open SQLite connection inside the migration transaction.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS primitives (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            component  TEXT NOT NULL UNIQUE,
            keyword    TEXT NOT NULL,
            note       TEXT,
            rank       INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS card_primitives (
            vocabulary_id INTEGER NOT NULL REFERENCES vocabulary(id) ON DELETE CASCADE,
            primitive_id  INTEGER NOT NULL REFERENCES primitives(id),
            position      INTEGER NOT NULL,
            PRIMARY KEY (vocabulary_id, primitive_id)
        )
    """)


# Ordered migrations. Index + 1 == the user_version they bring the DB to.
MIGRATIONS = [
    _migrate_v1_baseline,
    _migrate_v2_heisig_columns,
    _migrate_v3_primitive_tables,
]


def init_db() -> None:
    """Initialize the database by applying all pending migrations in order.

    Uses SQLite's built-in ``PRAGMA user_version`` as the schema version counter.
    Each migration with an index greater than the current version is applied in
    order inside a single transaction, and the version is bumped after each.
    Safe to call repeatedly; already-applied migrations are skipped.
    """
    with get_connection() as conn:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        for i, migration in enumerate(MIGRATIONS, start=1):
            if current < i:
                migration(conn)
                conn.execute(f"PRAGMA user_version = {i}")


def get_or_create_session(name: str, session_date: str | None = None) -> dict:
    """Get an existing session by name or create it if it does not exist.

    Uses INSERT OR IGNORE so concurrent/duplicate calls with the same name
    are no-ops on the INSERT; the subsequent SELECT always returns the canonical row.

    Args:
        name: Session name (unique key).
        session_date: ISO date string YYYY-MM-DD. Defaults to today if None.

    Returns:
        Dictionary with session id, name, date, and created_at.
    """
    resolved_date = session_date or date.today().isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sessions (name, date) VALUES (?, ?)",
            (name, resolved_date),
        )
        row = conn.execute("SELECT * FROM sessions WHERE name = ?", (name,)).fetchone()
    return dict(row)


def get_sessions() -> list[dict]:
    """Return all sessions ordered by date descending.

    Returns:
        List of session dicts with id, name, date, created_at.
    """
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM sessions ORDER BY date DESC").fetchall()
    return [dict(r) for r in rows]


def _attach_primitives(conn: sqlite3.Connection, cards: list[dict]) -> None:
    """Attach an ordered ``primitives`` list to each card dict in place.

    Args:
        conn: Open SQLite connection.
        cards: List of card dicts each containing an ``id`` key.
    """
    if not cards:
        return
    ids = [c["id"] for c in cards]
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""
        SELECT cp.vocabulary_id, p.id, p.component, p.keyword, p.note, p.rank, cp.position
        FROM card_primitives cp
        JOIN primitives p ON cp.primitive_id = p.id
        WHERE cp.vocabulary_id IN ({placeholders})
        ORDER BY cp.position
        """,
        ids,
    ).fetchall()
    by_card: dict[int, list[dict]] = {}
    for r in rows:
        by_card.setdefault(r["vocabulary_id"], []).append(
            {
                "id": r["id"],
                "component": r["component"],
                "keyword": r["keyword"],
                "note": r["note"],
                "rank": r["rank"],
                "position": r["position"],
            }
        )
    for c in cards:
        c["primitives"] = by_card.get(c["id"], [])


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


def insert_word(
    word: str,
    definition: str,
    example: str | None,
    language: str,
    session_name: str | None = None,
) -> dict:
    """Insert a new vocabulary word with SRS metadata.

    Args:
        word: The vocabulary word.
        definition: Definition of the word.
        example: Optional example sentence.
        language: Language code or name.
        session_name: Session to assign the word to. Defaults to 'misc'.

    Returns:
        Dictionary with word data including id, created_at, SM-2 fields, session_id, session_name.
    """
    created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    next_review = date.today().isoformat()
    resolved_name = session_name or "misc"
    session = get_or_create_session(resolved_name)
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO vocabulary (word, definition, example, language, created_at, next_review, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (word, definition, example, language, created_at, next_review, session["id"]),
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
        "session_id": session["id"],
        "session_name": resolved_name,
    }


def insert_words_bulk(words: list[dict]) -> dict:
    """Insert multiple vocabulary words in a single transaction.

    Uses INSERT OR IGNORE to skip duplicates (word + language combinations).
    Resolves unique session names to IDs upfront via upsert, then assigns
    each word its session_id.

    Args:
        words: List of dicts with word, definition, example, language, session_name keys.

    Returns:
        Dictionary with 'inserted' list of created word dicts and 'skipped_count'.
    """
    if not words:
        return {"inserted": [], "skipped_count": 0}

    created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    next_review = date.today().isoformat()

    unique_names = {w.get("session_name") or "misc" for w in words}
    session_map = {name: get_or_create_session(name) for name in unique_names}

    with get_connection() as conn:
        inserted = []
        for w in words:
            sname = w.get("session_name") or "misc"
            session = session_map[sname]
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO vocabulary
                    (word, definition, example, language, created_at, next_review, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    w["word"],
                    w["definition"],
                    w.get("example"),
                    w.get("language", "unknown"),
                    created_at,
                    next_review,
                    session["id"],
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
                        "session_id": session["id"],
                        "session_name": sname,
                    }
                )

    return {"inserted": inserted, "skipped_count": len(words) - len(inserted)}


def get_words(
    language: str | None,
    limit: int,
    offset: int,
    session_id: int | None = None,
) -> dict:
    """Retrieve paginated vocabulary words including session info.

    Args:
        language: Optional filter by language code. If None, returns all languages.
        limit: Max number of results (typically 100).
        offset: Number of results to skip for pagination.
        session_id: Optional filter by session ID.

    Returns:
        Dictionary with 'total' count and 'words' list. Each word includes session_name.
    """
    conditions: list[str] = []
    params: list = []
    if language:
        conditions.append("v.language = ?")
        params.append(language)
    if session_id is not None:
        conditions.append("v.session_id = ?")
        params.append(session_id)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with get_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM vocabulary v {where}", params).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT v.*, s.name AS session_name
            FROM vocabulary v
            LEFT JOIN sessions s ON v.session_id = s.id
            {where}
            ORDER BY v.created_at DESC LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        cards = [dict(r) for r in rows]
        _attach_primitives(conn, cards)
    return {"total": total, "words": cards}


def get_due_words(
    created_after: str | None = None,
    session_id: int | None = None,
) -> list[dict]:
    """Retrieve words with next_review <= now (due for study).

    Args:
        created_after: Optional ISO date string (YYYY-MM-DD). Filters to words
            created on or after this date.
        session_id: Optional filter by session ID. Stacks with created_after (AND).

    Returns:
        List of vocabulary dicts including session_name, ordered by next_review ASC.
    """
    today = date.today().isoformat()
    conditions = ["v.next_review <= ?"]
    params: list = [today]
    if created_after:
        conditions.append("v.created_at >= ?")
        params.append(created_after)
    if session_id is not None:
        conditions.append("v.session_id = ?")
        params.append(session_id)
    where = "WHERE " + " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT v.*, s.name AS session_name
            FROM vocabulary v
            LEFT JOIN sessions s ON v.session_id = s.id
            {where}
            ORDER BY v.next_review ASC
            """,
            params,
        ).fetchall()
        cards = [dict(r) for r in rows]
        _attach_primitives(conn, cards)
    return cards


def review_word(word_id: int, quality: int) -> dict | None:
    """Submit a review for a word and update SM-2 algorithm state.

    Applies the SM-2 algorithm to calculate new interval, ease factor, and
    repetition count. Updates next_review date based on new interval.

    Args:
        word_id: ID of the word being reviewed.
        quality: SM-2 quality score (0-5, where 3+ is passing).

    Returns:
        Updated vocabulary dict including session_name, or None if word_id not found.
    """
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT v.*, s.name AS session_name
            FROM vocabulary v
            LEFT JOIN sessions s ON v.session_id = s.id
            WHERE v.id = ?
            """,
            (word_id,),
        ).fetchone()
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
        _attach_primitives(conn, [row])

    return {
        **row,
        "interval": new_interval,
        "ease_factor": new_ease,
        "repetitions": new_reps,
        "next_review": next_review,
    }


def update_word(
    word_id: int,
    word: str,
    definition: str,
    example: str | None,
) -> dict | None:
    """Update the content fields of a vocabulary word.

    Only touches word, definition, and example — SM-2 state is left intact.
    Raises sqlite3.IntegrityError if the new word+language combination
    already exists (unique index violation).

    Args:
        word_id: ID of the word to update.
        word: New word text.
        definition: New definition text.
        example: New example sentence, or None to clear.

    Returns:
        Updated vocabulary dict with session_name joined, or None if word_id not found.
    """
    with get_connection() as conn:
        result = conn.execute(
            "UPDATE vocabulary SET word = ?, definition = ?, example = ? WHERE id = ?",
            (word, definition, example, word_id),
        )
        if result.rowcount == 0:
            return None
        row = conn.execute(
            """
            SELECT v.*, s.name AS session_name
            FROM vocabulary v
            LEFT JOIN sessions s ON v.session_id = s.id
            WHERE v.id = ?
            """,
            (word_id,),
        ).fetchone()
    return dict(row)


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


def delete_words_by_session(session_id: int) -> int | None:
    """Delete all vocabulary words for a session and the session record itself.

    Checks session existence first to distinguish a missing session (None)
    from a session that exists but has no words (0). Both deletes run in
    a single transaction.

    Args:
        session_id: ID of the session to delete.

    Returns:
        Count of deleted vocabulary words, or None if session_id not found.
    """
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        result = conn.execute("DELETE FROM vocabulary WHERE session_id = ?", (session_id,))
        deleted_count = result.rowcount
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    return deleted_count
