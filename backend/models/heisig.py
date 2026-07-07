"""Pydantic models for Heisig hanzi integration.

Defines the primitive registry models, the HanziUpsert request models, and
HeisigData — the composable bundle of Heisig fields nested under
VocabularyResponse.heisig in models.general. This module has no dependency
on models.general so that general.py can depend on it without a cycle.
"""

from pydantic import BaseModel, Field


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


class HeisigData(BaseModel):
    """Heisig mnemonic data for a hanzi vocabulary card, nested under VocabularyResponse.heisig.

    Attributes:
        keyword: Single Heisig keyword (meaning only) for hanzi words.
        pinyin: Pinyin romanization with tone mark.
        tone: Tone number 1-5 (5 = neutral).
        story: Mnemonic story with tone cue.
        story_edited: 0/1 flag; 1 when the story was hand-edited (preserves it from add_hanzi overwrite).
        primitives: Ordered primitive decomposition.
    """

    keyword: str
    pinyin: str
    tone: int
    story: str
    story_edited: int = 0
    primitives: list[PrimitiveResponse] = Field(default_factory=list)


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
