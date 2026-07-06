"""Pydantic models for general-purpose vocabulary API requests and responses.

Defines data validation and serialization for the core vocabulary feature:
words, sessions, authentication, and SM-2 scheduling. Heisig-specific models
live in models_heisig.py.
"""

from pydantic import BaseModel, Field


class SessionResponse(BaseModel):
    """Response model for a learning session.

    Attributes:
        id: Unique session identifier.
        name: Session name (unique across all sessions).
        date: ISO date string YYYY-MM-DD for the study day.
        created_at: ISO 8601 timestamp of creation.
    """

    id: int
    name: str
    date: str
    created_at: str


class VocabularyCreate(BaseModel):
    """Request model for adding a single vocabulary word.

    Attributes:
        word: The vocabulary word (required).
        definition: Definition of the word (required).
        example: Optional example sentence or usage.
        language: Language code (defaults to "unknown").
        session_name: Session to assign the word to. Auto-created if new. Defaults to "misc".
    """

    word: str
    definition: str
    example: str | None = None
    language: str = "unknown"
    session_name: str | None = None


class VocabularyResponse(BaseModel):
    """Response model for a vocabulary word.

    Includes SRS (Spaced Repetition System) metadata calculated by the SM-2 algorithm
    and session assignment. Heisig fields (keyword, pinyin, tone, story, primitives)
    are available on the HeisigVocabularyResponse subclass in models_heisig.py.

    Attributes:
        id: Unique word identifier.
        word: The vocabulary word.
        definition: Definition of the word.
        example: Optional example sentence.
        language: Language code.
        created_at: ISO 8601 timestamp of creation.
        next_review: ISO 8601 timestamp for next review.
        interval: Days until next review (SM-2).
        ease_factor: Difficulty multiplier (SM-2).
        repetitions: Number of successful reviews (SM-2).
        session_id: ID of the session this word belongs to.
        session_name: Name of the session this word belongs to.
    """

    id: int
    word: str
    definition: str
    example: str | None = None
    language: str
    created_at: str
    next_review: str
    interval: int
    ease_factor: float
    repetitions: int
    session_id: int | None = None
    session_name: str | None = None


class ReviewRequest(BaseModel):
    """Request model for submitting a word review.

    Attributes:
        quality: SM-2 quality score (0-5, where 0=complete failure, 5=perfect recall).
    """

    quality: int = Field(..., ge=0, le=5)  # SM-2 standard


class VocabularyUpdate(BaseModel):
    """Request model for updating vocabulary word content.

    All fields must be provided; example may be None to clear it.
    SM-2 scheduling fields are not affected by this model.

    Attributes:
        word: New word text (required).
        definition: New definition text (required).
        example: New example sentence, or None to clear the existing one.
    """

    word: str
    definition: str
    example: str | None = None


class LoginRequest(BaseModel):
    """Request model for password authentication.

    Attributes:
        password: Password for API access.
    """

    password: str


class BulkVocabularyCreate(BaseModel):
    """Request model for bulk adding vocabulary words.

    Attributes:
        words: List of 1-50 VocabularyCreate objects. Each word may specify session_name.
    """

    words: list[VocabularyCreate] = Field(min_length=1, max_length=50)


class BulkVocabularyResponse(BaseModel):
    """Response model for bulk vocabulary creation.

    Attributes:
        inserted: List of successfully created VocabularyResponse objects.
        skipped_count: Count of words that were skipped (e.g., duplicates).
    """

    inserted: list[VocabularyResponse]
    skipped_count: int
