"""The QuantScore endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas import WeightsRequest
from app.services import scoring as service

router = APIRouter(prefix="/api/scores", tags=["scores"])


@router.get("/leaderboard")
def leaderboard(
    sector: str | None = None,
    min_market_cap: float = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    valuation: float = Query(0.30, ge=0, le=1),
    profitability: float = Query(0.25, ge=0, le=1),
    growth: float = Query(0.25, ge=0, le=1),
    dividend: float = Query(0.20, ge=0, le=1),
):
    weights = service.Weights.normalised(
        valuation=valuation, profitability=profitability,
        growth=growth, dividend=dividend)
    return service.leaderboard(weights, sector, min_market_cap, limit, offset)


@router.post("/leaderboard")
def leaderboard_weighted(
    body: WeightsRequest,
    sector: str | None = None,
    min_market_cap: float = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    weights = service.Weights.normalised(**body.model_dump())
    return service.leaderboard(weights, sector, min_market_cap, limit)


@router.get("/sectors")
def sector_leaderboard(min_market_cap: float = Query(0, ge=0)):
    return {"sectors": service.sector_leaderboard(min_market_cap)}


@router.get("/distribution")
def distribution():
    return {"buckets": service.distribution()}


@router.get("/{ticker}")
def explain(
    ticker: str,
    valuation: float = Query(0.30, ge=0, le=1),
    profitability: float = Query(0.25, ge=0, le=1),
    growth: float = Query(0.25, ge=0, le=1),
    dividend: float = Query(0.20, ge=0, le=1),
):
    weights = service.Weights.normalised(
        valuation=valuation, profitability=profitability,
        growth=growth, dividend=dividend)
    data = service.explain(ticker, weights)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown ticker")
    return data
