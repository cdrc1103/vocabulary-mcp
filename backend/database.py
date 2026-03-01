import sqlite3
import os
from datetime import date, timedelta
from typing import Optional


DATABASE_PATH = os.getenv("DATABASE_PATH", "./vocab.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
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
        conn.commit()


def apply_sm2(interval: int, ease: float, reps: int, quality: int):
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


def insert_word(word: str, definition: str, example: Optional[str], language: str) -> dict:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO vocabulary (word, definition, example, language)
            VALUES (?, ?, ?, ?)
            """,
            (word, definition, example, language),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM vocabulary WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def get_words(language: Optional[str], limit: int, offset: int) -> dict:
    with get_connection() as conn:
        if language:
            total = conn.execute(
                "SELECT COUNT(*) FROM vocabulary WHERE language = ?", (language,)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM vocabulary WHERE language = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (language, limit, offset),
            ).fetchall()
        else:
            total = conn.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM vocabulary ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return {"total": total, "words": [dict(r) for r in rows]}


def get_due_words() -> list[dict]:
    today = date.today().isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM vocabulary WHERE next_review <= ? ORDER BY next_review ASC",
            (today,),
        ).fetchall()
        return [dict(r) for r in rows]


def review_word(word_id: int, quality: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM vocabulary WHERE id = ?", (word_id,)
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
        conn.commit()

        updated = conn.execute(
            "SELECT * FROM vocabulary WHERE id = ?", (word_id,)
        ).fetchone()
        return dict(updated)


def delete_word(word_id: int) -> bool:
    with get_connection() as conn:
        result = conn.execute(
            "DELETE FROM vocabulary WHERE id = ?", (word_id,)
        )
        conn.commit()
        return result.rowcount > 0
