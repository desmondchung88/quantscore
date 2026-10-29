"""Watchlists -- the many-to-many side of the relational model."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.security import current_user
from app.db import mongo, mysql
from app.schemas import WatchlistCreate, WatchlistTicker

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


def _assert_owns(user_id: int, watchlist_id: int) -> dict:
    row = mysql.query_one(
        "SELECT watchlist_id, user_id, name FROM watchlists"
        " WHERE watchlist_id = :w", {"w": watchlist_id})
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Watchlist not found")
    if int(row["user_id"]) != int(user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your watchlist")
    return row


@router.get("")
def list_watchlists(user: dict = Depends(current_user)):
    return {"watchlists": mysql.query(
        "SELECT w.watchlist_id, w.name, w.created_at,"
        "       COUNT(ws.stock_id) AS stock_count"
        "  FROM watchlists w"
        "  LEFT JOIN watchlist_stocks ws ON ws.watchlist_id = w.watchlist_id"
        " WHERE w.user_id = :u"
        " GROUP BY w.watchlist_id, w.name, w.created_at"
        " ORDER BY w.created_at",
        {"u": user["user_id"]})}


@router.post("", status_code=status.HTTP_201_CREATED)
def create(body: WatchlistCreate, user: dict = Depends(current_user)):
    try:
        wid = mysql.insert_returning_id(
            "INSERT INTO watchlists (user_id, name) VALUES (:u, :n)",
            {"u": user["user_id"], "n": body.name.strip()})
    except (IntegrityError, DBAPIError):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "You already have a watchlist with that name")
    return {"watchlist_id": wid, "name": body.name.strip(), "stock_count": 0}


@router.get("/{watchlist_id}")
def detail(watchlist_id: int, user: dict = Depends(current_user)):
    meta = _assert_owns(user["user_id"], watchlist_id)
    stocks = mysql.query(
        """
        SELECT sc.ticker, sc.company_name, sc.sector_name, sc.last_close,
               sc.pe_ratio, sc.dividend_yield, sc.ret_1y, sc.total_score,
               sc.grade, ws.added_at
          FROM watchlist_stocks ws
          JOIN v_stock_scores_total sc ON sc.stock_id = ws.stock_id
         WHERE ws.watchlist_id = :w
         ORDER BY sc.total_score DESC
        """,
        {"w": watchlist_id},
    )
    return {"watchlist": meta, "stocks": stocks}


@router.post("/{watchlist_id}/stocks", status_code=status.HTTP_201_CREATED)
def add_stock(watchlist_id: int, body: WatchlistTicker,
              user: dict = Depends(current_user)):
    _assert_owns(user["user_id"], watchlist_id)
    stock = mysql.query_one(
        "SELECT stock_id FROM stocks WHERE ticker = :t", {"t": body.ticker})
    if stock is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown ticker")

    mysql.execute(
        "INSERT IGNORE INTO watchlist_stocks (watchlist_id, stock_id)"
        " VALUES (:w, :s)",
        {"w": watchlist_id, "s": stock["stock_id"]})
    mongo.log_activity(user["user_id"], "watchlist.add",
                       {"watchlist_id": watchlist_id, "ticker": body.ticker})
    return {"watchlist_id": watchlist_id, "ticker": body.ticker, "added": True}


@router.delete("/{watchlist_id}/stocks/{ticker}",
               status_code=status.HTTP_204_NO_CONTENT)
def remove_stock(watchlist_id: int, ticker: str,
                 user: dict = Depends(current_user)):
    _assert_owns(user["user_id"], watchlist_id)
    mysql.execute(
        "DELETE ws FROM watchlist_stocks ws"
        "  JOIN stocks s ON s.stock_id = ws.stock_id"
        " WHERE ws.watchlist_id = :w AND s.ticker = :t",
        {"w": watchlist_id, "t": ticker.strip().upper()})


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(watchlist_id: int, user: dict = Depends(current_user)):
    _assert_owns(user["user_id"], watchlist_id)
    mysql.execute("DELETE FROM watchlists WHERE watchlist_id = :w",
                  {"w": watchlist_id})
