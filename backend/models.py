from pydantic import BaseModel, Field


class VocabularyCreate(BaseModel):
    word: str
    definition: str
    example: str | None = None
    language: str = "unknown"


class VocabularyResponse(BaseModel):
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
    total: int
    words: list[VocabularyResponse]


class ReviewRequest(BaseModel):
    quality: int = Field(..., ge=0, le=5)  # SM-2 standard


class LoginRequest(BaseModel):
    password: str
