"""NoSQL-powered market sentiment feed.

Everything here runs against MongoDB: the feed itself, the sentiment
time-series, the leaderboards and the full-text search. The aggregation
framework does the grouping and bucketing server-side so the API returns
chart-ready data rather than raw documents.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.db import mongo


def _clean(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    if isinstance(doc.get("published_at"), datetime):
        doc["published_at"] = doc["published_at"].isoformat()
    return doc


# ---------------------------------------------------------------------
# Feed
# ---------------------------------------------------------------------
def feed(ticker: str | None = None, label: str | None = None,
         search: str | None = None, limit: int = 50, skip: int = 0,
         days: int | None = None) -> dict:
    coll = mongo.get_db()[mongo.NEWS]
    query: dict[str, Any] = {}

    if ticker:
        query["ticker"] = ticker.strip().upper()
    if label in ("positive", "neutral", "negative"):
        query["sentiment.label"] = label
    if days:
        latest = _latest_timestamp()
        if latest:
            query["published_at"] = {"$gte": latest - timedelta(days=days)}
    if search:
        query["$text"] = {"$search": search}

    projection = {"headline": 1, "ticker": 1, "publisher": 1, "url": 1,
                  "published_at": 1, "sentiment": 1, "source": 1}
    sort = [("published_at", -1)]
    if search:
        projection["score"] = {"$meta": "textScore"}
        sort = [("score", {"$meta": "textScore"}), ("published_at", -1)]

    cursor = coll.find(query, projection).sort(sort).skip(skip).limit(limit)
    docs = [_clean(d) for d in cursor]

    # count_documents on a multi-million document collection is expensive;
    # cap the scan so the feed stays responsive.
    total = coll.count_documents(query, limit=10_000)
    return {"articles": docs, "total": total, "capped": total >= 10_000}


def _latest_timestamp() -> datetime | None:
    coll = mongo.get_db()[mongo.NEWS]
    doc = coll.find_one({}, {"published_at": 1}, sort=[("published_at", -1)])
    return doc["published_at"] if doc else None


# ---------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------
def sentiment_timeline(ticker: str | None = None, days: int = 180,
                       granularity: str = "week") -> list[dict]:
    """Average sentiment and article volume over time.

    $dateTrunc does the bucketing inside MongoDB, so the payload is one
    document per bucket instead of one per article.
    """
    coll = mongo.get_db()[mongo.NEWS]
    latest = _latest_timestamp()
    if latest is None:
        return []

    match: dict[str, Any] = {"published_at": {"$gte": latest - timedelta(days=days)}}
    if ticker:
        match["ticker"] = ticker.strip().upper()

    unit = granularity if granularity in ("day", "week", "month") else "week"
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"$dateTrunc": {"date": "$published_at", "unit": unit}},
            "articles": {"$sum": 1},
            "avg_sentiment": {"$avg": "$sentiment.score"},
            "positive": {"$sum": {"$cond": [
                {"$eq": ["$sentiment.label", "positive"]}, 1, 0]}},
            "negative": {"$sum": {"$cond": [
                {"$eq": ["$sentiment.label", "negative"]}, 1, 0]}},
            "neutral": {"$sum": {"$cond": [
                {"$eq": ["$sentiment.label", "neutral"]}, 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
        {"$project": {
            "_id": 0,
            "period": {"$dateToString": {"format": "%Y-%m-%d", "date": "$_id"}},
            "articles": 1,
            "avg_sentiment": {"$round": ["$avg_sentiment", 4]},
            "positive": 1, "negative": 1, "neutral": 1,
            "net_sentiment_pct": {"$round": [
                {"$multiply": [
                    {"$divide": [{"$subtract": ["$positive", "$negative"]},
                                 "$articles"]}, 100]}, 2]},
        }},
    ]
    return list(coll.aggregate(pipeline, allowDiskUse=True))


def ticker_leaderboard(days: int = 90, min_articles: int = 20,
                       limit: int = 15) -> dict:
    """Most positively and most negatively covered tickers.

    One $facet runs both halves in a single pass over the matched set.
    """
    coll = mongo.get_db()[mongo.NEWS]
    latest = _latest_timestamp()
    if latest is None:
        return {"most_positive": [], "most_negative": [], "most_covered": []}

    base = [
        {"$match": {"published_at": {"$gte": latest - timedelta(days=days)}}},
        {"$group": {
            "_id": "$ticker",
            "articles": {"$sum": 1},
            "avg_sentiment": {"$avg": "$sentiment.score"},
            "positive": {"$sum": {"$cond": [
                {"$eq": ["$sentiment.label", "positive"]}, 1, 0]}},
            "negative": {"$sum": {"$cond": [
                {"$eq": ["$sentiment.label", "negative"]}, 1, 0]}},
        }},
        {"$match": {"articles": {"$gte": min_articles}}},
        {"$project": {
            "_id": 0, "ticker": "$_id", "articles": 1,
            "avg_sentiment": {"$round": ["$avg_sentiment", 4]},
            "positive": 1, "negative": 1,
        }},
        {"$facet": {
            "most_positive": [{"$sort": {"avg_sentiment": -1}}, {"$limit": limit}],
            "most_negative": [{"$sort": {"avg_sentiment": 1}}, {"$limit": limit}],
            "most_covered": [{"$sort": {"articles": -1}}, {"$limit": limit}],
        }},
    ]
    result = list(coll.aggregate(base, allowDiskUse=True))
    return result[0] if result else {"most_positive": [], "most_negative": [],
                                     "most_covered": []}


def publisher_breakdown(days: int = 90, limit: int = 12) -> list[dict]:
    coll = mongo.get_db()[mongo.NEWS]
    latest = _latest_timestamp()
    if latest is None:
        return []
    pipeline = [
        {"$match": {"published_at": {"$gte": latest - timedelta(days=days)},
                    "publisher": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$publisher", "articles": {"$sum": 1},
                    "avg_sentiment": {"$avg": "$sentiment.score"}}},
        {"$sort": {"articles": -1}},
        {"$limit": limit},
        {"$project": {"_id": 0, "publisher": "$_id", "articles": 1,
                      "avg_sentiment": {"$round": ["$avg_sentiment", 4]}}},
    ]
    return list(coll.aggregate(pipeline, allowDiskUse=True))


def sentiment_distribution(ticker: str | None = None) -> list[dict]:
    """$bucket the raw scores into bands -- a histogram without a scan
    in the client."""
    coll = mongo.get_db()[mongo.NEWS]
    match = {"ticker": ticker.strip().upper()} if ticker else {}
    pipeline = [
        {"$match": match},
        {"$bucket": {
            "groupBy": "$sentiment.score",
            "boundaries": [-1, -0.5, -0.25, -0.15, 0, 0.15, 0.25, 0.5, 1.01],
            "default": "other",
            "output": {"count": {"$sum": 1}},
        }},
        {"$project": {"_id": 0, "lower_bound": "$_id", "count": 1}},
    ]
    return list(coll.aggregate(pipeline, allowDiskUse=True))


def ticker_summary(ticker: str, days: int = 90) -> dict:
    """Headline sentiment card for one stock, used on the stock page."""
    coll = mongo.get_db()[mongo.NEWS]
    latest = _latest_timestamp()
    symbol = ticker.strip().upper()
    match: dict[str, Any] = {"ticker": symbol}
    if latest:
        match["published_at"] = {"$gte": latest - timedelta(days=days)}

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "articles": {"$sum": 1},
            "avg_sentiment": {"$avg": "$sentiment.score"},
            "positive": {"$sum": {"$cond": [
                {"$eq": ["$sentiment.label", "positive"]}, 1, 0]}},
            "negative": {"$sum": {"$cond": [
                {"$eq": ["$sentiment.label", "negative"]}, 1, 0]}},
            "neutral": {"$sum": {"$cond": [
                {"$eq": ["$sentiment.label", "neutral"]}, 1, 0]}},
            "publishers": {"$addToSet": "$publisher"},
        }},
        {"$project": {
            "_id": 0, "articles": 1, "positive": 1, "negative": 1, "neutral": 1,
            "avg_sentiment": {"$round": ["$avg_sentiment", 4]},
            "publisher_count": {"$size": "$publishers"},
        }},
    ]
    rows = list(coll.aggregate(pipeline, allowDiskUse=True))
    summary = rows[0] if rows else {"articles": 0, "positive": 0, "negative": 0,
                                    "neutral": 0, "avg_sentiment": 0,
                                    "publisher_count": 0}
    summary["ticker"] = symbol
    summary["window_days"] = days
    summary["recent"] = feed(ticker=symbol, limit=8)["articles"]
    return summary


# ---------------------------------------------------------------------
# company_profiles -- the variable-schema collection
# ---------------------------------------------------------------------
def profile(ticker: str) -> dict | None:
    doc = mongo.get_db()[mongo.PROFILES].find_one(
        {"ticker": ticker.strip().upper()})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def profiles_by_tag(tag: str, limit: int = 50) -> list[dict]:
    cursor = mongo.get_db()[mongo.PROFILES].find(
        {"tags": tag}, {"ticker": 1, "company_name": 1, "sector": 1, "tags": 1}
    ).limit(limit)
    return [_clean(d) for d in cursor]
