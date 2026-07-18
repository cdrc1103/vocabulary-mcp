"""Pydantic models for Heisig hanzi integration.

Defines HeisigData — the composable bundle of Heisig fields nested under
VocabularyResponse.heisig in models.general. This module has no dependency
on models.general so that general.py can depend on it without a cycle.
"""

from pydantic import BaseModel, Field


class HeisigData(BaseModel):
    """Heisig data for a hanzi vocabulary card, nested under VocabularyResponse.heisig.

    Attributes:
        keyword: Single Heisig keyword (meaning only) for hanzi words.
        pinyin: Pinyin romanization with tone mark.
        tone: Tone number 1-5 (5 = neutral).
    """

    keyword: str
    pinyin: str
    tone: int


class HanziUpsert(BaseModel):
    """Request model for creating or enriching one Heisig hanzi card.

    Attributes:
        word: The hanzi character.
        keyword: Single Heisig keyword (meaning only).
        pinyin: Pinyin with tone mark.
        tone: Tone number 1-5 (5 = neutral).
        definition: Meaning/usage for a new card; ignored on enrich. NOT for pinyin.
        example: Optional usage sentence for a new card; ignored on enrich.
    """

    word: str
    keyword: str
    pinyin: str
    tone: int = Field(ge=1, le=5)
    definition: str | None = None
    example: str | None = None


class HanziBulkUpsert(BaseModel):
    """Request model for creating/enriching up to 50 Heisig hanzi cards.

    Attributes:
        cards: 1-50 HanziUpsert items.
        session_name: Session for newly created cards only; enrich never reassigns.
    """

    cards: list[HanziUpsert] = Field(min_length=1, max_length=50)
    session_name: str | None = None
