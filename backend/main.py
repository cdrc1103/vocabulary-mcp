from contextlib import asynccontextmanager

from auth import PWA_PASSWORD, APIKeyMiddleware, create_token
from database import delete_word, get_due_words, get_words, init_db, insert_word, review_word
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from models import (
    LoginRequest,
    ReviewRequest,
    VocabularyCreate,
    VocabularyListResponse,
    VocabularyResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Vocabulary API", lifespan=lifespan)

# APIKeyMiddleware must be added first so CORSMiddleware is outermost.
# Starlette executes middleware LIFO, so the last add_middleware call runs first.
# CORS must be outermost to handle OPTIONS preflight before auth is checked.
app.add_middleware(APIKeyMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/login")
def login(payload: LoginRequest):
    if payload.password != PWA_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"token": create_token(), "token_type": "bearer"}


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
    language: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return get_words(language=language, limit=limit, offset=offset)


@app.get("/vocabulary/due", response_model=list[VocabularyResponse])
def due_vocabulary():
    return get_due_words()


@app.patch("/vocabulary/{word_id}/review", response_model=VocabularyResponse)
def submit_review(word_id: int, payload: ReviewRequest):
    result = review_word(word_id=word_id, quality=payload.quality)
    if result is None:
        raise HTTPException(status_code=404, detail="Word not found")
    return result


@app.delete("/vocabulary/{word_id}", status_code=204)
def remove_vocabulary(word_id: int):
    deleted = delete_word(word_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Word not found")
