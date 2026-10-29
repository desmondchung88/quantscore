"""End-to-end smoke test.

Checks that both databases are reachable and loaded, that every view and
stored program works, that the integrity rules actually fire, and that
the API's own service layer returns sensible data.

    python etl/verify.py

Exit code 0 means everything passed.
"""
from __future__ import annotations

import sys
import traceback

from common import banner

from app.db import mongo, mysql

PASS, FAIL = [], []


def check(name: str, fn, *, expect_failure: str | None = None) -> None:
    """Run one assertion. `expect_failure` asserts the call raises and the
    message contains that token -- used for the integrity rules."""
    try:
        result = fn()
        if expect_failure:
            FAIL.append((name, f"expected it to be rejected with "
                               f"{expect_failure}, but it succeeded"))
            print(f"  FAIL  {name}")
            return
        detail = "" if result is True or result is None else f"  ({result})"
        PASS.append(name)
        print(f"  ok    {name}{detail}")
    except Exception as exc:
        message = str(exc)
        if expect_failure and expect_failure in message:
            PASS.append(name)
            print(f"  ok    {name}  (correctly rejected)")
        else:
            FAIL.append((name, message.splitlines()[0][:150]))
            print(f"  FAIL  {name}: {message.splitlines()[0][:150]}")


# ---------------------------------------------------------------------
def check_relational() -> None:
    banner("Relational database")

    check("connects", lambda: mysql.query_one("SELECT 1 AS n")["n"] == 1)

    counts = mysql.query_one(
        "SELECT (SELECT COUNT(*) FROM stocks)             AS stocks,"
        "       (SELECT COUNT(*) FROM sectors)            AS sectors,"
        "       (SELECT COUNT(*) FROM stock_prices)       AS prices,"
        "       (SELECT COUNT(*) FROM financial_snapshots) AS snaps,"
        "       (SELECT COUNT(*) FROM stock_latest_price) AS cached"
    )
    check("stocks loaded", lambda: f"{counts['stocks']} companies"
          if counts["stocks"] > 400 else (_ for _ in ()).throw(
              AssertionError(f"only {counts['stocks']} stocks")))
    check("sectors loaded", lambda: f"{counts['sectors']} sectors"
          if counts["sectors"] >= 5 else (_ for _ in ()).throw(
              AssertionError("too few sectors")))
    check("price history loaded", lambda: f"{counts['prices']:,} rows"
          if counts["prices"] > 100_000 else (_ for _ in ()).throw(
              AssertionError(f"only {counts['prices']} price rows")))
    check("latest-price cache built", lambda: f"{counts['cached']} stocks"
          if counts["cached"] > 400 else (_ for _ in ()).throw(
              AssertionError("run sp_refresh_latest_prices()")))

    for view in ("v_latest_snapshot", "v_stock_metrics", "v_sector_averages",
                 "v_stock_metrics_peer", "v_stock_scores",
                 "v_stock_scores_total", "v_portfolio_holdings",
                 "v_portfolio_summary"):
        check(f"view {view}",
              lambda v=view: f"{mysql.query_one(f'SELECT COUNT(*) AS n FROM {v}')['n']} rows")

    check("scores are in range 0-100", lambda: _scores_in_range())
    check("sp_sector_leaderboard()",
          lambda: f"{len(mysql.query('CALL sp_sector_leaderboard(0)'))} sectors")

    check("window functions produced returns", lambda: _has_returns())
    check("EXPLAIN uses the composite PK", lambda: _explain_uses_index())


def _scores_in_range() -> str:
    row = mysql.query_one(
        "SELECT MIN(total_score) AS lo, MAX(total_score) AS hi,"
        "       AVG(total_score) AS avg FROM v_stock_scores_total"
        " WHERE total_score IS NOT NULL")
    if row["lo"] is None:
        raise AssertionError("no scores computed")
    if row["lo"] < 0 or row["hi"] > 100:
        raise AssertionError(f"out of range: {row['lo']}..{row['hi']}")
    return f"{row['lo']:.1f}..{row['hi']:.1f}, mean {row['avg']:.1f}"


def _has_returns() -> str:
    row = mysql.query_one(
        "SELECT COUNT(ret_1y) AS n, AVG(vol_30d) AS vol FROM stock_latest_price")
    if not row["n"]:
        raise AssertionError("no 1-year returns computed")
    return f"{row['n']} stocks with a 1y return, mean 30d vol {row['vol']:.3f}"


def _explain_uses_index() -> str:
    plan = mysql.query(
        "EXPLAIN SELECT close_price FROM stock_prices"
        " WHERE stock_id = 1 AND price_date > '2022-01-01'")
    key = plan[0].get("key") if plan else None
    if not key:
        raise AssertionError("full table scan -- the index is not being used")
    return f"key={key}"


# ---------------------------------------------------------------------
def check_integrity() -> None:
    banner("Integrity rules (these SHOULD be rejected)")

    user = mysql.query_one("SELECT user_id FROM users WHERE username = 'demo'")
    if user is None:
        print("  (skipped -- run step5_seed.py first)")
        return
    pf = mysql.query_one(
        "SELECT portfolio_id, cash_balance FROM portfolios"
        " WHERE user_id = :u ORDER BY portfolio_id LIMIT 1", {"u": user["user_id"]})
    if pf is None:
        print("  (skipped -- no portfolio)")
        return
    pid = pf["portfolio_id"]

    check("CHECK: negative trade quantity",
          lambda: mysql.execute(
              "INSERT INTO transactions (portfolio_id, stock_id, transaction_type,"
              " quantity, execution_price) VALUES (:p, 1, 'BUY', -5, 10)",
              {"p": pid}),
          expect_failure="chk_txn_qty")

    check("FK: trade against a non-existent stock",
          lambda: mysql.execute(
              "INSERT INTO transactions (portfolio_id, stock_id, transaction_type,"
              " quantity, execution_price) VALUES (:p, 99999999, 'BUY', 1, 10)",
              {"p": pid}),
          expect_failure="fk_txn_stock")

    check("UNIQUE: duplicate ticker",
          lambda: mysql.execute(
              "INSERT INTO stocks (ticker, company_name)"
              " SELECT ticker, 'dupe' FROM stocks LIMIT 1"),
          expect_failure="uq_stock_ticker")

    check("CHECK: malformed email",
          lambda: mysql.execute(
              "INSERT INTO users (username, email, password_hash)"
              " VALUES ('verifyuser', 'not-an-email', 'x')"),
          expect_failure="chk_email")

    check("TRIGGER: selling more than held",
          lambda: mysql.call_trade_procedure(pid, "AAPL", "SELL", 1e9, 0),
          expect_failure="INSUFFICIENT_HOLDINGS")

    check("TRIGGER: buying beyond the cash balance",
          lambda: mysql.call_trade_procedure(pid, "AAPL", "BUY", 1e9, 0),
          expect_failure="INSUFFICIENT_CASH")

    check("PROCEDURE: unknown ticker",
          lambda: mysql.call_trade_procedure(pid, "ZZZZ", "BUY", 1, 0),
          expect_failure="UNKNOWN_TICKER")

    # After all those rejections the cash balance must be untouched.
    after = mysql.query_one(
        "SELECT cash_balance FROM portfolios WHERE portfolio_id = :p", {"p": pid})
    check("cash balance unchanged after the rollbacks",
          lambda: f"${after['cash_balance']:,.2f}"
          if abs(after["cash_balance"] - pf["cash_balance"]) < 0.01
          else (_ for _ in ()).throw(AssertionError(
              f"{pf['cash_balance']} -> {after['cash_balance']}")))


# ---------------------------------------------------------------------
def check_documents() -> None:
    banner("Document database")

    if not mongo.ping():
        FAIL.append(("mongodb reachable", "cannot connect"))
        print("  FAIL  mongodb reachable -- is the container running?")
        return
    PASS.append("mongodb reachable")
    print("  ok    mongodb reachable")

    db = mongo.get_db()
    news = db[mongo.NEWS]

    check("news_articles loaded",
          lambda: f"{news.estimated_document_count():,} documents"
          if news.estimated_document_count() > 1000
          else (_ for _ in ()).throw(AssertionError("too few documents")))

    check("compound index present",
          lambda: "ix_ticker_time" if "ix_ticker_time" in news.index_information()
          else (_ for _ in ()).throw(AssertionError("missing ix_ticker_time")))
    check("text index present",
          lambda: "ix_headline_text"
          if "ix_headline_text" in news.index_information()
          else (_ for _ in ()).throw(AssertionError("missing text index")))
    check("TTL index on activity_logs",
          lambda: _ttl_index())

    check("document validator rejects a bad document",
          lambda: news.insert_one({"ticker": "XXX"}),
          expect_failure="failed validation")

    check("$group aggregation", lambda: _agg_group())
    check("$facet leaderboard", lambda: _agg_facet())
    check("full-text search",
          lambda: f"{len(list(news.find({'$text': {'$search': 'earnings'}}).limit(5)))} hits")

    check("company_profiles are variable-schema", lambda: _profiles_vary())


def _ttl_index() -> str:
    info = mongo.get_db()[mongo.ACTIVITY].index_information()
    ix = info.get("ix_activity_ttl")
    if not ix or "expireAfterSeconds" not in ix:
        raise AssertionError("no TTL index")
    return f"{ix['expireAfterSeconds'] // 86400} days"


def _agg_group() -> str:
    rows = list(mongo.get_db()[mongo.NEWS].aggregate([
        {"$group": {"_id": "$sentiment.label", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ], allowDiskUse=True))
    if not rows:
        raise AssertionError("no results")
    return ", ".join(f"{r['_id']}={r['n']:,}" for r in rows)


def _agg_facet() -> str:
    from app.services import news as svc

    board = svc.ticker_leaderboard(days=3000, min_articles=10, limit=3)
    if not board["most_positive"]:
        raise AssertionError("empty leaderboard")
    top = board["most_positive"][0]
    return f"most positive: {top['ticker']} ({top['avg_sentiment']})"


def _profiles_vary() -> str:
    coll = mongo.get_db()[mongo.PROFILES]
    with_reg = coll.count_documents({"regulatory": {"$exists": True}})
    with_reit = coll.count_documents({"reit": {"$exists": True}})
    total = coll.estimated_document_count()
    if total == 0:
        raise AssertionError("no profiles loaded")
    return (f"{total} profiles; {with_reg} carry regulatory fields, "
            f"{with_reit} carry REIT fields")


# ---------------------------------------------------------------------
def check_services() -> None:
    banner("Application services")

    from app.services import news as news_svc
    from app.services import scoring, screener, stocks

    check("stock search", lambda: f"{len(stocks.search('apple'))} hits")
    check("stock detail", lambda: _detail())
    check("price history",
          lambda: f"{len(stocks.price_history('AAPL', 120))} bars")
    check("sector overview",
          lambda: f"{len(stocks.sector_overview())} sectors")
    check("screener", lambda: _screener())
    check("score leaderboard",
          lambda: f"top = {scoring.leaderboard(scoring.Weights(), limit=1)['results'][0]['ticker']}")
    check("score explanation", lambda: _explain())
    if mongo.ping():
        check("sentiment timeline",
              lambda: f"{len(news_svc.sentiment_timeline(days=3000, granularity='month'))} buckets")


def _detail() -> str:
    from app.services import stocks

    data = stocks.detail("AAPL")
    if data is None:
        raise AssertionError("AAPL not found")
    return (f"score {data['stock']['total_score']}, "
            f"{len(data['comparisons'])} sector comparisons")


def _screener() -> str:
    from app.services import screener

    out = screener.run({"min_market_cap": 1e10, "exclude_null_pe": True},
                       limit=10)
    return f"{out['stats']['matches']} matches, avg score {out['stats']['avg_score']}"


def _explain() -> str:
    from app.services import scoring

    data = scoring.explain("MSFT", scoring.Weights())
    if data is None:
        raise AssertionError("MSFT not found")
    return f"{data['grade']} ({data['weighted_score']}), {len(data['factors'])} factors"


# ---------------------------------------------------------------------
def main() -> None:
    banner("QuantScore verification")
    try:
        check_relational()
        check_integrity()
        check_documents()
        check_services()
    except Exception:
        traceback.print_exc()
        FAIL.append(("verification run", "crashed -- see traceback above"))

    banner(f"RESULT  {len(PASS)} passed, {len(FAIL)} failed")
    for name, why in FAIL:
        print(f"  FAILED  {name}: {why}")
    print()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
