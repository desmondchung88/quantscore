"""Stock comparison screener."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import optional_user
from app.db import mongo
from app.schemas import CompareRequest, ScreenerRequest
from app.services import screener as service

router = APIRouter(prefix="/api/screener", tags=["screener"])


@router.get("/options")
def options():
    return service.filter_options()


@router.post("/run")
def run(body: ScreenerRequest, user: dict | None = Depends(optional_user)):
    filters = body.model_dump(exclude_none=True)
    for key in ("sort_by", "sort_dir", "limit", "offset"):
        filters.pop(key, None)

    result = service.run(filters, body.sort_by, body.sort_dir,
                         body.limit, body.offset)
    mongo.log_activity(user["user_id"] if user else None, "screener.run",
                       {"filters": filters,
                        "matches": (result["stats"] or {}).get("matches")})
    return result


@router.post("/compare")
def compare(body: CompareRequest, user: dict | None = Depends(optional_user)):
    result = service.compare(body.tickers)
    mongo.log_activity(user["user_id"] if user else None, "screener.compare",
                       {"tickers": body.tickers})
    return result
