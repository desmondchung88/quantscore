"""Step 2 -- load sectors, companies, fundamentals and the OHLCV series.

Sources
-------
constituents-financials_csv.csv   -> sectors, stocks, financial_snapshots
<ticker>.csv (one per company)    -> stock_prices
"""
from __future__ import annotations

import math

import pandas as pd
from common import (CONSTITUENTS_FILE, Timer, banner, find_file, find_price_dir,
                    require)

from app.config import settings
from app.db import mysql

SNAPSHOT_DATE = "2018-02-08"  # documented snapshot date of the Kaggle extract
CHUNK = 20_000

# Source header -> our column name.
CONSTITUENT_COLUMNS = {
    "Symbol": "ticker",
    "Name": "company_name",
    "Sector": "sector",
    "Price": "snapshot_price",
    "Price/Earnings": "pe_ratio",
    "Dividend Yield": "dividend_yield",
    "Earnings/Share": "eps",
    "52 Week Low": "week52_a",
    "52 Week High": "week52_b",
    "Market Cap": "market_cap",
    "EBITDA": "ebitda",
    "Price/Sales": "price_sales_ratio",
    "Price/Book": "price_book_ratio",
    "SEC Filings": "sec_filings_url",
}


def _num(value) -> float | None:
    """Coerce to a finite float or None (NaN, inf and junk all become None)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def _text(value) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    s = str(value).strip()
    return s or None


def register_import(name: str, url: str, version: str, rows: int) -> int:
    return mysql.insert_returning_id(
        "INSERT INTO data_imports (dataset_name, source_url, dataset_version, row_count)"
        " VALUES (:n, :u, :v, :r)"
        " ON DUPLICATE KEY UPDATE row_count = VALUES(row_count),"
        " imported_at = CURRENT_TIMESTAMP, import_id = LAST_INSERT_ID(import_id)",
        {"n": name, "u": url, "v": version, "r": rows},
    )


# ---------------------------------------------------------------------
# Companies + fundamentals
# ---------------------------------------------------------------------
def load_companies() -> dict[str, int]:
    path = require(find_file(CONSTITUENTS_FILE), "the S&P 500 constituents CSV")
    print(f"  constituents file: {path}")

    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in CONSTITUENT_COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(f"constituents CSV is missing columns: {missing}")

    df = df[list(CONSTITUENT_COLUMNS)].rename(columns=CONSTITUENT_COLUMNS)
    df = df.dropna(subset=["ticker"])
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df = df.drop_duplicates(subset=["ticker"], keep="first")
    records = df.to_dict("records")

    import_id = register_import(
        "S&P 500 Companies with Financial Information",
        "https://www.kaggle.com/datasets/franoisgeorgesjulien/"
        "s-and-p-500-companies-with-financial-information",
        SNAPSHOT_DATE,
        len(records),
    )

    with Timer(f"sectors + stocks ({len(records)} companies)"):
        sectors = sorted({_text(r["sector"]) for r in records if _text(r["sector"])})
        mysql.bulk_insert(
            "INSERT IGNORE INTO sectors (sector_name) VALUES (:name)",
            [{"name": s} for s in sectors],
        )
        sector_ids = {
            r["sector_name"]: r["sector_id"]
            for r in mysql.query("SELECT sector_id, sector_name FROM sectors")
        }

        mysql.bulk_insert(
            "INSERT INTO stocks (ticker, company_name, sector_id, sec_filings_url)"
            " VALUES (:ticker, :name, :sector_id, :url)"
            " ON DUPLICATE KEY UPDATE company_name = VALUES(company_name),"
            " sector_id = VALUES(sector_id)",
            [
                {
                    "ticker": r["ticker"][:10],
                    "name": (_text(r["company_name"]) or r["ticker"])[:255],
                    "sector_id": sector_ids.get(_text(r["sector"])),
                    "url": _text(r["sec_filings_url"]),
                }
                for r in records
            ],
        )

    stock_ids = {
        r["ticker"]: r["stock_id"]
        for r in mysql.query("SELECT stock_id, ticker FROM stocks")
    }

    with Timer("financial_snapshots"):
        rows, swapped = [], 0
        for r in records:
            sid = stock_ids.get(r["ticker"])
            if sid is None:
                continue

            # The published extract has the 52-week low and high columns
            # transposed for every row (MMM: "low" 259.77 > "high" 175.49).
            # Order them by value so the CHECK constraint holds and the
            # range-position calculation stays meaningful.
            a, b = _num(r["week52_a"]), _num(r["week52_b"])
            if a is not None and b is not None and a > b:
                a, b = b, a
                swapped += 1

            rows.append({
                "stock_id": sid,
                "import_id": import_id,
                "as_of": SNAPSHOT_DATE,
                "price": _num(r["snapshot_price"]),
                "pe": _num(r["pe_ratio"]),
                "dy": _num(r["dividend_yield"]),
                "eps": _num(r["eps"]),
                "lo": a,
                "hi": b,
                "mc": _num(r["market_cap"]),
                "eb": _num(r["ebitda"]),
                "ps": _num(r["price_sales_ratio"]),
                "pb": _num(r["price_book_ratio"]),
            })

        mysql.bulk_insert(
            "INSERT INTO financial_snapshots"
            " (stock_id, import_id, as_of_date, snapshot_price, pe_ratio,"
            "  dividend_yield, eps, week52_low, week52_high, market_cap, ebitda,"
            "  price_sales_ratio, price_book_ratio)"
            " VALUES (:stock_id, :import_id, :as_of, :price, :pe, :dy, :eps,"
            "         :lo, :hi, :mc, :eb, :ps, :pb)"
            " ON DUPLICATE KEY UPDATE snapshot_price = VALUES(snapshot_price),"
            " pe_ratio = VALUES(pe_ratio), eps = VALUES(eps),"
            " dividend_yield = VALUES(dividend_yield), market_cap = VALUES(market_cap),"
            " ebitda = VALUES(ebitda), price_sales_ratio = VALUES(price_sales_ratio),"
            " price_book_ratio = VALUES(price_book_ratio),"
            " week52_low = VALUES(week52_low), week52_high = VALUES(week52_high)",
            rows,
        )
        print(f"     {len(rows)} snapshots as at {SNAPSHOT_DATE} "
              f"({swapped} rows had 52-week low/high transposed in the source)")

    return stock_ids


# ---------------------------------------------------------------------
# Price time-series
# ---------------------------------------------------------------------
PRICE_COLUMNS = {
    "Date": "d", "Open": "o", "High": "h", "Low": "l",
    "Close": "c", "Adj Close": "ac", "Volume": "v",
}


def register_price_only_tickers(price_dir, stock_ids: dict[str, int]) -> int:
    """Add companies that have prices but are absent from the constituents file.

    The fundamentals extract is a 2018 snapshot of the index while the price
    extract runs to 2023, so the two memberships differ by roughly a hundred
    names in each direction (FB, CELG and CTXS left; CARR, CEG and ENPH
    joined). Registering the price-only tickers means they can still be
    charted, traded and matched to news; they are simply left out of the
    scoring views, because there are no fundamentals to score.
    """
    missing = sorted(
        {p.stem.strip().upper() for p in price_dir.glob("*.csv")} - set(stock_ids)
    )
    if not missing:
        return 0
    mysql.bulk_insert(
        "INSERT IGNORE INTO stocks (ticker, company_name) VALUES (:t, :t)",
        [{"t": t[:10]} for t in missing],
    )
    stock_ids.update({
        r["ticker"]: r["stock_id"]
        for r in mysql.query("SELECT stock_id, ticker FROM stocks")
    })
    return len(missing)


def load_prices(stock_ids: dict[str, int]) -> None:
    price_dir = require(find_price_dir(), "the per-ticker OHLCV directory")
    files = sorted(price_dir.glob("*.csv"))
    print(f"  price directory: {price_dir}  ({len(files)} files)")

    added = register_price_only_tickers(price_dir, stock_ids)
    if added:
        print(f"  registered {added} tickers that have prices but no "
              f"fundamentals (index turnover since the 2018 snapshot)")

    import_id = register_import(
        "S&P 500 Stock Data From Listing Day to 2023",
        "https://www.kaggle.com/datasets/pavankrishnanarne/"
        "s-and-p-500-stock-data-from-listing-day-to-2023",
        f"{settings.PRICE_START_DATE}..{settings.PRICE_END_DATE}",
        0,
    )

    sql = (
        "INSERT IGNORE INTO stock_prices"
        " (stock_id, price_date, import_id, open_price, high_price, low_price,"
        "  close_price, adjusted_close, volume)"
        " VALUES (:stock_id, :d, :imp, :o, :h, :l, :c, :ac, :v)"
    )

    start = pd.Timestamp(settings.PRICE_START_DATE)
    end = pd.Timestamp(settings.PRICE_END_DATE)
    total, dropped = 0, 0
    skipped: list[str] = []
    buffer: list[dict] = []

    with Timer(f"stock_prices {settings.PRICE_START_DATE} .. {settings.PRICE_END_DATE}"):
        for i, path in enumerate(files, 1):
            ticker = path.stem.strip().upper()
            sid = stock_ids.get(ticker)
            if sid is None:
                skipped.append(ticker)
                continue
            try:
                df = pd.read_csv(path, usecols=list(PRICE_COLUMNS),
                                 parse_dates=["Date"])
            except (ValueError, OSError):
                skipped.append(ticker)
                continue

            df = df.rename(columns=PRICE_COLUMNS)
            df = df[(df["d"] >= start) & (df["d"] <= end)].dropna(subset=["c"])
            if df.empty:
                continue

            # A handful of source rows have high < low, which the CHECK
            # constraint rejects. Drop them rather than silently repair.
            bad = (df["h"].notna() & df["l"].notna() & (df["h"] < df["l"]))
            if bad.any():
                dropped += int(bad.sum())
                df = df[~bad]

            df = df.astype(object).where(pd.notnull(df), None)
            for rec in df.to_dict("records"):
                vol = _num(rec["v"])
                buffer.append({
                    "stock_id": sid,
                    "d": rec["d"].date(),
                    "imp": import_id,
                    "o": _num(rec["o"]), "h": _num(rec["h"]), "l": _num(rec["l"]),
                    "c": _num(rec["c"]), "ac": _num(rec["ac"]),
                    "v": None if vol is None else int(vol),
                })

            if len(buffer) >= CHUNK:
                mysql.bulk_insert(sql, buffer)
                total += len(buffer)
                buffer.clear()

            if i % 100 == 0:
                print(f"       {i}/{len(files)} files, {total:,} rows", flush=True)

        if buffer:
            mysql.bulk_insert(sql, buffer)
            total += len(buffer)

    print(f"     {total:,} price rows loaded; {dropped} rows failed the high>=low "
          f"check; {len(skipped)} tickers not in the constituents list")
    mysql.execute("UPDATE data_imports SET row_count = :r WHERE import_id = :i",
                  {"r": total, "i": import_id})


def main() -> None:
    banner("STEP 2  Relational data load")
    stock_ids = load_companies()
    load_prices(stock_ids)

    with Timer("sp_refresh_latest_prices() -- window-function cache rebuild"):
        mysql.execute("CALL sp_refresh_latest_prices()")

    counts = mysql.query_one(
        "SELECT (SELECT COUNT(*) FROM sectors)             AS sectors,"
        "       (SELECT COUNT(*) FROM stocks)              AS stocks,"
        "       (SELECT COUNT(*) FROM financial_snapshots) AS snapshots,"
        "       (SELECT COUNT(*) FROM stock_prices)        AS prices,"
        "       (SELECT COUNT(*) FROM stock_latest_price)  AS cached,"
        "       (SELECT COUNT(*) FROM stocks s"
        "         WHERE EXISTS (SELECT 1 FROM financial_snapshots f"
        "                        WHERE f.stock_id = s.stock_id)"
        "           AND EXISTS (SELECT 1 FROM stock_latest_price l"
        "                        WHERE l.stock_id = s.stock_id)) AS complete"
    )
    print(f"\n  sectors={counts['sectors']}  stocks={counts['stocks']}  "
          f"snapshots={counts['snapshots']}  prices={counts['prices']:,}  "
          f"cached={counts['cached']}")
    print(f"  {counts['complete']} companies have both fundamentals and prices "
          f"and are therefore scored")


if __name__ == "__main__":
    main()
