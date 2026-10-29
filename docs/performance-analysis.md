# Performance Analysis — MySQL vs MongoDB

Measured on the loaded QuantScore dataset. Reproduce from the **SQL vs NoSQL**
page in the app, or:

```bash
curl "http://127.0.0.1:8000/api/benchmark/run?ticker=AAPL&runs=7&days=2200"
```

## Method

A comparison is only meaningful if both engines answer the *same question*
over the *same rows* with *comparable resources*. Three things had to be
equalised before any number here was worth reporting.

**1. Same data.** `etl/step4_benchmark.py` mirrors each corpus into the other
engine — the news documents into MySQL `bench_news`, the price rows into
MongoDB `bench_prices`. Each engine therefore plays to its strength on one
dataset and against its grain on the other.

**2. Same indexes.** The MySQL index set on `bench_news` mirrors MongoDB's
one-for-one:

| MongoDB | MySQL |
|---|---|
| `{ticker: 1, published_at: -1}` | `idx_bench_ticker_time` |
| `{published_at: -1}` | `idx_bench_time` |
| `{sentiment.label: 1, published_at: -1}` | `idx_bench_sentiment_time` |
| text index on `headline` | `FULLTEXT ftx_bench_headline` |

**3. Same cache.** MongoDB runs with `--wiredTigerCacheSizeGB 1`. MySQL's
default `innodb_buffer_pool_size` is 128 MB, smaller than the working set,
so it was raised to 1 G in `docker-compose.yml`.

**Measurement.** Each scenario runs once to warm the cache, then seven more
times; the median is reported with the standard deviation.

### The two results that changed — and why they matter

Both initial runs looked decisive in MongoDB's favour. Both were measuring
configuration, not database technology.

| Scenario | Unequal indexes | Unequal cache | Equalised | MongoDB |
|---|---|---|---|---|
| Range scan + filter | 236.84 ms | 43.99 ms | **17.22 ms** | 9.57 ms |
| Grouped aggregation | 2470.13 ms | 2365.31 ms | **818.77 ms** | 1509.94 ms |

Adding `(sentiment_label, published_at)` turned a *33× MongoDB win* on the
range scan into a *1.8×* one. Raising the buffer pool to match MongoDB's
cache turned the grouped aggregation from a *1.6× MongoDB win* into a
*1.8× MySQL win* — the result flipped sides.

**This is the most useful finding in the study.** Most published "NoSQL is
faster than SQL" comparisons are measuring an index that was never created
or a cache that was never sized, not the engines.

## Results

Dataset: 325,118 news rows / 325,118 news documents; 698,614 price rows /
400,000 price documents. Median of 7 runs, Windows 11, MySQL 8.4 and
MongoDB 7.0 in Docker, 1 GB cache each.

| Scenario | What it asks | MySQL | MongoDB | Faster |
|---|---|---|---|---|
| Point lookup | 50 newest headlines for one ticker | 13.13 ms | **4.66 ms** | MongoDB 2.8× |
| Range scan + filter | Negative headlines in a date window | 17.22 ms | **9.57 ms** | MongoDB 1.8× |
| Grouped aggregation | Count + mean sentiment per ticker | **818.77 ms** | 1509.94 ms | MySQL 1.8× |
| Time bucketing | Monthly volume and mean sentiment | **375.36 ms** | 544.09 ms | MySQL 1.5× |
| Full-text search | Headlines matching "earnings" | 417.88 ms | **5.33 ms** | MongoDB 78× |
| Time-series scan | Full price history for one ticker | 50.35 ms | **16.80 ms** | MongoDB 3.0× |
| Join vs embedded lookup | Top movers with company + sector | **16.28 ms** | 261.75 ms | MySQL 16× |

**MySQL 3 wins, MongoDB 4 wins.** Total 1,709 ms vs 2,352 ms.

## Interpretation

**Where MongoDB wins.** Point lookups, range scans and time-series scans all
return whole records that MongoDB stores contiguously as one BSON document,
while MySQL assembles a row from a clustered index and projects typed
columns. Real, but modest — 1.8×–3.0× once indexing and cache are equal.

The exception is full-text search at **78×**. MySQL's `MATCH … AGAINST` in
natural-language mode computes a relevance score for every matching row
before applying `LIMIT`; MongoDB's text index streams matches and stops
early. For a headline-search feature this is a genuine architectural
advantage, and it is why the sentiment feed is served from MongoDB.

**Where MySQL wins.** The join scenario is the clearest result in the table
at **16×**. Joining three indexed tables is precisely what a relational
optimiser is built for, while `$lookup` is a per-document nested loop with
no hash-join strategy available. Anything combining entities belongs on the
relational side — which is how the portfolio, holdings and screener features
are built.

Grouped aggregation and time bucketing also go to MySQL once the cache is
sized properly: `GROUP BY` over an indexed column into a temporary table
beats `$group` streaming through documents, and `DATE_FORMAT` is cheaper
than `$dateTrunc` at this scale.

**What the index is worth.** The same point lookup, with every index on
`bench_news` hidden from the optimiser:

| | Median |
|---|---|
| With indexes | 11.47 ms |
| Forced full scan | 185.08 ms |
| **Speed-up** | **16.1×** |

`EXPLAIN` on the indexed version reports `type=ref`,
`key=idx_bench_ticker_time`, `rows=942`, `Extra=Backward index scan` — the
optimiser walks the composite index backwards and never touches the other
324,000 rows. Hiding the indexes forces a scan of all of them.

## Conclusion for the architecture

The measurements support the split the application actually uses:

| Data | Store | Evidence |
|---|---|---|
| Users, portfolios, trades | MySQL | Needs ACID; joins win 16× |
| Companies, fundamentals, prices | MySQL | Joins and `GROUP BY`; composite PK gives a 16× index win |
| News headlines + sentiment | MongoDB | Text search 78×, point lookups 2.8× |
| Company profiles | MongoDB | Variable schema — a modelling question, not a speed one |
| Activity logs | MongoDB | TTL expiry, no referential integrity needed |

## Caveats

- Single machine, no network latency, no concurrent load. These are latency
  figures, not throughput under contention.
- Both engines run in Docker on the same host and compete for CPU; a local
  MariaDB install would differ.
- The news corpus covers 2018–2020 (the overlap between the price and news
  datasets), so time bucketing spans about 30 months.
- Absolute numbers move by 20–30% between runs depending on what else the
  machine is doing. The *ordering* of the results is stable; treat the
  millisecond values as indicative.
- 128,707 duplicate headlines were removed at load time (see
  `etl/step3_documents.py`), so these figures are over unique stories.
