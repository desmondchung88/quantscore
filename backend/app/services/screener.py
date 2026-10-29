"""SQL-driven stock comparison screener.

Filters are composed into a single parameterised WHERE clause. Column
names and sort directions are only ever chosen from fixed allow-lists,
so no part of the SQL text comes from the request body -- the values all
travel as bound parameters.
"""
from __future__ import annotations

from typing import Any

from app.db import mysql

# ---- allow-listed filter columns -------------------------------------
NUMERIC_FILTERS: dict[str, str] = {
    "market_cap": "market_cap",
    "pe_ratio": "pe_ratio",
    "price_sales_ratio": "price_sales_ratio",
    "price_book_ratio": "price_book_ratio",
    "dividend_yield": "dividend_yield",
    "eps": "eps",
    "ret_1y": "ret_1y",
    "ret_1m": "ret_1m",
    "vol_30d": "vol_30d",
    "last_close": "last_close",
    "total_score": "total_score",
    "valuation_score": "valuation_score",
    "profitability_score": "profitability_score",
    "growth_score": "growth_score",
    "dividend_score": "dividend_score",
}

SORTABLE = {**NUMERIC_FILTERS, "ticker": "ticker",
            "company_name": "company_name", "sector_name": "sector_name"}

SELECT_COLUMNS = """
    stock_id, ticker, company_name, sector_name, market_cap, last_close,
    pe_ratio, price_sales_ratio, price_book_ratio, dividend_yield, eps,
    ret_1m, ret_1y, vol_30d, valuation_score, profitability_score,
    growth_score, dividend_score, total_score, grade
"""


def _build_where(filters: dict[str, Any]) -> tuple[str, dict]:
    clauses: list[str] = []
    params: dict = {}

    for key, column in NUMERIC_FILTERS.items():
        for bound, op in (("min", ">="), ("max", "<=")):
            raw = filters.get(f"{bound}_{key}")
            if raw is None:
                continue
            slot = f"{bound}_{key}"
            clauses.append(f"{column} {op} :{slot}")
            params[slot] = float(raw)

    sectors = filters.get("sectors")
    if sectors:
        slots = []
        for i, s in enumerate(sectors):
            slots.append(f":sector_{i}")
            params[f"sector_{i}"] = s
        clauses.append(f"sector_name IN ({', '.join(slots)})")

    grades = filters.get("grades")
    if grades:
        slots = []
        for i, g in enumerate(grades):
            slots.append(f":grade_{i}")
            params[f"grade_{i}"] = g
        clauses.append(f"grade IN ({', '.join(slots)})")

    search = (filters.get("search") or "").strip()
    if search:
        clauses.append("(ticker LIKE :search OR company_name LIKE :search)")
        params["search"] = f"%{search}%"

    if filters.get("exclude_null_pe"):
        clauses.append("pe_ratio IS NOT NULL AND pe_ratio > 0")

    where = " AND ".join(clauses) if clauses else "1 = 1"
    return where, params


def run(filters: dict[str, Any], sort_by: str = "total_score",
        sort_dir: str = "desc", limit: int = 50, offset: int = 0) -> dict:
    where, params = _build_where(filters)

    column = SORTABLE.get(sort_by, "total_score")
    direction = "ASC" if str(sort_dir).lower() == "asc" else "DESC"
    params.update({"limit": min(int(limit), 500), "offset": max(int(offset), 0)})

    rows = mysql.query(
        f"""
        SELECT {SELECT_COLUMNS}
          FROM v_stock_scores_total
         WHERE {where}
         ORDER BY {column} IS NULL, {column} {direction}, ticker ASC
         LIMIT :limit OFFSET :offset
        """,
        params,
    )

    # Aggregates over the whole filtered set, not just the page.
    stats = mysql.query_one(
        f"""
        SELECT COUNT(*)                     AS matches,
               ROUND(AVG(total_score), 2)   AS avg_score,
               ROUND(AVG(pe_ratio), 2)      AS avg_pe,
               ROUND(AVG(dividend_yield),3) AS avg_dividend_yield,
               ROUND(AVG(ret_1y) * 100, 2)  AS avg_ret_1y_pct,
               SUM(market_cap)              AS total_market_cap,
               COUNT(DISTINCT sector_name)  AS sectors_covered
          FROM v_stock_scores_total
         WHERE {where}
        """,
        params,
    )

    by_sector = mysql.query(
        f"""
        SELECT sector_name,
               COUNT(*)                   AS companies,
               ROUND(AVG(total_score), 2) AS avg_score
          FROM v_stock_scores_total
         WHERE {where}
         GROUP BY sector_name
        HAVING COUNT(*) > 0
         ORDER BY companies DESC
        """,
        params,
    )

    return {"results": rows, "stats": stats, "by_sector": by_sector,
            "sort": {"by": column, "dir": direction.lower()}}


def compare(tickers: list[str]) -> dict:
    """Side-by-side comparison of up to eight tickers.

    Each metric also carries its rank within the selected set, so the
    UI can mark the best cell in every row.
    """
    tickers = [t.strip().upper() for t in tickers if t.strip()][:8]
    if not tickers:
        return {"stocks": [], "sector_averages": []}

    slots = ", ".join(f":t{i}" for i in range(len(tickers)))
    params = {f"t{i}": t for i, t in enumerate(tickers)}

    stocks = mysql.query(
        f"""
        SELECT {SELECT_COLUMNS}, earnings_yield, ebitda_to_mktcap, range_position,
               sec_avg_pe, sec_avg_ps, sec_avg_pb, sec_avg_div
          FROM v_stock_scores_total
         WHERE ticker IN ({slots})
        """,
        params,
    )

    sectors = sorted({s["sector_name"] for s in stocks})
    sector_rows = []
    if sectors:
        s_slots = ", ".join(f":s{i}" for i in range(len(sectors)))
        s_params = {f"s{i}": s for i, s in enumerate(sectors)}
        sector_rows = mysql.query(
            f"SELECT * FROM v_sector_averages WHERE sector_name IN ({s_slots})",
            s_params,
        )

    return {"stocks": stocks, "sector_averages": sector_rows,
            "requested": tickers}


def filter_options() -> dict:
    """Ranges and distinct values the UI needs to build its controls."""
    # Listed from the scored universe so that every sector offered as a
    # filter actually returns rows.
    sectors = mysql.query(
        "SELECT sector_name, COUNT(*) AS companies"
        "  FROM v_stock_scores_total GROUP BY sector_name ORDER BY sector_name")
    bounds = mysql.query_one(
        """
        SELECT MIN(market_cap) AS min_market_cap, MAX(market_cap) AS max_market_cap,
               MIN(pe_ratio)   AS min_pe,         MAX(pe_ratio)   AS max_pe,
               MIN(dividend_yield) AS min_div,    MAX(dividend_yield) AS max_div,
               MIN(ret_1y)     AS min_ret1y,      MAX(ret_1y)     AS max_ret1y
          FROM v_stock_scores_total
        """
    )
    return {"sectors": sectors, "bounds": bounds,
            "grades": ["A", "B", "C", "D", "E"]}
