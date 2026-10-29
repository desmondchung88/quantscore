"""Market sentiment feed and research notes -- the MongoDB surface."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import current_user, optional_user
from app.db import mongo
from app.schemas import NoteCreate, NoteUpdate
from app.services import news as service
from app.services import notes as notes_service
from app.services import sentiment

router = APIRouter(prefix="/api/news", tags=["news"])
notes_router = APIRouter(prefix="/api/notes", tags=["notes"])


# ---------------------------------------------------------------------
# Sentiment feed
# ---------------------------------------------------------------------
@router.get("/feed")
def feed(
    ticker: str | None = None,
    label: str | None = Query(None, pattern="^(positive|neutral|negative)$"),
    search: str | None = None,
    days: int | None = Query(None, ge=1, le=3650),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    user: dict | None = Depends(optional_user),
):
    result = service.feed(ticker, label, search, limit, skip, days)
    mongo.log_activity(user["user_id"] if user else None, "news.feed",
                       {"ticker": ticker, "label": label, "search": search})
    return result


@router.get("/timeline")
def timeline(ticker: str | None = None,
             days: int = Query(180, ge=7, le=3650),
             granularity: str = Query("week", pattern="^(day|week|month)$")):
    return {"timeline": service.sentiment_timeline(ticker, days, granularity)}


@router.get("/leaderboard")
def leaderboard(days: int = Query(90, ge=7, le=3650),
                min_articles: int = Query(20, ge=1, le=1000),
                limit: int = Query(15, ge=1, le=50)):
    return service.ticker_leaderboard(days, min_articles, limit)


@router.get("/publishers")
def publishers(days: int = Query(90, ge=7, le=3650),
               limit: int = Query(12, ge=1, le=50)):
    return {"publishers": service.publisher_breakdown(days, limit)}


@router.get("/distribution")
def distribution(ticker: str | None = None):
    return {"buckets": service.sentiment_distribution(ticker)}


@router.get("/summary/{ticker}")
def summary(ticker: str, days: int = Query(90, ge=7, le=3650)):
    return service.ticker_summary(ticker, days)


@router.post("/score")
def score_headline(payload: dict):
    """Expose the lexicon so the scoring can be demonstrated live."""
    text = str(payload.get("text", "")).strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide some text")
    value, label, terms = sentiment.score_text(text)
    return {"text": text, "score": value, "label": label,
            "matched_terms": terms}


@router.get("/profiles/{ticker}")
def profile(ticker: str):
    doc = service.profile(ticker)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile for that ticker")
    return doc


@router.get("/profiles/tag/{tag}")
def profiles_by_tag(tag: str, limit: int = Query(50, ge=1, le=200)):
    return {"tag": tag, "profiles": service.profiles_by_tag(tag, limit)}


# ---------------------------------------------------------------------
# Research notes -- CRUD on a schemaless collection
# ---------------------------------------------------------------------
@notes_router.get("")
def list_notes(ticker: str | None = None, tag: str | None = None,
               search: str | None = None, limit: int = Query(50, ge=1, le=200),
               user: dict = Depends(current_user)):
    return {"notes": notes_service.list_notes(
        user["user_id"], ticker, tag, search, limit)}


@notes_router.post("", status_code=status.HTTP_201_CREATED)
def create_note(body: NoteCreate, user: dict = Depends(current_user)):
    return notes_service.create_note(user["user_id"],
                                     body.model_dump(exclude_none=True))


@notes_router.get("/tags")
def tags(user: dict = Depends(current_user)):
    return {"tags": notes_service.tag_cloud(user["user_id"])}


@notes_router.get("/activity")
def activity(limit: int = Query(40, ge=1, le=200),
             user: dict = Depends(current_user)):
    return {"activity": notes_service.recent_activity(user["user_id"], limit)}


@notes_router.get("/{note_id}")
def get_note(note_id: str, user: dict = Depends(current_user)):
    return notes_service.get_note(user["user_id"], note_id)


@notes_router.put("/{note_id}")
def update_note(note_id: str, body: NoteUpdate,
                user: dict = Depends(current_user)):
    return notes_service.update_note(user["user_id"], note_id,
                                     body.model_dump(exclude_none=True))


@notes_router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: str, user: dict = Depends(current_user)):
    notes_service.delete_note(user["user_id"], note_id)
