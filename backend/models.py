from pydantic import BaseModel
from typing import Optional


class VocabularyCreate(BaseModel):
    word: str
    definition: str
    example: Optional[str] = None
    language: str = "unknown"


class VocabularyResponse(BaseModel):
    id: int
    word: str
    definition: str
    example: Optional[str] = None
    language: str
    created_at: str
    next_review: str
    interval: int
    ease_factor: float
    repetitions: int


class VocabularyListResponse(BaseModel):
    total: int
    words: list[VocabularyResponse]


class ReviewRequest(BaseModel):
    quality: int  # 0-5 (SM-2 standard)
