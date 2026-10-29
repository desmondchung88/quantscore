"""Research notes -- full CRUD against MongoDB.

Deliberately schema-light: a note may carry a price target, arbitrary
tags, or nothing beyond a body. Adding a field to one note costs nothing
and migrates nothing, which is the argument for the document model.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.db import mongo

EDITABLE = {"title", "body", "ticker", "tags", "rating", "price_target",
            "conviction", "horizon", "attachments"}


def _oid(note_id: str) -> ObjectId:
    try:
        return ObjectId(note_id)
    except (InvalidId, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed note id")


def _clean(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    for key in ("created_at", "updated_at"):
        if isinstance(doc.get(key), datetime):
            doc[key] = doc[key].isoformat()
    return doc


def list_notes(user_id: int, ticker: str | None = None,
               tag: str | None = None, search: str | None = None,
               limit: int = 50) -> list[dict]:
    query: dict[str, Any] = {"user_id": user_id}
    if ticker:
        query["ticker"] = ticker.strip().upper()
    if tag:
        query["tags"] = tag
    if search:
        query["$text"] = {"$search": search}

    cursor = mongo.get_db()[mongo.NOTES].find(query) \
        .sort([("updated_at", -1)]).limit(limit)
    return [_clean(d) for d in cursor]


def get_note(user_id: int, note_id: str) -> dict:
    doc = mongo.get_db()[mongo.NOTES].find_one(
        {"_id": _oid(note_id), "user_id": user_id})
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    return _clean(doc)


def create_note(user_id: int, payload: dict) -> dict:
    body = {k: v for k, v in payload.items() if k in EDITABLE and v is not None}
    if not body.get("body"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A note needs a body")

    now = datetime.utcnow()
    body.update({"user_id": user_id, "created_at": now, "updated_at": now})
    if body.get("ticker"):
        body["ticker"] = str(body["ticker"]).strip().upper()

    result = mongo.get_db()[mongo.NOTES].insert_one(body)
    mongo.log_activity(user_id, "note.create",
                       {"note_id": str(result.inserted_id),
                        "ticker": body.get("ticker")})
    return get_note(user_id, str(result.inserted_id))


def update_note(user_id: int, note_id: str, payload: dict) -> dict:
    changes = {k: v for k, v in payload.items() if k in EDITABLE}
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to update")
    if changes.get("ticker"):
        changes["ticker"] = str(changes["ticker"]).strip().upper()
    changes["updated_at"] = datetime.utcnow()

    result = mongo.get_db()[mongo.NOTES].update_one(
        {"_id": _oid(note_id), "user_id": user_id}, {"$set": changes})
    if result.matched_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")

    mongo.log_activity(user_id, "note.update", {"note_id": note_id})
    return get_note(user_id, note_id)


def delete_note(user_id: int, note_id: str) -> None:
    result = mongo.get_db()[mongo.NOTES].delete_one(
        {"_id": _oid(note_id), "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    mongo.log_activity(user_id, "note.delete", {"note_id": note_id})


def tag_cloud(user_id: int) -> list[dict]:
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 40},
        {"$project": {"_id": 0, "tag": "$_id", "count": 1}},
    ]
    return list(mongo.get_db()[mongo.NOTES].aggregate(pipeline))


def recent_activity(user_id: int, limit: int = 40) -> list[dict]:
    """The TTL-expiring activity log."""
    cursor = mongo.get_db()[mongo.ACTIVITY].find({"user_id": user_id}) \
        .sort([("created_at", -1)]).limit(limit)
    out = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        if isinstance(doc.get("created_at"), datetime):
            doc["created_at"] = doc["created_at"].isoformat()
        out.append(doc)
    return out
