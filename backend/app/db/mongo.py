"""Document data access (MongoDB).

Collections
-----------
news_articles     high-volume, variable-schema headline feed with an
                  application-computed sentiment sub-document.
company_profiles  per-company metadata whose shape varies by sector --
                  the case for a schemaless store: a bank carries
                  regulatory fields a biotech does not.
research_notes    free-text user notes, tags and arbitrary attachments.
activity_logs     append-only user activity, expired automatically by a
                  TTL index instead of a housekeeping job.
"""
from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient, TEXT
from pymongo.database import Database

from app.config import settings

_client: MongoClient | None = None

NEWS = "news_articles"
PROFILES = "company_profiles"
NOTES = "research_notes"
ACTIVITY = "activity_logs"
BENCH_PRICES = "bench_prices"


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(
            settings.MONGO_URI,
            serverSelectionTimeoutMS=5000,
            tz_aware=False,
        )
    return _client


def get_db() -> Database:
    return get_client()[settings.MONGO_DB]


def ping() -> bool:
    try:
        get_client().admin.command("ping")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------
# Schema design -- applied by the ETL and on application start-up.
# ---------------------------------------------------------------------

NEWS_VALIDATOR: dict[str, Any] = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["ticker", "headline", "published_at", "sentiment"],
        "properties": {
            "ticker": {"bsonType": "string", "maxLength": 10},
            "headline": {"bsonType": "string"},
            "url": {"bsonType": ["string", "null"]},
            "publisher": {"bsonType": ["string", "null"]},
            "published_at": {"bsonType": "date"},
            "source": {"bsonType": "string"},
            "sentiment": {
                "bsonType": "object",
                "required": ["score", "label"],
                "properties": {
                    "score": {"bsonType": "double", "minimum": -1, "maximum": 1},
                    "label": {"enum": ["positive", "neutral", "negative"]},
                    "terms": {"bsonType": "array"},
                },
            },
        },
    }
}


def ensure_collections() -> None:
    """Create collections, document validators and indexes (idempotent)."""
    db = get_db()
    existing = set(db.list_collection_names())

    if NEWS not in existing:
        db.create_collection(NEWS, validator=NEWS_VALIDATOR, validationLevel="moderate")
    else:
        db.command("collMod", NEWS, validator=NEWS_VALIDATOR, validationLevel="moderate")

    news = db[NEWS]
    # Compound index: the feed is always "this ticker, newest first".
    news.create_index([("ticker", ASCENDING), ("published_at", DESCENDING)],
                      name="ix_ticker_time")
    news.create_index([("published_at", DESCENDING)], name="ix_time")
    news.create_index([("sentiment.label", ASCENDING), ("published_at", DESCENDING)],
                      name="ix_sentiment_time")
    # Full-text search over headlines.
    news.create_index([("headline", TEXT)], name="ix_headline_text",
                      default_language="english")

    db[PROFILES].create_index([("ticker", ASCENDING)], name="ix_profile_ticker",
                              unique=True)
    db[PROFILES].create_index([("sector", ASCENDING)], name="ix_profile_sector")
    db[PROFILES].create_index([("tags", ASCENDING)], name="ix_profile_tags")

    db[NOTES].create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)],
                           name="ix_notes_user")
    db[NOTES].create_index([("ticker", ASCENDING)], name="ix_notes_ticker")
    db[NOTES].create_index([("tags", ASCENDING)], name="ix_notes_tags")
    db[NOTES].create_index([("body", TEXT), ("title", TEXT)], name="ix_notes_text")

    # TTL: activity rows evaporate after 30 days with no cron job.
    db[ACTIVITY].create_index([("created_at", ASCENDING)], name="ix_activity_ttl",
                              expireAfterSeconds=60 * 60 * 24 * 30)
    db[ACTIVITY].create_index([("user_id", ASCENDING), ("created_at", DESCENDING)],
                              name="ix_activity_user")

    db[BENCH_PRICES].create_index([("ticker", ASCENDING), ("date", ASCENDING)],
                                  name="ix_bench_ticker_date")


def log_activity(user_id: int | None, action: str, payload: dict | None = None) -> None:
    """Fire-and-forget audit trail. Never allowed to break a request."""
    from datetime import datetime

    try:
        get_db()[ACTIVITY].insert_one(
            {
                "user_id": user_id,
                "action": action,
                "payload": payload or {},
                "created_at": datetime.utcnow(),
            }
        )
    except Exception:
        pass
