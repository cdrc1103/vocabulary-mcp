from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from auth import APIKeyMiddleware
from database import delete_word, get_due_words, get_words, init_db, insert_word, review_word
from models import ReviewRequest, VocabularyCreate, VocabularyListResponse, VocabularyResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Vocabulary API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(APIKeyMiddleware)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/vocabulary", response_model=VocabularyResponse, status_code=201)
def add_vocabulary(payload: VocabularyCreate):
    word = insert_word(
        word=payload.word,
        definition=payload.definition,
        example=payload.example,
        language=payload.language,
    )
    return word


@app.get("/vocabulary", response_model=VocabularyListResponse)
def list_vocabulary(
    language: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return get_words(language=language, limit=limit, offset=offset)


@app.get("/vocabulary/due", response_model=list[VocabularyResponse])
def due_vocabulary():
    return get_due_words()


@app.patch("/vocabulary/{word_id}/review", response_model=VocabularyResponse)
def submit_review(word_id: int, payload: ReviewRequest):
    if not (0 <= payload.quality <= 5):
        raise HTTPException(status_code=422, detail="quality must be between 0 and 5")
    result = review_word(word_id=word_id, quality=payload.quality)
    if result is None:
        raise HTTPException(status_code=404, detail="Word not found")
    return result


@app.delete("/vocabulary/{word_id}", status_code=204)
def remove_vocabulary(word_id: int):
    deleted = delete_word(word_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Word not found")
