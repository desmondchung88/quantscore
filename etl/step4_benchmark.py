"""Step 4 -- mirror two datasets so the engines can be compared fairly.

A SQL-vs-NoSQL comparison is only meaningful if both stores hold the
same rows and answer the same questions. So:

  news  : MongoDB is the primary store -> mirrored into MySQL bench_news
  prices: MySQL is the primary store   -> mirrored into MongoDB bench_prices

Each engine therefore plays to its strength on one dataset and against
its grain on the other, which is what makes the timings interesting.
"""
from __future__ import annotations

from datetime import date, datetime, time

from common import Timer, banner

from app.db import mongo, mysql

NEWS_MIRROR_LIMIT = 400_000
PRICE_MIRROR_LIMIT = 400_000
BATCH = 10_000


def _as_datetime(value) -> datetime | None:
    if isinstance(value, datetime) or value is None:
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    return value


def mirror_news_to_mysql() -> int:
    coll = mongo.get_db()[mongo.NEWS]
    mysql.execute("DELETE FROM bench_news")

    sql = (
        "INSERT INTO bench_news"
        " (ticker, headline, publisher, published_at, sentiment, sentiment_label)"
        " VALUES (:t, :h, :p, :d, :s, :l)"
    )
    cursor = coll.find(
        {},
        {"ticker": 1, "headline": 1, "publisher": 1, "published_at": 1, "sentiment": 1},
    ).limit(NEWS_MIRROR_LIMIT).batch_size(BATCH)

    buffer, total = [], 0
    for doc in cursor:
        buffer.append({
            "t": doc["ticker"],
            "h": doc["headline"][:500],
            "p": (doc.get("publisher") or None),
            "d": doc["published_at"],
            "s": float(doc["sentiment"]["score"]),
            "l": doc["sentiment"]["label"],
        })
        if len(buffer) >= BATCH:
            mysql.bulk_insert(sql, buffer)
            total += len(buffer)
            buffer.clear()
    if buffer:
        mysql.bulk_insert(sql, buffer)
        total += len(buffer)
    return total


def mirror_prices_to_mongo() -> int:
    coll = mongo.get_db()[mongo.BENCH_PRICES]
    coll.delete_many({})

    rows = mysql.query(
        "SELECT s.ticker, p.price_date, p.open_price, p.high_price, p.low_price,"
        "       p.close_price, p.adjusted_close, p.volume"
        "  FROM stock_prices p JOIN stocks s ON s.stock_id = p.stock_id"
        " ORDER BY p.price_date DESC, s.ticker"
        " LIMIT :lim",
        {"lim": PRICE_MIRROR_LIMIT},
    )

    docs, total = [], 0
    for r in rows:
        docs.append({
            "ticker": r["ticker"],
            # BSON has no date type, only datetime -- MySQL hands back a
            # date, so widen it to midnight rather than let pymongo fail.
            "date": _as_datetime(r["price_date"]),
            "open": r["open_price"], "high": r["high_price"],
            "low": r["low_price"], "close": r["close_price"],
            "adj_close": r["adjusted_close"], "volume": r["volume"],
        })
        if len(docs) >= BATCH:
            coll.insert_many(docs, ordered=False)
            total += len(docs)
            docs.clear()
    if docs:
        coll.insert_many(docs, ordered=False)
        total += len(docs)

    coll.create_index([("ticker", 1), ("date", 1)], name="ix_bench_ticker_date")
    return total


def main() -> None:
    banner("STEP 4  Benchmark mirrors")

    with Timer(f"MongoDB news_articles -> MySQL bench_news (<= {NEWS_MIRROR_LIMIT:,})"):
        n = mirror_news_to_mysql()
        print(f"     {n:,} rows")

    with Timer(f"MySQL stock_prices -> MongoDB bench_prices (<= {PRICE_MIRROR_LIMIT:,})"):
        m = mirror_prices_to_mongo()
        print(f"     {m:,} documents")

    print("\n  Both engines now hold identical copies of both datasets.")


if __name__ == "__main__":
    main()
