"""The QuantScore multi-factor framework.

The four sub-scores live in v_stock_scores (see sql/02_programs.sql) so
the arithmetic is auditable in the database itself. This module adds the
parts that belong in the application: user-supplied factor weights,
ranking, and the explanation payload that makes the score transparent
rather than a black box.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.db import mysql

DEFAULT_WEIGHTS = {
    "valuation": 0.30,
    "profitability": 0.25,
    "growth": 0.25,
    "dividend": 0.20,
}

FACTOR_COLUMNS = {
    "valuation": "valuation_score",
    "profitability": "profitability_score",
    "growth": "growth_score",
    "dividend": "dividend_score",
}

FACTOR_INPUTS = {
    "valuation": ["pe_ratio", "price_sales_ratio", "price_book_ratio"],
    "profitability": ["earnings_yield", "ebitda_to_mktcap"],
    "growth": ["ret_1y", "range_position"],
    "dividend": ["dividend_yield"],
}


@dataclass(frozen=True)
class Weights:
    valuation: float = DEFAULT_WEIGHTS["valuation"]
    profitability: float = DEFAULT_WEIGHTS["profitability"]
    growth: float = DEFAULT_WEIGHTS["growth"]
    dividend: float = DEFAULT_WEIGHTS["dividend"]

    @classmethod
    def normalised(cls, **kwargs) -> "Weights":
        """Accept any positive weights and rescale them to sum to 1."""
        values = {k: float(v) for k, v in kwargs.items()
                  if v is not None and k in DEFAULT_WEIGHTS}
        merged = {**DEFAULT_WEIGHTS, **values}
        merged = {k: max(0.0, v) for k, v in merged.items()}
        total = sum(merged.values())
        if total <= 0:
            return cls()
        return cls(**{k: v / total for k, v in merged.items()})

    def as_dict(self) -> dict[str, float]:
        return {
            "valuation": self.valuation,
            "profitability": self.profitability,
            "growth": self.growth,
            "dividend": self.dividend,
        }

    def sql_expression(self) -> str:
        """The weighted sum, inlined as literal floats.

        The values are produced by normalised() from floats we have
        already coerced and clamped, so they cannot carry SQL text.
        """
        return " + ".join(
            f"{FACTOR_COLUMNS[name]} * {weight:.6f}"
            for name, weight in self.as_dict().items()
        )


def leaderboard(
    weights: Weights,
    sector: str | None = None,
    min_market_cap: float = 0,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Rank the universe under a caller-supplied weighting."""
    expr = weights.sql_expression()
    params: dict = {"cap": min_market_cap, "limit": limit, "offset": offset}

    where = ["COALESCE(market_cap, 0) >= :cap"]
    if sector:
        where.append("sector_name = :sector")
        params["sector"] = sector
    clause = " AND ".join(where)

    rows = mysql.query(
        f"""
        SELECT ticker, company_name, sector_name, market_cap, last_close,
               pe_ratio, dividend_yield, ret_1y, grade,
               valuation_score, profitability_score, growth_score, dividend_score,
               ROUND({expr}, 2) AS weighted_score,
               RANK() OVER (ORDER BY ({expr}) DESC) AS overall_rank,
               RANK() OVER (PARTITION BY sector_name ORDER BY ({expr}) DESC)
                 AS sector_rank
          FROM v_stock_scores_total
         WHERE {clause}
         ORDER BY weighted_score DESC
         LIMIT :limit OFFSET :offset
        """,
        params,
    )
    total = mysql.query_one(
        f"SELECT COUNT(*) AS n FROM v_stock_scores_total WHERE {clause}", params)

    return {
        "weights": weights.as_dict(),
        "total": total["n"] if total else 0,
        "results": rows,
    }


def explain(ticker: str, weights: Weights) -> dict | None:
    """Full breakdown for one stock: inputs, peer values, contributions."""
    row = mysql.query_one(
        f"""
        SELECT sc.*, ROUND({weights.sql_expression()}, 2) AS weighted_score
          FROM v_stock_scores_total sc
         WHERE sc.ticker = :t
        """,
        {"t": ticker.strip().upper()},
    )
    if row is None:
        return None

    factors = []
    for name, column in FACTOR_COLUMNS.items():
        score = row.get(column) or 0.0
        weight = weights.as_dict()[name]
        factors.append({
            "factor": name,
            "score": round(score, 2),
            "weight": round(weight, 4),
            "contribution": round(score * weight, 2),
            "inputs": {k: row.get(k) for k in FACTOR_INPUTS[name]},
            "interpretation": _interpret(score),
        })

    return {
        "ticker": row["ticker"],
        "company_name": row["company_name"],
        "sector_name": row["sector_name"],
        "sector_peers": row.get("sec_peers"),
        "weighted_score": row["weighted_score"],
        "default_score": row["total_score"],
        "grade": row["grade"],
        "factors": factors,
        "sector_benchmarks": {
            "pe": row.get("sec_avg_pe"),
            "ps": row.get("sec_avg_ps"),
            "pb": row.get("sec_avg_pb"),
            "dividend_yield": row.get("sec_avg_div"),
        },
        "methodology": (
            "Each sub-score compares the company with the mean of its own "
            "sector: 50 is exactly average, above 50 is better than the "
            "sector, below 50 is worse. The headline score is the weighted "
            "sum of the four sub-scores."
        ),
    }


def _interpret(score: float) -> str:
    if score >= 70:
        return "well ahead of the sector"
    if score >= 58:
        return "ahead of the sector"
    if score >= 42:
        return "around the sector average"
    if score >= 30:
        return "behind the sector"
    return "well behind the sector"


def sector_leaderboard(min_market_cap: float = 0) -> list[dict]:
    """Delegates to the stored procedure sp_sector_leaderboard."""
    with mysql.connection() as conn:
        from sqlalchemy import text

        result = conn.execute(text("CALL sp_sector_leaderboard(:cap)"),
                              {"cap": min_market_cap})
        rows = [dict(r) for r in result.mappings().all()]
    return [{k: float(v) if hasattr(v, "quantize") else v for k, v in r.items()}
            for r in rows]


def distribution() -> list[dict]:
    """Score histogram in 10-point buckets -- a CASE-based bucketisation."""
    return mysql.query(
        """
        SELECT bucket, COUNT(*) AS companies
          FROM (
            SELECT CONCAT(FLOOR(total_score / 10) * 10, '-',
                          FLOOR(total_score / 10) * 10 + 9) AS bucket,
                   FLOOR(total_score / 10)                  AS ord
              FROM v_stock_scores_total
             WHERE total_score IS NOT NULL
          ) b
         GROUP BY bucket, ord
         ORDER BY ord
        """
    )
