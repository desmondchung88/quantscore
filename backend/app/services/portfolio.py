"""Virtual portfolio simulator and risk analytics.

Trade execution is delegated to sp_execute_trade so that the cash check,
the no-short-selling rule and the ledger insert happen inside one
database transaction. The analytics here rebuild the portfolio's daily
value series in SQL and derive the standard risk measures from it.
"""
from __future__ import annotations

import math

from fastapi import HTTPException, status
from sqlalchemy.exc import DBAPIError, OperationalError

from app.config import settings
from app.db import mysql

TRADING_DAYS = 252
RISK_FREE_RATE = 0.02  # annual, used for the Sharpe ratio
BENCHMARK_TICKER = "SPY"


# ---------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------
def list_portfolios(user_id: int) -> list[dict]:
    return mysql.query(
        "SELECT * FROM v_portfolio_summary WHERE user_id = :u ORDER BY portfolio_id",
        {"u": user_id},
    )


def create_portfolio(user_id: int, name: str, initial_cash: float,
                     currency: str = "USD") -> dict:
    if initial_cash <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Initial cash must be positive")
    try:
        pid = mysql.insert_returning_id(
            "INSERT INTO portfolios (user_id, name, initial_cash, cash_balance,"
            " currency_code) VALUES (:u, :n, :c, :c, :cur)",
            {"u": user_id, "n": name.strip(), "c": initial_cash,
             "cur": currency.upper()[:3]},
        )
    except (DBAPIError, OperationalError) as exc:
        if "uq_portfolio_per_user" in str(exc):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "You already have a portfolio with that name")
        raise
    return mysql.query_one(
        "SELECT * FROM v_portfolio_summary WHERE portfolio_id = :p", {"p": pid})


def rename_portfolio(portfolio_id: int, name: str) -> dict:
    mysql.execute("UPDATE portfolios SET name = :n WHERE portfolio_id = :p",
                  {"n": name.strip(), "p": portfolio_id})
    return mysql.query_one(
        "SELECT * FROM v_portfolio_summary WHERE portfolio_id = :p",
        {"p": portfolio_id})


def delete_portfolio(portfolio_id: int) -> None:
    # ON DELETE CASCADE removes the ledger with it.
    mysql.execute("DELETE FROM portfolios WHERE portfolio_id = :p",
                  {"p": portfolio_id})


def holdings(portfolio_id: int) -> list[dict]:
    rows = mysql.query(
        """
        SELECT h.*,
               h.net_quantity * COALESCE(h.last_close, h.avg_cost) AS market_value,
               h.net_quantity * h.avg_cost                         AS cost_basis,
               h.net_quantity * (COALESCE(h.last_close, h.avg_cost) - h.avg_cost)
                 AS unrealised_pnl,
               CASE WHEN h.avg_cost > 0
                    THEN (COALESCE(h.last_close, h.avg_cost) - h.avg_cost) / h.avg_cost
               END AS unrealised_pct,
               sc.total_score, sc.grade
          FROM v_portfolio_holdings h
          LEFT JOIN v_stock_scores_total sc ON sc.stock_id = h.stock_id
         WHERE h.portfolio_id = :p
         ORDER BY market_value DESC
        """,
        {"p": portfolio_id},
    )
    total = sum(r["market_value"] or 0 for r in rows)
    for r in rows:
        r["weight"] = (r["market_value"] / total) if total else 0
    return rows


def transactions(portfolio_id: int, limit: int = 100) -> list[dict]:
    return mysql.query(
        """
        SELECT t.transaction_id, t.transaction_type, t.quantity, t.execution_price,
               t.fees, t.executed_at, s.ticker, s.company_name,
               t.quantity * t.execution_price AS gross_value
          FROM transactions t
          JOIN stocks s ON s.stock_id = t.stock_id
         WHERE t.portfolio_id = :p
         ORDER BY t.executed_at DESC, t.transaction_id DESC
         LIMIT :n
        """,
        {"p": portfolio_id, "n": limit},
    )


def execute_trade(portfolio_id: int, ticker: str, side: str,
                  quantity: float) -> dict:
    """Run the trade through the stored procedure and translate errors.

    The procedure raises SQLSTATE 45000 with a machine-readable prefix;
    those map onto HTTP status codes here.
    """
    try:
        result = mysql.call_trade_procedure(
            portfolio_id, ticker, side, quantity, settings.TRADE_FEE_RATE)
    except (DBAPIError, OperationalError) as exc:
        message = str(exc.orig) if getattr(exc, "orig", None) else str(exc)
        for token, (code, text) in {
            "INSUFFICIENT_CASH": (status.HTTP_409_CONFLICT,
                                  "Not enough cash for this trade"),
            "INSUFFICIENT_HOLDINGS": (status.HTTP_409_CONFLICT,
                                      "You cannot sell more shares than you hold"),
            "UNKNOWN_TICKER": (status.HTTP_404_NOT_FOUND, "Unknown ticker"),
            "NO_PRICE_AVAILABLE": (status.HTTP_409_CONFLICT,
                                   "No price available for that stock"),
            "PORTFOLIO_NOT_FOUND": (status.HTTP_404_NOT_FOUND,
                                    "Portfolio not found"),
            "INVALID_QUANTITY": (status.HTTP_400_BAD_REQUEST, "Invalid quantity"),
            "INVALID_SIDE": (status.HTTP_400_BAD_REQUEST, "Invalid side"),
        }.items():
            if token in message:
                raise HTTPException(code, text)
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Trade rejected by the database")

    summary = mysql.query_one(
        "SELECT * FROM v_portfolio_summary WHERE portfolio_id = :p",
        {"p": portfolio_id})
    return {"trade": result, "portfolio": summary}


# ---------------------------------------------------------------------
# Risk analytics
# ---------------------------------------------------------------------
def value_series(portfolio_id: int, days: int = 365) -> list[dict]:
    """Daily mark-to-market value of the current positions.

    Position quantities are held constant at today's weights and valued
    back through history -- the standard way to show what the portfolio
    you hold now would have done, without replaying every trade.
    """
    return mysql.query(
        """
        WITH pos AS (
            SELECT stock_id, net_quantity
              FROM v_portfolio_holdings
             WHERE portfolio_id = :p
        ),
        window_dates AS (
            SELECT DISTINCT price_date
              FROM stock_prices
             WHERE stock_id IN (SELECT stock_id FROM pos)
             ORDER BY price_date DESC
             LIMIT :days
        )
        SELECT sp.price_date,
               SUM(sp.close_price * pos.net_quantity) AS value
          FROM stock_prices sp
          JOIN pos ON pos.stock_id = sp.stock_id
         WHERE sp.price_date IN (SELECT price_date FROM window_dates)
         GROUP BY sp.price_date
         ORDER BY sp.price_date
        """,
        {"p": portfolio_id, "days": days},
    )


def _returns(values: list[float]) -> list[float]:
    out = []
    for prev, cur in zip(values, values[1:]):
        if prev and prev > 0:
            out.append(cur / prev - 1)
    return out


def _max_drawdown(values: list[float]) -> float:
    peak, worst = float("-inf"), 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, v / peak - 1)
    return worst


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = q * (len(sorted_values) - 1)
    lo, hi = math.floor(idx), math.ceil(idx)
    if lo == hi:
        return sorted_values[int(idx)]
    frac = idx - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def risk_analytics(portfolio_id: int, days: int = 365) -> dict:
    """Volatility, Sharpe, beta, max drawdown, VaR and concentration."""
    series = value_series(portfolio_id, days)
    values = [float(r["value"]) for r in series if r["value"] is not None]
    rets = _returns(values)

    positions = holdings(portfolio_id)
    summary = mysql.query_one(
        "SELECT * FROM v_portfolio_summary WHERE portfolio_id = :p",
        {"p": portfolio_id})

    analytics: dict = {
        "observations": len(rets),
        "start_date": series[0]["price_date"] if series else None,
        "end_date": series[-1]["price_date"] if series else None,
        "summary": summary,
    }

    if len(rets) >= 2:
        mean = sum(rets) / len(rets)
        variance = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        daily_vol = math.sqrt(variance)
        ann_vol = daily_vol * math.sqrt(TRADING_DAYS)
        ann_return = (values[-1] / values[0]) ** (TRADING_DAYS / len(rets)) - 1 \
            if values[0] > 0 else 0.0

        ordered = sorted(rets)
        var95 = _percentile(ordered, 0.05)
        tail = [r for r in ordered if r <= var95]

        analytics.update({
            "period_return": values[-1] / values[0] - 1 if values[0] > 0 else None,
            "annualised_return": ann_return,
            "daily_volatility": daily_vol,
            "annualised_volatility": ann_vol,
            "sharpe_ratio": ((ann_return - RISK_FREE_RATE) / ann_vol)
                            if ann_vol > 0 else None,
            "max_drawdown": _max_drawdown(values),
            "var_95_daily": var95,
            "cvar_95_daily": (sum(tail) / len(tail)) if tail else None,
            "best_day": max(rets),
            "worst_day": min(rets),
            "positive_days_pct": sum(1 for r in rets if r > 0) / len(rets),
        })
        beta, basis = _beta_vs_benchmark(rets, series)
        analytics["beta"] = beta
        analytics["beta_basis"] = basis
    else:
        analytics["note"] = (
            "Not enough overlapping price history to compute risk measures. "
            "Add positions with at least two days of prices."
        )

    analytics["concentration"] = _concentration(positions)
    analytics["sector_allocation"] = _sector_allocation(portfolio_id)
    return analytics


def _beta_vs_benchmark(
    port_returns: list[float], series: list[dict]
) -> tuple[float | None, str | None]:
    """Beta of the portfolio against the market.

    Returns (beta, what it was measured against), so the UI can say which
    benchmark the number refers to instead of implying it is always SPY.
    """
    if not series:
        return None, None
    start, end = series[0]["price_date"], series[-1]["price_date"]

    bench = mysql.query(
        """
        SELECT p.price_date, p.close_price
          FROM stock_prices p
          JOIN stocks s ON s.stock_id = p.stock_id
         WHERE s.ticker = :b AND p.price_date BETWEEN :s AND :e
         ORDER BY p.price_date
        """,
        {"b": BENCHMARK_TICKER, "s": start, "e": end},
    )

    if len(bench) >= len(series) * 0.8:
        bench_returns = _returns([float(r["close_price"]) for r in bench])
        basis = BENCHMARK_TICKER
    else:
        # The datasets hold index *constituents*, so an ETF proxy like SPY
        # is usually absent. Build an equal-weighted market return instead:
        # one LAG per stock, then the cross-sectional mean per day.
        rows = mysql.query(
            """
            WITH daily AS (
                SELECT price_date,
                       close_price / NULLIF(LAG(close_price) OVER (
                           PARTITION BY stock_id ORDER BY price_date), 0) - 1 AS r
                  FROM stock_prices
                 WHERE price_date BETWEEN :s AND :e
            )
            SELECT price_date, AVG(r) AS market_return
              FROM daily
             WHERE r IS NOT NULL
             GROUP BY price_date
             ORDER BY price_date
            """,
            {"s": start, "e": end},
        )
        if len(rows) < 30:
            return None, None
        bench_returns = [float(r["market_return"]) for r in rows]
        basis = "equal-weighted market"

    n = min(len(port_returns), len(bench_returns))
    if n < 2:
        return None, None
    p, m = port_returns[-n:], bench_returns[-n:]

    mean_p, mean_m = sum(p) / n, sum(m) / n
    cov = sum((a - mean_p) * (b - mean_m) for a, b in zip(p, m)) / (n - 1)
    var_m = sum((b - mean_m) ** 2 for b in m) / (n - 1)
    if var_m <= 0:
        return None, basis
    return cov / var_m, basis


def _concentration(positions: list[dict]) -> dict:
    """Herfindahl-Hirschman index over position weights."""
    weights = [p["weight"] for p in positions if p.get("weight")]
    if not weights:
        return {"hhi": None, "largest_position_pct": None, "positions": 0}
    hhi = sum(w * w for w in weights)
    if hhi >= 0.25:
        verdict = "highly concentrated"
    elif hhi >= 0.15:
        verdict = "moderately concentrated"
    else:
        verdict = "well diversified"
    return {
        "hhi": round(hhi, 4),
        "effective_positions": round(1 / hhi, 2) if hhi else None,
        "largest_position_pct": round(max(weights) * 100, 2),
        "positions": len(weights),
        "verdict": verdict,
    }


def _sector_allocation(portfolio_id: int) -> list[dict]:
    return mysql.query(
        """
        SELECT sector_name,
               COUNT(*)                                               AS positions,
               SUM(net_quantity * COALESCE(last_close, avg_cost))     AS market_value
          FROM v_portfolio_holdings
         WHERE portfolio_id = :p
         GROUP BY sector_name
         ORDER BY market_value DESC
        """,
        {"p": portfolio_id},
    )
