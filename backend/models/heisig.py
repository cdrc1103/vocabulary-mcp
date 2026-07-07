"""Pydantic models for Heisig hanzi integration.

Extends the base vocabulary models with Heisig-specific fields: keywords, pinyin,
tone, mnemonic stories, and the primitive registry. All general vocabulary models
live in models.general.
"""

from pydantic import BaseModel, Field

from models.general import VocabularyResponse


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


class HeisigVocabularyResponse(VocabularyResponse):
    """VocabularyResponse extended with Heisig mnemonic fields.

    A card is considered a Heisig card when keyword is not None. Non-Heisig
    cards carry None for all Heisig fields and an empty primitives list.

    Attributes:
        keyword: Single Heisig keyword (meaning only) for hanzi words.
        pinyin: Pinyin romanization with tone mark for hanzi words.
        tone: Tone number 1-5 (5 = neutral) for hanzi words.
        story: Mnemonic story with tone cue for hanzi words.
        story_edited: 0/1 flag; 1 when the story was hand-edited (preserves it from add_hanzi overwrite).
        primitives: Ordered primitive decomposition for hanzi words.
    """

    keyword: str | None = None
    pinyin: str | None = None
    tone: int | None = None
    story: str | None = None
    story_edited: int = 0
    primitives: list[PrimitiveResponse] = Field(default_factory=list)


class HeisigVocabularyListResponse(BaseModel):
    """Paginated vocabulary list response that includes Heisig fields.

    Attributes:
        total: Total count of words matching the query.
        words: List of HeisigVocabularyResponse objects for this page.
    """

    total: int
    words: list[HeisigVocabularyResponse]


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
        cards: The resulting cards with Heisig fields populated.
    """

    created: int
    enriched: int
    unchanged: int
    cards: list[HeisigVocabularyResponse]
