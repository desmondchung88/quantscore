"""SQL vs NoSQL performance harness.

Both engines hold the same two datasets (see etl/step4_benchmark.py), so
each scenario below is the *same question* asked twice. Every scenario
is run several times; the first run is discarded as a warm-up and the
median of the rest is reported, because a single timing on a laptop is
mostly noise.

Throughput is reported as the number of source rows the engine had to
consider per second, which makes scenarios of different sizes
comparable.
"""
from __future__ import annotations

import statistics
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from app.db import mongo, mysql

DEFAULT_RUNS = 5


# ---------------------------------------------------------------------
# Timing primitives
# ---------------------------------------------------------------------
def _time_it(fn: Callable[[], Any], runs: int) -> dict:
    timings: list[float] = []
    rows = 0
    error: str | None = None

    try:
        fn()  # warm-up: fills the buffer pool / working set
        for _ in range(runs):
            start = time.perf_counter()
            result = fn()
            timings.append((time.perf_counter() - start) * 1000)
            rows = len(result) if hasattr(result, "__len__") else 1
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"

    if error or not timings:
        return {"error": error or "no timings", "median_ms": None}

    return {
        "median_ms": round(statistics.median(timings), 2),
        "mean_ms": round(statistics.fmean(timings), 2),
        "min_ms": round(min(timings), 2),
        "max_ms": round(max(timings), 2),
        "stdev_ms": round(statistics.stdev(timings), 2) if len(timings) > 1 else 0.0,
        "rows_returned": rows,
        "runs": len(timings),
    }


def _latest_news_date() -> datetime:
    doc = mongo.get_db()[mongo.NEWS].find_one(
        {}, {"published_at": 1}, sort=[("published_at", -1)])
    return doc["published_at"] if doc else datetime(2020, 6, 1)


def _dataset_sizes() -> dict:
    sql_news = mysql.query_one("SELECT COUNT(*) AS n FROM bench_news")
    sql_prices = mysql.query_one("SELECT COUNT(*) AS n FROM stock_prices")
    db = mongo.get_db()
    return {
        "mysql_bench_news": sql_news["n"] if sql_news else 0,
        "mysql_stock_prices": sql_prices["n"] if sql_prices else 0,
        "mongo_news_articles": db[mongo.NEWS].estimated_document_count(),
        "mongo_bench_prices": db[mongo.BENCH_PRICES].estimated_document_count(),
    }


# ---------------------------------------------------------------------
# Scenarios -- each is (name, description, dataset, sql_fn, mongo_fn)
# ---------------------------------------------------------------------
def _scenarios(ticker: str, days: int) -> list[dict]:
    cutoff = _latest_news_date() - timedelta(days=days)
    news = mongo.get_db()[mongo.NEWS]
    prices = mongo.get_db()[mongo.BENCH_PRICES]

    return [
        {
            "key": "point_lookup",
            "name": "Point lookup",
            "description": f"50 most recent headlines for {ticker}",
            "dataset": "news",
            "indexes": "MySQL: (ticker, published_at) B-tree | "
                       "MongoDB: compound {ticker:1, published_at:-1}",
            "sql": lambda: mysql.query(
                "SELECT ticker, headline, published_at, sentiment"
                "  FROM bench_news WHERE ticker = :t"
                " ORDER BY published_at DESC LIMIT 50", {"t": ticker}),
            "mongo": lambda: list(
                news.find({"ticker": ticker},
                          {"ticker": 1, "headline": 1, "published_at": 1,
                           "sentiment": 1})
                .sort([("published_at", -1)]).limit(50)),
        },
        {
            "key": "range_scan",
            "name": "Range scan + filter",
            "description": f"Negative headlines in the last {days} days",
            "dataset": "news",
            "indexes": "MySQL: (sentiment_label, published_at) | "
                       "MongoDB: {sentiment.label:1, published_at:-1}",
            "sql": lambda: mysql.query(
                "SELECT ticker, headline, published_at FROM bench_news"
                " WHERE sentiment_label = 'negative' AND published_at >= :c"
                " ORDER BY published_at DESC LIMIT 200", {"c": cutoff}),
            "mongo": lambda: list(
                news.find({"sentiment.label": "negative",
                           "published_at": {"$gte": cutoff}},
                          {"ticker": 1, "headline": 1, "published_at": 1})
                .sort([("published_at", -1)]).limit(200)),
        },
        {
            "key": "group_by",
            "name": "Grouped aggregation",
            "description": "Article count and mean sentiment per ticker",
            "dataset": "news",
            "indexes": "MySQL: (published_at) then GROUP BY | "
                       "MongoDB: {published_at:-1} then $group",
            "sql": lambda: mysql.query(
                "SELECT ticker, COUNT(*) AS n, AVG(sentiment) AS avg_sentiment"
                "  FROM bench_news WHERE published_at >= :c"
                " GROUP BY ticker HAVING n >= 20"
                " ORDER BY avg_sentiment DESC LIMIT 100", {"c": cutoff}),
            "mongo": lambda: list(news.aggregate([
                {"$match": {"published_at": {"$gte": cutoff}}},
                {"$group": {"_id": "$ticker", "n": {"$sum": 1},
                            "avg_sentiment": {"$avg": "$sentiment.score"}}},
                {"$match": {"n": {"$gte": 20}}},
                {"$sort": {"avg_sentiment": -1}},
                {"$limit": 100},
            ], allowDiskUse=True)),
        },
        {
            "key": "time_bucket",
            "name": "Time bucketing",
            "description": "Monthly article volume and mean sentiment",
            "dataset": "news",
            "indexes": "MySQL: DATE_FORMAT + GROUP BY | "
                       "MongoDB: $dateTrunc + $group",
            "sql": lambda: mysql.query(
                "SELECT DATE_FORMAT(published_at, '%Y-%m') AS period,"
                "       COUNT(*) AS n, AVG(sentiment) AS avg_sentiment"
                "  FROM bench_news GROUP BY period ORDER BY period"),
            "mongo": lambda: list(news.aggregate([
                {"$group": {
                    "_id": {"$dateTrunc": {"date": "$published_at",
                                           "unit": "month"}},
                    "n": {"$sum": 1},
                    "avg_sentiment": {"$avg": "$sentiment.score"}}},
                {"$sort": {"_id": 1}},
            ], allowDiskUse=True)),
        },
        {
            "key": "text_search",
            "name": "Full-text search",
            "description": "Headlines matching 'earnings'",
            "dataset": "news",
            "indexes": "MySQL: FULLTEXT (headline) | "
                       "MongoDB: text index on headline",
            "sql": lambda: mysql.query(
                "SELECT ticker, headline, published_at FROM bench_news"
                " WHERE MATCH(headline) AGAINST (:q IN NATURAL LANGUAGE MODE)"
                " LIMIT 100", {"q": "earnings"}),
            "mongo": lambda: list(
                news.find({"$text": {"$search": "earnings"}},
                          {"ticker": 1, "headline": 1, "published_at": 1})
                .limit(100)),
        },
        {
            "key": "timeseries_scan",
            "name": "Time-series scan",
            "description": f"Full price history for {ticker}",
            "dataset": "prices",
            "indexes": "MySQL: clustered PK (stock_id, price_date) | "
                       "MongoDB: compound {ticker:1, date:1}",
            "sql": lambda: mysql.query(
                "SELECT p.price_date, p.close_price, p.volume"
                "  FROM stock_prices p JOIN stocks s ON s.stock_id = p.stock_id"
                " WHERE s.ticker = :t ORDER BY p.price_date", {"t": ticker}),
            "mongo": lambda: list(
                prices.find({"ticker": ticker},
                            {"date": 1, "close": 1, "volume": 1})
                .sort([("date", 1)])),
        },
        {
            "key": "join_vs_lookup",
            "name": "Join vs embedded lookup",
            "description": "Top 100 one-day movers with company and sector",
            "dataset": "prices",
            "indexes": "MySQL: 3-table join on indexed keys | "
                       "MongoDB: $lookup into company_profiles",
            "sql": lambda: mysql.query(
                "SELECT s.ticker, s.company_name, sec.sector_name,"
                "       p.close_price, p.volume"
                "  FROM stock_prices p"
                "  JOIN stocks s     ON s.stock_id = p.stock_id"
                "  LEFT JOIN sectors sec ON sec.sector_id = s.sector_id"
                " WHERE p.price_date = (SELECT MAX(price_date) FROM stock_prices)"
                " ORDER BY p.volume DESC LIMIT 100"),
            "mongo": lambda: list(prices.aggregate([
                {"$sort": {"date": -1}},
                {"$limit": 2000},
                {"$sort": {"volume": -1}},
                {"$limit": 100},
                {"$lookup": {"from": mongo.PROFILES, "localField": "ticker",
                             "foreignField": "ticker", "as": "profile"}},
                {"$unwind": {"path": "$profile",
                             "preserveNullAndEmptyArrays": True}},
                {"$project": {"_id": 0, "ticker": 1, "close": 1, "volume": 1,
                              "company_name": "$profile.company_name",
                              "sector": "$profile.sector"}},
            ], allowDiskUse=True)),
        },
    ]


# ---------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------
def run(ticker: str = "AAPL", days: int = 365, runs: int = DEFAULT_RUNS,
        only: list[str] | None = None) -> dict:
    ticker = ticker.strip().upper()
    runs = max(1, min(int(runs), 15))

    results = []
    for scenario in _scenarios(ticker, days):
        if only and scenario["key"] not in only:
            continue

        sql_stats = _time_it(scenario["sql"], runs)
        mongo_stats = _time_it(scenario["mongo"], runs)

        verdict, ratio = _compare(sql_stats, mongo_stats)
        results.append({
            "key": scenario["key"],
            "name": scenario["name"],
            "description": scenario["description"],
            "dataset": scenario["dataset"],
            "indexes": scenario["indexes"],
            "mysql": sql_stats,
            "mongodb": mongo_stats,
            "faster": verdict,
            "speedup": ratio,
        })

    return {
        "ticker": ticker,
        "window_days": days,
        "runs_per_scenario": runs,
        "dataset_sizes": _dataset_sizes(),
        "scenarios": results,
        "summary": _summarise(results),
        "method": (
            "Each scenario is executed once to warm the cache, then "
            f"{runs} times; the median is reported. Both engines hold "
            "identical copies of both datasets."
        ),
    }


def _compare(sql_stats: dict, mongo_stats: dict) -> tuple[str, float | None]:
    a, b = sql_stats.get("median_ms"), mongo_stats.get("median_ms")
    if a is None or b is None or a <= 0 or b <= 0:
        return "n/a", None
    if a < b:
        return "mysql", round(b / a, 2)
    if b < a:
        return "mongodb", round(a / b, 2)
    return "tie", 1.0


def _summarise(results: list[dict]) -> dict:
    wins = {"mysql": 0, "mongodb": 0, "tie": 0, "n/a": 0}
    for r in results:
        wins[r["faster"]] = wins.get(r["faster"], 0) + 1

    sql_times = [r["mysql"]["median_ms"] for r in results
                 if r["mysql"].get("median_ms")]
    mongo_times = [r["mongodb"]["median_ms"] for r in results
                   if r["mongodb"].get("median_ms")]

    return {
        "scenarios_run": len(results),
        "mysql_wins": wins["mysql"],
        "mongodb_wins": wins["mongodb"],
        "total_mysql_ms": round(sum(sql_times), 2),
        "total_mongodb_ms": round(sum(mongo_times), 2),
    }


def explain_plan(ticker: str = "AAPL") -> dict:
    """Side-by-side query plans for the point-lookup scenario."""
    sql_plan = mysql.query(
        "EXPLAIN SELECT ticker, headline, published_at FROM bench_news"
        " WHERE ticker = :t ORDER BY published_at DESC LIMIT 50",
        {"t": ticker.upper()},
    )
    try:
        mongo_plan = mongo.get_db()[mongo.NEWS].find(
            {"ticker": ticker.upper()}
        ).sort([("published_at", -1)]).limit(50).explain()
        winning = (mongo_plan.get("queryPlanner", {})
                   .get("winningPlan", {}))
    except Exception as exc:
        winning = {"error": str(exc)[:200]}

    return {"mysql_explain": sql_plan, "mongodb_winning_plan": winning}


def index_impact(ticker: str = "AAPL", runs: int = 3) -> dict:
    """Show what the index is actually worth.

    The same lookup is run with the index available and then with
    IGNORE INDEX, which forces a full table scan.
    """
    indexed = _time_it(
        lambda: mysql.query(
            "SELECT ticker, headline FROM bench_news WHERE ticker = :t"
            " ORDER BY published_at DESC LIMIT 50", {"t": ticker.upper()}),
        runs,
    )
    # Every candidate index has to be hidden, not just the obvious one:
    # with only idx_bench_ticker_time ignored the optimiser simply falls
    # back to idx_bench_time and the comparison measures nothing.
    scanned = _time_it(
        lambda: mysql.query(
            "SELECT ticker, headline FROM bench_news"
            " IGNORE INDEX (idx_bench_ticker_time, idx_bench_time,"
            "               idx_bench_sentiment_time)"
            " WHERE ticker = :t ORDER BY published_at DESC LIMIT 50",
            {"t": ticker.upper()}),
        runs,
    )
    speedup = None
    if indexed.get("median_ms") and scanned.get("median_ms"):
        speedup = round(scanned["median_ms"] / indexed["median_ms"], 2)

    return {
        "with_index": indexed,
        "without_index": scanned,
        "speedup": speedup,
        "note": "Same query, same rows; the only difference is whether the "
                "optimiser is allowed to use any index on bench_news.",
    }
