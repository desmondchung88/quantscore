"""Step 3 -- load the document store.

news_articles     headlines from three Kaggle news extracts, each scored
                  by the application's finance sentiment lexicon.
company_profiles  variable-schema company metadata; the fields present
                  depend on the sector, which is exactly the case for a
                  schemaless store.
research_notes    seeded with a few example notes (full CRUD lives in
                  the API).
"""
from __future__ import annotations

import hashlib

import pandas as pd
from common import NEWS_FILES, Timer, banner, find_file
from pymongo.errors import BulkWriteError

from app.config import settings
from app.db import mongo, mysql
from app.services import sentiment

CHUNK = 200_000
INSERT_BATCH = 5_000

NEWS_SOURCES = {
    "raw_analyst_ratings.csv": ("headline", "analyst_ratings"),
    "raw_partner_headlines.csv": ("headline", "partner_headlines"),
    "analyst_ratings_processed.csv": ("title", "analyst_ratings_processed"),
}

# Sector-specific fields -- the reason this collection is not a SQL table.
SECTOR_PROFILE_EXTRAS = {
    "Financials": {
        "regulatory": {"basel_tier": "Tier 1", "stress_tested": True,
                       "primary_regulator": "Federal Reserve"},
        "key_metrics": ["net_interest_margin", "tier1_capital_ratio",
                        "loan_loss_provision"],
    },
    "Health Care": {
        "pipeline": {"phase_3_trials": None, "fda_submissions": None},
        "key_metrics": ["rnd_intensity", "patent_cliff_year"],
        "regulatory": {"primary_regulator": "FDA"},
    },
    "Energy": {
        "reserves": {"proven_boe": None, "reserve_life_years": None},
        "key_metrics": ["breakeven_oil_price", "refining_margin"],
        "esg": {"carbon_intensity_scope1": None},
    },
    "Information Technology": {
        "key_metrics": ["rnd_intensity", "arr_growth", "gross_margin"],
        "business_model": {"recurring_revenue": True},
    },
    "Real Estate": {
        "reit": {"is_reit": True, "ffo_payout_ratio": None},
        "key_metrics": ["occupancy_rate", "cap_rate"],
    },
    "Utilities": {
        "regulatory": {"rate_regulated": True, "primary_regulator": "FERC"},
        "key_metrics": ["allowed_roe", "rate_base_growth"],
    },
}


def _resolve_tickers() -> set[str]:
    return {
        r["ticker"] for r in mysql.query("SELECT ticker FROM stocks")
    }


def _dedupe_id(ticker: str, headline: str, published) -> str:
    """Deterministic _id so re-posted stories collapse to one document.

    The three source files overlap heavily: analyst_ratings_processed is
    largely raw_analyst_ratings with the publisher and url columns
    dropped and the seconds zeroed, so an exact-timestamp key would miss
    the duplicates. Keying on ticker + normalised headline + calendar day
    catches them, and also collapses the same story syndicated to several
    publishers on the same day -- which matters, because otherwise one
    story would be counted several times in the sentiment averages.

    Using it as _id means MongoDB enforces the rule; the loader does not
    have to hold a seen-set of half a million hashes in memory.
    """
    key = f"{ticker}|{' '.join(headline.lower().split())}|{published.date().isoformat()}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------
# news_articles
# ---------------------------------------------------------------------
def load_news(tickers: set[str]) -> int:
    db = mongo.get_db()
    coll = db[mongo.NEWS]
    coll.delete_many({})

    start = pd.Timestamp(settings.PRICE_START_DATE)
    end = pd.Timestamp(settings.PRICE_END_DATE) + pd.Timedelta(days=1)
    budget = settings.NEWS_MAX_ROWS
    inserted = 0
    total_dupes = 0

    for filename in NEWS_FILES:
        if inserted >= budget:
            break
        path = find_file(filename)
        if path is None:
            print(f"     (skipping {filename} -- not found)")
            continue

        text_col, source = NEWS_SOURCES[filename]
        has_url = filename != "analyst_ratings_processed.csv"
        usecols = [text_col, "date", "stock"] + (["url", "publisher"] if has_url else [])

        with Timer(f"{filename} -> news_articles"):
            buffer: list[dict] = []
            file_rows = 0
            file_dupes = 0

            reader = pd.read_csv(
                path, usecols=usecols, chunksize=CHUNK,
                dtype=str, on_bad_lines="skip",
            )
            for chunk in reader:
                if inserted >= budget:
                    break

                chunk = chunk.dropna(subset=["stock", text_col, "date"])
                chunk["stock"] = chunk["stock"].str.strip().str.upper()
                chunk = chunk[chunk["stock"].isin(tickers)]
                if chunk.empty:
                    continue

                ts = pd.to_datetime(chunk["date"], format="mixed", utc=True,
                                    errors="coerce")
                chunk = chunk.assign(_ts=ts.dt.tz_localize(None))
                chunk = chunk[chunk["_ts"].notna()]
                chunk = chunk[(chunk["_ts"] >= start) & (chunk["_ts"] < end)]
                if chunk.empty:
                    continue

                for rec in chunk.to_dict("records"):
                    headline = str(rec[text_col]).strip()[:500]
                    if not headline:
                        continue
                    score, label, terms = sentiment.score_text(headline)
                    buffer.append({
                        "_id": _dedupe_id(rec["stock"], headline, rec["_ts"]),
                        "ticker": rec["stock"],
                        "headline": headline,
                        "url": (str(rec["url"]) if has_url and rec.get("url") else None),
                        "publisher": (str(rec["publisher"])[:120]
                                      if has_url and rec.get("publisher") else None),
                        "published_at": rec["_ts"].to_pydatetime(),
                        "source": source,
                        "sentiment": {"score": float(score), "label": label,
                                      "terms": terms},
                    })

                    if len(buffer) >= INSERT_BATCH:
                        new, dupes = _insert_batch(coll, buffer)
                        inserted += new
                        file_rows += new
                        file_dupes += dupes
                        buffer.clear()
                        if inserted % 100_000 < INSERT_BATCH:
                            print(f"       {inserted:,} documents", flush=True)
                        if inserted >= budget:
                            break

            if buffer:
                new, dupes = _insert_batch(coll, buffer)
                inserted += new
                file_rows += new
                file_dupes += dupes
            print(f"     {file_rows:,} new documents, "
                  f"{file_dupes:,} duplicates of stories already loaded")
            total_dupes += file_dupes

    print(f"     {total_dupes:,} duplicate headlines collapsed in total")
    return inserted


def _insert_batch(coll, docs: list[dict]) -> tuple[int, int]:
    """Insert, treating duplicate _id as "already have it", not an error."""
    try:
        result = coll.insert_many(docs, ordered=False)
        return len(result.inserted_ids), 0
    except BulkWriteError as exc:
        errors = exc.details.get("writeErrors", [])
        duplicates = sum(1 for e in errors if e.get("code") == 11000)
        other = [e for e in errors if e.get("code") != 11000]
        if other:
            raise RuntimeError(
                f"{len(other)} non-duplicate write errors, first: "
                f"{other[0].get('errmsg', '')[:200]}"
            ) from exc
        return len(docs) - len(errors), duplicates


# ---------------------------------------------------------------------
# company_profiles
# ---------------------------------------------------------------------
def load_profiles() -> int:
    db = mongo.get_db()
    coll = db[mongo.PROFILES]
    coll.delete_many({})

    rows = mysql.query(
        "SELECT s.ticker, s.company_name, s.sec_filings_url,"
        "       COALESCE(sec.sector_name,'Unclassified') AS sector,"
        "       fs.market_cap, fs.ebitda, fs.dividend_yield, fs.pe_ratio"
        "  FROM stocks s"
        "  LEFT JOIN sectors sec ON sec.sector_id = s.sector_id"
        "  LEFT JOIN financial_snapshots fs ON fs.stock_id = s.stock_id"
    )

    docs = []
    for r in rows:
        cap = r.get("market_cap") or 0
        tags = [r["sector"].lower().replace(" ", "-")]
        if cap >= 200e9:
            tags.append("mega-cap")
        elif cap >= 10e9:
            tags.append("large-cap")
        else:
            tags.append("mid-cap")
        if (r.get("dividend_yield") or 0) >= 3:
            tags.append("high-yield")
        if (r.get("pe_ratio") or 0) > 40:
            tags.append("high-multiple")

        doc = {
            "ticker": r["ticker"],
            "company_name": r["company_name"],
            "sector": r["sector"],
            "tags": tags,
            "links": {"sec_filings": r.get("sec_filings_url")},
            "size": {"market_cap": cap, "ebitda": r.get("ebitda")},
            "profile_version": 1,
        }
        doc.update(SECTOR_PROFILE_EXTRAS.get(r["sector"], {}))
        docs.append(doc)

    if docs:
        coll.insert_many(docs, ordered=False)
    return len(docs)


def seed_notes() -> int:
    db = mongo.get_db()
    coll = db[mongo.NOTES]
    coll.delete_many({})
    from datetime import datetime

    now = datetime.utcnow()
    samples = [
        {"user_id": 1, "ticker": "AAPL", "title": "Services mix",
         "body": "Watching the services revenue share; gross margin leverage "
                 "is the whole thesis here.",
         "tags": ["thesis", "margins"], "rating": 4},
        {"user_id": 1, "ticker": "XOM", "title": "Cyclical, not structural",
         "body": "Dividend looks attractive but the yield is a function of "
                 "where we are in the oil cycle.",
         "tags": ["dividend", "cyclical"], "rating": 3,
         "price_target": {"low": 78, "high": 102, "currency": "USD"}},
        {"user_id": 1, "ticker": "NVDA", "title": "Valuation check",
         "body": "Growth score is excellent, valuation score is poor. "
                 "Classic momentum versus multiple trade-off.",
         "tags": ["valuation", "momentum"], "rating": 4},
    ]
    for s in samples:
        s["created_at"] = now
        s["updated_at"] = now
    coll.insert_many(samples)
    return len(samples)


def main() -> None:
    banner("STEP 3  Document store load")
    if not mongo.ping():
        raise SystemExit(
            f"Cannot reach MongoDB at {settings.MONGO_URI}.\n"
            "Start it with:  docker compose up -d mongo"
        )

    with Timer("collections, validators and indexes"):
        mongo.ensure_collections()

    tickers = _resolve_tickers()
    if not tickers:
        raise SystemExit("No stocks in MySQL -- run step2_relational.py first.")

    n_news = load_news(tickers)

    with Timer("company_profiles"):
        n_profiles = load_profiles()
    with Timer("research_notes (samples)"):
        n_notes = seed_notes()

    db = mongo.get_db()
    print(f"\n  news_articles={db[mongo.NEWS].estimated_document_count():,}  "
          f"company_profiles={n_profiles}  research_notes={n_notes}")

    if n_news:
        agg = list(db[mongo.NEWS].aggregate([
            {"$group": {"_id": "$sentiment.label", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
        ]))
        spread = "  ".join(f"{a['_id']}={a['n']:,}" for a in agg)
        print(f"  sentiment spread: {spread}")


if __name__ == "__main__":
    main()
