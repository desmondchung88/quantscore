"""QuantScore API -- the application tier of the three-tier architecture."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import mongo
from app.routers import (auth, benchmark, meta, news, portfolios, scores,
                         screener, stocks, watchlists)

log = logging.getLogger("quantscore")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        mongo.ensure_collections()
        log.info("MongoDB collections, validators and indexes are in place")
    except Exception as exc:
        log.warning("MongoDB unavailable at start-up (%s). "
                    "News and notes endpoints will fail until it is running.",
                    str(exc).splitlines()[0][:120])
    yield


app = FastAPI(
    title="QuantScore API",
    version="1.0.0",
    description=(
        "S&P 500 research and investment-support platform.\n\n"
        "Polyglot persistence: MySQL holds the transactional and "
        "time-series data, MongoDB holds the news, profiles, notes and "
        "activity logs."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error",
                 "hint": "Check the API log; the database may not be loaded."},
    )


for router in (auth.router, stocks.router, scores.router, screener.router,
               portfolios.router, watchlists.router, news.router,
               news.notes_router, benchmark.router, meta.router):
    app.include_router(router)


@app.get("/", tags=["meta"])
def root():
    return {
        "name": "QuantScore",
        "docs": "/docs",
        "health": "/api/meta/health",
        "features": {
            "stock_search": "/api/stocks/search?q=apple",
            "quantscore": "/api/scores/leaderboard",
            "screener": "POST /api/screener/run",
            "portfolio": "/api/portfolios",
            "sentiment": "/api/news/feed",
            "benchmark": "/api/benchmark/run",
        },
    }
