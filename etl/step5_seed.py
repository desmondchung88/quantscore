"""Step 5 -- seed demo users, portfolios, watchlists and a trade history.

Trades go through sp_execute_trade, so the seed exercises the same
locking, triggers and cash accounting as the live application.
"""
from __future__ import annotations

import sys
from pathlib import Path

from common import Timer, banner

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import settings
from app.core.security import hash_password
from app.db import mongo, mysql

DEMO_USERS = [
    ("demo", "demo@quantscore.local", "demo1234"),
    ("damien", "2500837@sit.singaporetech.edu.sg", "quantscore"),
    ("adora", "2502513@sit.singaporetech.edu.sg", "quantscore"),
    ("calson", "2502169@sit.singaporetech.edu.sg", "quantscore"),
    ("aumyat", "2502143@sit.singaporetech.edu.sg", "quantscore"),
    ("desmond", "2502081@sit.singaporetech.edu.sg", "quantscore"),
]

DEMO_TRADES = [
    ("AAPL", "BUY", 60), ("MSFT", "BUY", 40), ("JNJ", "BUY", 50),
    ("XOM", "BUY", 100), ("JPM", "BUY", 45), ("NVDA", "BUY", 30),
    ("PG", "BUY", 55), ("AAPL", "SELL", 10),
]

DEMO_WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "TSLA", "JPM", "XOM"]


def main() -> None:
    banner("STEP 5  Demo users, portfolios and trades")

    with Timer("users"):
        for username, email, password in DEMO_USERS:
            mysql.execute(
                "INSERT INTO users (username, email, password_hash)"
                " VALUES (:u, :e, :p)"
                " ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash)",
                {"u": username, "e": email, "p": hash_password(password)},
            )
        print(f"     {len(DEMO_USERS)} users "
              f"(login as 'demo' / 'demo1234')")

    user = mysql.query_one("SELECT user_id FROM users WHERE username = 'demo'")
    uid = user["user_id"]

    with Timer("portfolio + watchlist"):
        mysql.execute(
            "INSERT INTO portfolios (user_id, name, initial_cash, cash_balance)"
            " VALUES (:u, 'Core Holdings', 100000, 100000)"
            " ON DUPLICATE KEY UPDATE portfolio_id = LAST_INSERT_ID(portfolio_id)",
            {"u": uid},
        )
        pf = mysql.query_one(
            "SELECT portfolio_id FROM portfolios"
            " WHERE user_id = :u AND name = 'Core Holdings'", {"u": uid})
        pid = pf["portfolio_id"]

        mysql.execute(
            "INSERT IGNORE INTO watchlists (user_id, name) VALUES (:u, 'Megacap Tech')",
            {"u": uid})
        wl = mysql.query_one(
            "SELECT watchlist_id FROM watchlists"
            " WHERE user_id = :u AND name = 'Megacap Tech'", {"u": uid})
        # Generated placeholders keep the IN list parameterised.
        slots = ", ".join(f":t{i}" for i in range(len(DEMO_WATCHLIST)))
        params = {f"t{i}": t for i, t in enumerate(DEMO_WATCHLIST)}
        params["w"] = wl["watchlist_id"]
        mysql.execute(
            "INSERT IGNORE INTO watchlist_stocks (watchlist_id, stock_id)"
            f" SELECT :w, stock_id FROM stocks WHERE ticker IN ({slots})",
            params,
        )

    with Timer("trades via sp_execute_trade()"):
        existing = mysql.query_one(
            "SELECT COUNT(*) AS n FROM transactions WHERE portfolio_id = :p",
            {"p": pid})
        if existing["n"]:
            print(f"     portfolio already has {existing['n']} trades, skipping")
        else:
            done = 0
            for ticker, side, qty in DEMO_TRADES:
                try:
                    mysql.call_trade_procedure(
                        pid, ticker, side, qty, settings.TRADE_FEE_RATE)
                    done += 1
                except Exception as exc:  # unknown ticker / no price / no cash
                    print(f"     skipped {side} {qty} {ticker}: "
                          f"{str(exc).splitlines()[0][:90]}")
            print(f"     {done}/{len(DEMO_TRADES)} trades executed")

    summary = mysql.query_one(
        "SELECT * FROM v_portfolio_summary WHERE portfolio_id = :p", {"p": pid})
    if summary:
        print(f"\n  '{summary['name']}': {summary['positions']} positions, "
              f"cash ${summary['cash_balance']:,.2f}, "
              f"market value ${summary['market_value']:,.2f}, "
              f"total ${summary['total_value']:,.2f}")

    mongo.log_activity(uid, "seed", {"portfolio_id": pid})


if __name__ == "__main__":
    main()
