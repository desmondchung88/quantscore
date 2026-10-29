"""Stock search, detail, price history and sector context."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import optional_user
from app.db import mongo
from app.services import news as news_service
from app.services import stocks as service

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=64),
           limit: int = Query(20, ge=1, le=100),
           user: dict | None = Depends(optional_user)):
    results = service.search(q, limit)
    mongo.log_activity(user["user_id"] if user else None,
                       "stock.search", {"q": q, "hits": len(results)})
    return {"query": q, "count": len(results), "results": results}


@router.get("/sectors")
def sectors():
    return {"sectors": service.sector_overview()}


@router.get("/movers")
def movers(limit: int = Query(10, ge=1, le=50)):
    return service.market_movers(limit)


@router.get("/{ticker}")
def detail(ticker: str, user: dict | None = Depends(optional_user)):
    data = service.detail(ticker)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"No stock with ticker {ticker.upper()}")
    # The document store supplies the sentiment card and the profile.
    data["sentiment"] = news_service.ticker_summary(ticker)
    data["profile"] = news_service.profile(ticker)
    mongo.log_activity(user["user_id"] if user else None,
                       "stock.view", {"ticker": ticker.upper()})
    return data


@router.get("/{ticker}/history")
def history(ticker: str, days: int = Query(365, ge=5, le=2000)):
    rows = service.price_history(ticker, days)
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "No price history for that ticker")
    return {"ticker": ticker.upper(), "points": len(rows), "history": rows}
