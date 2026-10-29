# QuantScore — Database Design

## Relational ER diagram

Paste this into any Mermaid renderer (GitHub, VS Code, mermaid.live) for the
diagram, or screenshot it for the report.

```mermaid
erDiagram
    USERS ||--o{ PORTFOLIOS : "owns"
    USERS ||--o{ WATCHLISTS : "owns"
    PORTFOLIOS ||--o{ TRANSACTIONS : "records"
    STOCKS ||--o{ TRANSACTIONS : "traded in"
    SECTORS ||--o{ STOCKS : "classifies"
    STOCKS ||--o{ FINANCIAL_SNAPSHOTS : "has"
    STOCKS ||--o{ STOCK_PRICES : "has"
    STOCKS ||--|| STOCK_LATEST_PRICE : "cached as"
    WATCHLISTS ||--o{ WATCHLIST_STOCKS : "contains"
    STOCKS ||--o{ WATCHLIST_STOCKS : "appears on"
    DATA_IMPORTS ||--o{ STOCK_PRICES : "sourced"
    DATA_IMPORTS ||--o{ FINANCIAL_SNAPSHOTS : "sourced"

    USERS {
        bigint   user_id PK
        varchar  username UK
        varchar  email UK
        varchar  password_hash
        timestamp created_at
    }
    SECTORS {
        int      sector_id PK
        varchar  sector_name UK
    }
    STOCKS {
        bigint   stock_id PK
        varchar  ticker UK
        varchar  company_name
        int      sector_id FK
        text     sec_filings_url
        boolean  is_active
    }
    FINANCIAL_SNAPSHOTS {
        bigint   snapshot_id PK
        bigint   stock_id FK
        bigint   import_id FK
        date     as_of_date
        decimal  snapshot_price
        decimal  pe_ratio
        decimal  eps
        decimal  dividend_yield
        decimal  market_cap
        decimal  ebitda
        decimal  price_sales_ratio
        decimal  price_book_ratio
        decimal  week52_low
        decimal  week52_high
    }
    STOCK_PRICES {
        bigint   stock_id PK_FK
        date     price_date PK
        bigint   import_id FK
        decimal  open_price
        decimal  high_price
        decimal  low_price
        decimal  close_price
        decimal  adjusted_close
        bigint   volume
    }
    STOCK_LATEST_PRICE {
        bigint   stock_id PK_FK
        date     price_date
        decimal  close_price
        decimal  ret_1m
        decimal  ret_3m
        decimal  ret_6m
        decimal  ret_1y
        decimal  vol_30d
    }
    PORTFOLIOS {
        bigint   portfolio_id PK
        bigint   user_id FK
        varchar  name
        decimal  initial_cash
        decimal  cash_balance
        char     currency_code
    }
    TRANSACTIONS {
        bigint   transaction_id PK
        bigint   portfolio_id FK
        bigint   stock_id FK
        enum     transaction_type
        decimal  quantity
        decimal  execution_price
        decimal  fees
        datetime executed_at
    }
    WATCHLISTS {
        bigint   watchlist_id PK
        bigint   user_id FK
        varchar  name
    }
    WATCHLIST_STOCKS {
        bigint   watchlist_id PK_FK
        bigint   stock_id PK_FK
        timestamp added_at
    }
    DATA_IMPORTS {
        bigint   import_id PK
        varchar  dataset_name
        text     source_url
        varchar  dataset_version
        bigint   row_count
        timestamp imported_at
    }
```

### Relationship types present

| Type | Example |
|---|---|
| One-to-many | `users` → `portfolios`, `stocks` → `stock_prices` |
| Many-to-one | `stocks` → `sectors`, `transactions` → `stocks` |
| Many-to-many | `watchlists` ↔ `stocks` through `watchlist_stocks` |
| One-to-one | `stocks` → `stock_latest_price` |

### Delete behaviour, chosen per relationship

| Parent → child | Rule | Why |
|---|---|---|
| `users` → `portfolios`, `watchlists` | CASCADE | A deleted account takes its own data with it |
| `portfolios` → `transactions` | CASCADE | The ledger has no meaning without its portfolio |
| `stocks` → `transactions` | **RESTRICT** | A stock with trade history must not vanish |
| `stocks` → `stock_prices` | CASCADE | Prices belong to the stock |
| `sectors` → `stocks` | SET NULL | A reclassified sector should not delete companies |
| `data_imports` → loaded rows | SET NULL | Deleting the provenance record keeps the data |

---

## Document model (MongoDB)

### `news_articles` — high volume, nested, validated

```json
{
  "_id": ObjectId("…"),
  "ticker": "AAPL",
  "headline": "Apple shares surge after earnings beat estimates",
  "url": "https://www.benzinga.com/…",
  "publisher": "Benzinga Insights",
  "published_at": ISODate("2020-06-05T10:30:54Z"),
  "source": "analyst_ratings",
  "sentiment": {
    "score": 0.6396,
    "label": "positive",
    "terms": ["surge", "beat"]
  }
}
```

Indexes: `{ticker: 1, published_at: -1}`, `{published_at: -1}`,
`{sentiment.label: 1, published_at: -1}`, text index on `headline`.
A `$jsonSchema` validator enforces the required fields and the score range.

### `company_profiles` — variable schema, the reason for a document store

The fields present depend on the sector. The same collection holds:

```json
{ "ticker": "JPM", "sector": "Financials",
  "regulatory": { "basel_tier": "Tier 1", "stress_tested": true,
                  "primary_regulator": "Federal Reserve" },
  "key_metrics": ["net_interest_margin", "tier1_capital_ratio"] }
```

```json
{ "ticker": "PFE", "sector": "Health Care",
  "pipeline": { "phase_3_trials": null, "fda_submissions": null },
  "regulatory": { "primary_regulator": "FDA" } }
```

```json
{ "ticker": "AMT", "sector": "Real Estate",
  "reit": { "is_reit": true, "ffo_payout_ratio": null },
  "key_metrics": ["occupancy_rate", "cap_rate"] }
```

Relationally this needs either a very sparse table or a sector-specific side
table per sector; as documents it needs neither.

### `research_notes` — free-form user content

```json
{ "user_id": 1, "ticker": "XOM", "title": "Cyclical, not structural",
  "body": "Dividend looks attractive but the yield is a function of …",
  "tags": ["dividend", "cyclical"], "rating": 3,
  "price_target": { "low": 78, "high": 102, "currency": "USD" },
  "created_at": ISODate("…"), "updated_at": ISODate("…") }
```

### `activity_logs` — append-only, self-expiring

A TTL index on `created_at` with `expireAfterSeconds: 2592000` removes rows
after 30 days with no housekeeping job.

---

## Division of responsibility

| Data | Store | Reason |
|---|---|---|
| Users, portfolios, trades | MySQL | ACID; money must not be lost or double-spent |
| Companies, fundamentals, prices | MySQL | Fixed schema, heavy joins and aggregates, range scans on a composite key |
| News headlines + sentiment | MongoDB | Millions of documents, nested sub-document, optional fields per source |
| Company profiles | MongoDB | Schema varies by sector |
| Research notes | MongoDB | Free-form, user-defined fields |
| Activity logs | MongoDB | Append-only, TTL expiry, no referential integrity needed |

Two datasets are deliberately mirrored into both engines
(`bench_news` in MySQL, `bench_prices` in MongoDB) so the performance
comparison asks each engine the same question over the same rows.
