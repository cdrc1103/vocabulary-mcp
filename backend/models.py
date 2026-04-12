"""Pydantic models for vocabulary API requests and responses.

This module defines data validation and serialization models using Pydantic v2,
including request payloads (VocabularyCreate, LoginRequest) and response models
(VocabularyResponse, VocabularyListResponse).
"""

from pydantic import BaseModel, Field


class VocabularyCreate(BaseModel):
    """Request model for adding a single vocabulary word.

    Attributes:
        word: The vocabulary word (required).
        definition: Definition of the word (required).
        example: Optional example sentence or usage.
        language: Language code (defaults to "unknown").
    """

    word: str
    definition: str
    example: str | None = None
    language: str = "unknown"


class VocabularyResponse(BaseModel):
    """Response model for a vocabulary word.

    Includes SRS (Spaced Repetition System) metadata calculated by the SM-2 algorithm.

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


class VocabularyListResponse(BaseModel):
    """Response model for paginated vocabulary list.

    Attributes:
        total: Total count of words matching the query.
        words: List of VocabularyResponse objects for this page.
    """

    total: int
    words: list[VocabularyResponse]


class ReviewRequest(BaseModel):
    """Request model for submitting a word review.

    Attributes:
        quality: SM-2 quality score (0-5, where 0=complete failure, 5=perfect recall).
    """

    quality: int = Field(..., ge=0, le=5)  # SM-2 standard


class LoginRequest(BaseModel):
    """Request model for password authentication.

    Attributes:
        password: Password for API access.
    """

    password: str


class BulkVocabularyCreate(BaseModel):
    """Request model for bulk adding vocabulary words.

    Attributes:
        words: List of 1-50 VocabularyCreate objects.
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
