"""FastAPI application for vocabulary study API.

Provides RESTful endpoints for managing vocabulary words with spaced repetition
scheduling (SM-2 algorithm) and session-based grouping. Includes authentication,
CORS support, and health checks.
"""

import sqlite3
from contextlib import asynccontextmanager

from auth import PWA_PASSWORD, APIKeyMiddleware, create_token
from database import (
    delete_word,
    delete_words_by_session,
    get_due_words,
    get_primitives,
    get_sessions,
    get_words,
    init_db,
    insert_word,
    insert_words_bulk,
    review_word,
    update_word,
    upsert_primitive,
)
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from models import (
    BulkVocabularyCreate,
    BulkVocabularyResponse,
    LoginRequest,
    PrimitiveCreate,
    PrimitiveResponse,
    ReviewRequest,
    SessionResponse,
    VocabularyCreate,
    VocabularyListResponse,
    VocabularyResponse,
    VocabularyUpdate,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle hook for startup/shutdown tasks.

    Initializes the SQLite database on app startup.

    Args:
        app: FastAPI application instance.

    Yields:
        Control returns to FastAPI after db initialization.
    """
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
    """Health check endpoint.

    Returns:
        Dictionary with status "ok".
    """
    return {"status": "ok"}


@app.post("/auth/login")
def login(payload: LoginRequest):
    """Authenticate user with password and return JWT token.

    Args:
        payload: LoginRequest with password field.

    Returns:
        Dictionary with 'token' and 'token_type'.

    Raises:
        HTTPException: 401 if password is invalid.
    """
    if payload.password != PWA_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"token": create_token(), "token_type": "bearer"}


@app.get("/sessions", response_model=list[SessionResponse])
def list_sessions():
    """List all learning sessions ordered by date descending.

    Returns:
        List of SessionResponse objects.
    """
    return get_sessions()


@app.post("/vocabulary", response_model=VocabularyResponse, status_code=201)
def add_vocabulary(payload: VocabularyCreate):
    """Create and store a new vocabulary word.

    Args:
        payload: VocabularyCreate with word, definition, example, language, session_name.

    Returns:
        VocabularyResponse with id, timestamps, SM-2 state, and session info.
    """
    word = insert_word(
        word=payload.word,
        definition=payload.definition,
        example=payload.example,
        language=payload.language,
        session_name=payload.session_name,
    )
    return word


@app.post("/vocabulary/bulk", response_model=BulkVocabularyResponse, status_code=201)
def bulk_add_vocabulary(payload: BulkVocabularyCreate):
    """Create and store multiple vocabulary words in a single request.

    Args:
        payload: BulkVocabularyCreate with 1-50 VocabularyCreate words.

    Returns:
        BulkVocabularyResponse with inserted list and skipped_count.
    """
    result = insert_words_bulk([w.model_dump() for w in payload.words])
    return result


@app.get("/vocabulary", response_model=VocabularyListResponse)
def list_vocabulary(
    language: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session_id: int | None = Query(None),
):
    """List vocabulary words with optional language/session filters and pagination.

    Args:
        language: Optional filter by language code.
        limit: Number of results per page (1-1000, default 100).
        offset: Number of results to skip (default 0).
        session_id: Optional filter by session ID.

    Returns:
        VocabularyListResponse with total count and paginated words.
    """
    return get_words(language=language, limit=limit, offset=offset, session_id=session_id)


@app.get("/vocabulary/due", response_model=list[VocabularyResponse])
def due_vocabulary(
    created_after: str | None = Query(None),
    session_id: int | None = Query(None),
):
    """Get words due for review (next_review <= now), optionally filtered.

    Args:
        created_after: Optional ISO date string (YYYY-MM-DD). Filters to words
            created on or after this date.
        session_id: Optional session ID filter. Stacks AND with created_after.

    Returns:
        List of VocabularyResponse objects ready for study.
    """
    return get_due_words(created_after=created_after, session_id=session_id)


@app.patch("/vocabulary/{word_id}/review", response_model=VocabularyResponse)
def submit_review(word_id: int, payload: ReviewRequest):
    """Submit a review for a word and update SM-2 state.

    Args:
        word_id: ID of the word being reviewed.
        payload: ReviewRequest with quality score (0-5).

    Returns:
        Updated VocabularyResponse.

    Raises:
        HTTPException: 404 if word_id not found.
    """
    result = review_word(word_id=word_id, quality=payload.quality)
    if result is None:
        raise HTTPException(status_code=404, detail="Word not found")
    return result


@app.patch("/vocabulary/{word_id}", response_model=VocabularyResponse)
def update_vocabulary_content(word_id: int, payload: VocabularyUpdate):
    """Update the content of a vocabulary word without changing SM-2 state.

    Args:
        word_id: ID of the word to update.
        payload: VocabularyUpdate with word, definition, and optional example.

    Returns:
        Updated VocabularyResponse.

    Raises:
        HTTPException: 404 if word_id not found.
        HTTPException: 409 if the new word+language combination already exists.
    """
    try:
        result = update_word(
            word_id=word_id,
            word=payload.word,
            definition=payload.definition,
            example=payload.example,
        )
    except sqlite3.IntegrityError as err:
        raise HTTPException(
            status_code=409,
            detail="A word with this name already exists in the same language",
        ) from err
    if result is None:
        raise HTTPException(status_code=404, detail="Word not found")
    return result


@app.delete("/vocabulary/{word_id}", status_code=204)
def remove_vocabulary(word_id: int):
    """Delete a vocabulary word by ID.

    Args:
        word_id: ID of the word to delete.

    Raises:
        HTTPException: 404 if word_id not found.
    """
    deleted = delete_word(word_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Word not found")


@app.delete("/vocabulary/session/{session_id}")
def delete_vocabulary_session(session_id: int):
    """Delete all words in a session and the session record itself.

    Args:
        session_id: ID of the session to delete.

    Returns:
        Dictionary with deleted_words count.

    Raises:
        HTTPException: 404 if session_id not found.
    """
    deleted = delete_words_by_session(session_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted_words": deleted}


@app.get("/primitives", response_model=list[PrimitiveResponse])
def list_primitives():
    """List the primitive registry ordered by introduction rank.

    Returns:
        List of PrimitiveResponse objects.
    """
    return get_primitives()


@app.post("/primitives", response_model=PrimitiveResponse, status_code=201)
def create_primitive(payload: PrimitiveCreate):
    """Register a primitive (first-write-wins; existing keyword is preserved).

    Args:
        payload: PrimitiveCreate with component, keyword, optional note.

    Returns:
        The stored PrimitiveResponse.
    """
    return upsert_primitive(payload.component, payload.keyword, payload.note)
