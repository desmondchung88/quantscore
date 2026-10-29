"""Virtual portfolio management, trading and risk analytics."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.core.security import assert_owns_portfolio, current_user
from app.db import mongo
from app.schemas import PortfolioCreate, PortfolioRename, TradeRequest
from app.services import portfolio as service

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])


@router.get("")
def list_portfolios(user: dict = Depends(current_user)):
    return {"portfolios": service.list_portfolios(user["user_id"])}


@router.post("", status_code=status.HTTP_201_CREATED)
def create(body: PortfolioCreate, user: dict = Depends(current_user)):
    created = service.create_portfolio(
        user["user_id"], body.name, body.initial_cash, body.currency_code)
    mongo.log_activity(user["user_id"], "portfolio.create", {"name": body.name})
    return created


@router.get("/{portfolio_id}")
def detail(portfolio_id: int, user: dict = Depends(current_user)):
    assert_owns_portfolio(user["user_id"], portfolio_id)
    summaries = service.list_portfolios(user["user_id"])
    return {
        "summary": next((p for p in summaries
                         if p["portfolio_id"] == portfolio_id), None),
        "holdings": service.holdings(portfolio_id),
        "transactions": service.transactions(portfolio_id, 25),
    }


@router.patch("/{portfolio_id}")
def rename(portfolio_id: int, body: PortfolioRename,
           user: dict = Depends(current_user)):
    assert_owns_portfolio(user["user_id"], portfolio_id)
    return service.rename_portfolio(portfolio_id, body.name)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(portfolio_id: int, user: dict = Depends(current_user)):
    assert_owns_portfolio(user["user_id"], portfolio_id)
    service.delete_portfolio(portfolio_id)
    mongo.log_activity(user["user_id"], "portfolio.delete",
                       {"portfolio_id": portfolio_id})


@router.get("/{portfolio_id}/holdings")
def holdings(portfolio_id: int, user: dict = Depends(current_user)):
    assert_owns_portfolio(user["user_id"], portfolio_id)
    return {"holdings": service.holdings(portfolio_id)}


@router.get("/{portfolio_id}/transactions")
def transactions(portfolio_id: int, limit: int = Query(100, ge=1, le=500),
                 user: dict = Depends(current_user)):
    assert_owns_portfolio(user["user_id"], portfolio_id)
    return {"transactions": service.transactions(portfolio_id, limit)}


@router.post("/{portfolio_id}/trade")
def trade(portfolio_id: int, body: TradeRequest,
          user: dict = Depends(current_user)):
    assert_owns_portfolio(user["user_id"], portfolio_id)
    result = service.execute_trade(portfolio_id, body.ticker, body.side,
                                   body.quantity)
    mongo.log_activity(user["user_id"], "portfolio.trade", {
        "portfolio_id": portfolio_id, "ticker": body.ticker,
        "side": body.side, "quantity": body.quantity,
        "price": result["trade"]["price"],
    })
    return result


@router.get("/{portfolio_id}/risk")
def risk(portfolio_id: int, days: int = Query(365, ge=30, le=2000),
         user: dict = Depends(current_user)):
    assert_owns_portfolio(user["user_id"], portfolio_id)
    return service.risk_analytics(portfolio_id, days)


@router.get("/{portfolio_id}/history")
def history(portfolio_id: int, days: int = Query(365, ge=30, le=2000),
            user: dict = Depends(current_user)):
    assert_owns_portfolio(user["user_id"], portfolio_id)
    return {"series": service.value_series(portfolio_id, days)}
