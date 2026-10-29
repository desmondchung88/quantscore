"""Intelligent stock search and stock detail.

The point of difference: a ratio on its own means nothing. Every number
returned here arrives with its sector benchmark and a plain-English
verdict, so "P/E 18.4" becomes "P/E 18.4, 24% cheaper than the sector".
"""
from __future__ import annotations

from app.db import mysql

# Metrics where a lower number is the better number.
LOWER_IS_BETTER = {"pe_ratio", "price_sales_ratio", "price_book_ratio"}

METRIC_LABELS = {
    "pe_ratio": ("P/E", "sec_avg_pe"),
    "price_sales_ratio": ("P/S", "sec_avg_ps"),
    "price_book_ratio": ("P/B", "sec_avg_pb"),
    "dividend_yield": ("Dividend yield", "sec_avg_div"),
}


def search(term: str, limit: int = 20) -> list[dict]:
    """Ticker-prefix and company-name search, best match first.

    The CASE in the ORDER BY ranks an exact ticker hit above a prefix
    hit above a name match, so typing "AA" puts AA before AAPL before
    "Advance Auto Parts".
    """
    like = f"%{term.strip()}%"
    prefix = f"{term.strip()}%"
    return mysql.query(
        """
        SELECT stock_id, ticker, company_name, sector_name, market_cap,
               last_close, pe_ratio, dividend_yield, ret_1y
          FROM v_stock_metrics
         WHERE ticker LIKE :prefix
            OR company_name LIKE :like
         ORDER BY CASE
                    WHEN ticker = :exact  THEN 0
                    WHEN ticker LIKE :prefix THEN 1
                    WHEN company_name LIKE :prefix THEN 2
                    ELSE 3
                  END,
                  market_cap DESC
         LIMIT :limit
        """,
        {"like": like, "prefix": prefix, "exact": term.strip().upper(),
         "limit": limit},
    )


def detail(ticker: str) -> dict | None:
    """Everything the stock page needs, in three round trips."""
    row = mysql.query_one(
        """
        SELECT sc.*, m.company_name AS name, m.eps, m.ebitda, m.week52_low,
               m.week52_high, m.as_of_date, m.last_price_date, m.snapshot_price,
               m.sec_filings_url, m.ebitda_to_mktcap, m.ret_1m, m.ret_3m, m.ret_6m
          FROM v_stock_scores_total sc
          JOIN v_stock_metrics m ON m.stock_id = sc.stock_id
         WHERE sc.ticker = :t
        """,
        {"t": ticker.strip().upper()},
    )
    if row is None:
        return None

    sector = mysql.query_one(
        "SELECT * FROM v_sector_averages WHERE sector_name = :s",
        {"s": row["sector_name"]},
    )

    # Where does this stock sit inside its own sector?
    rank = mysql.query_one(
        """
        WITH ranked AS (
            SELECT ticker,
                   RANK() OVER (ORDER BY total_score DESC) AS rnk,
                   COUNT(*) OVER ()                        AS n
              FROM v_stock_scores_total
             WHERE sector_name = :s
        )
        SELECT rnk, n FROM ranked WHERE ticker = :t
        """,
        {"s": row["sector_name"], "t": row["ticker"]},
    )

    return {
        "stock": row,
        "sector_averages": sector,
        "sector_rank": rank,
        "comparisons": _comparisons(row),
    }


def _comparisons(row: dict) -> list[dict]:
    """Turn raw ratios into 'cheaper/richer than the sector' statements."""
    out = []
    for key, (label, peer_key) in METRIC_LABELS.items():
        value, peer = row.get(key), row.get(peer_key)
        if value in (None, 0) or peer in (None, 0):
            continue
        delta = (value - peer) / peer
        lower_better = key in LOWER_IS_BETTER
        favourable = (delta < 0) if lower_better else (delta > 0)
        out.append({
            "metric": label,
            "value": value,
            "sector_average": peer,
            "delta_pct": round(delta * 100, 1),
            "verdict": "better than sector" if favourable else "worse than sector",
            "lower_is_better": lower_better,
        })
    return out


def price_history(ticker: str, days: int = 365) -> list[dict]:
    """Close series plus a 50-day moving average, computed in SQL.

    The window frame does the smoothing server-side so the browser never
    receives more rows than it draws.
    """
    return mysql.query(
        """
        WITH bounded AS (
            SELECT p.price_date, p.close_price, p.volume
              FROM stock_prices p
              JOIN stocks s ON s.stock_id = p.stock_id
             WHERE s.ticker = :t
             ORDER BY p.price_date DESC
             LIMIT :days
        )
        SELECT price_date,
               close_price,
               volume,
               AVG(close_price) OVER (ORDER BY price_date
                                      ROWS BETWEEN 49 PRECEDING AND CURRENT ROW)
                 AS ma50
          FROM bounded
         ORDER BY price_date
        """,
        {"t": ticker.strip().upper(), "days": days},
    )


def sector_overview() -> list[dict]:
    return mysql.query(
        """
        SELECT sa.*,
               ROUND(AVG(sc.total_score), 2) AS avg_score
          FROM v_sector_averages sa
          LEFT JOIN v_stock_scores_total sc ON sc.sector_name = sa.sector_name
         GROUP BY sa.sector_id, sa.sector_name, sa.company_count, sa.avg_pe,
                  sa.avg_ps, sa.avg_pb, sa.avg_div_yield, sa.avg_earnings_yield,
                  sa.avg_ebitda_to_mktcap, sa.avg_ret_1y, sa.avg_vol_30d,
                  sa.avg_market_cap, sa.total_market_cap
         ORDER BY sa.total_market_cap DESC
        """
    )


def market_movers(limit: int = 10) -> dict:
    """Top gainers and losers over the trailing month."""
    gainers = mysql.query(
        "SELECT ticker, company_name, sector_name, last_close, ret_1m, ret_1y"
        "  FROM v_stock_metrics WHERE ret_1m IS NOT NULL"
        " ORDER BY ret_1m DESC LIMIT :n", {"n": limit})
    losers = mysql.query(
        "SELECT ticker, company_name, sector_name, last_close, ret_1m, ret_1y"
        "  FROM v_stock_metrics WHERE ret_1m IS NOT NULL"
        " ORDER BY ret_1m ASC LIMIT :n", {"n": limit})
    return {"gainers": gainers, "losers": losers}
