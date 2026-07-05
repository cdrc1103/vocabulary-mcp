"""Pydantic models for vocabulary API requests and responses.

This module defines data validation and serialization models using Pydantic v2,
including request payloads (VocabularyCreate, LoginRequest) and response models
(VocabularyResponse, VocabularyListResponse, SessionResponse).
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
    and session assignment.

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
        keyword: Heisig keyword (meaning only) for hanzi words.
        pinyin: Pinyin romanization with tone mark for hanzi words.
        tone: Tone number 1-5 (5 = neutral) for hanzi words.
        story: Mnemonic story with tone cue for hanzi words.
        story_edited: Timestamp of the last story edit (Unix timestamp); 0 if never edited.
        primitives: Ordered primitive decomposition for hanzi words.
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
    keyword: str | None = None
    pinyin: str | None = None
    tone: int | None = None
    story: str | None = None
    story_edited: int = 0
    primitives: list["PrimitiveResponse"] = Field(default_factory=list)


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


class PrimitiveRef(BaseModel):
    """A primitive reference within a hanzi decomposition.

    Attributes:
        component: The primitive's shape/character.
        keyword: The keyword to register for this component (first-write-wins server-side).
        note: Optional gloss.
        position: Zero-based order of this primitive within the character.
    """

    component: str
    keyword: str
    note: str | None = None
    position: int = Field(ge=0)


class PrimitiveCreate(BaseModel):
    """Request model for registering a single primitive.

    Attributes:
        component: The primitive's shape/character (unique key).
        keyword: The keyword to register.
        note: Optional gloss.
    """

    component: str
    keyword: str
    note: str | None = None


class PrimitiveResponse(BaseModel):
    """Response model for a primitive.

    Attributes:
        id: Primitive id.
        component: The shape/character.
        keyword: The registered keyword.
        note: Optional gloss.
        rank: Introduction order.
        position: Order within a card, when returned in a card context.
    """

    id: int
    component: str
    keyword: str
    note: str | None = None
    rank: int | None = None
    position: int | None = None


class HanziUpsert(BaseModel):
    """Request model for creating or enriching one Heisig hanzi card.

    Attributes:
        word: The hanzi character.
        keyword: Single Heisig keyword (meaning only).
        pinyin: Pinyin with tone mark.
        tone: Tone number 1-5 (5 = neutral).
        story: Mnemonic story with the tone cue baked in.
        definition: Meaning/usage for a new card; ignored on enrich. NOT for pinyin.
        example: Optional usage sentence for a new card; ignored on enrich.
        primitives: Ordered primitive decomposition.
    """

    word: str
    keyword: str
    pinyin: str
    tone: int = Field(ge=1, le=5)
    story: str
    definition: str | None = None
    example: str | None = None
    primitives: list[PrimitiveRef] = Field(default_factory=list)


class HanziBulkUpsert(BaseModel):
    """Request model for creating/enriching up to 50 Heisig hanzi cards.

    Attributes:
        cards: 1-50 HanziUpsert items.
        session_name: Session for newly created cards only; enrich never reassigns.
    """

    cards: list[HanziUpsert] = Field(min_length=1, max_length=50)
    session_name: str | None = None


class HanziUpsertResponse(BaseModel):
    """Response model for a hanzi bulk upsert.

    Attributes:
        created: Count of newly created cards.
        enriched: Count of existing cards enriched.
        unchanged: Count of cards whose Heisig data already matched.
        cards: The resulting cards.
    """

    created: int
    enriched: int
    unchanged: int
    cards: list[VocabularyResponse]
