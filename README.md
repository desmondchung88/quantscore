# QuantScore — User Manual

**INF2003 Database Systems · Group Project**

A web-based S&P 500 research and investment-support platform built on two
databases: **MySQL/MariaDB** for the transactional and time-series data, and
**MongoDB** for the news, sentiment, company profiles and notes.

| | |
|---|---|
| **Presentation layer** | React 18 + Vite + Recharts |
| **Application layer** | Python 3.11+ / FastAPI (55 endpoints) |
| **Relational DB** | MySQL 8 or MariaDB 10.6+ — 12 tables, 7 views, 2 procedures, 2 triggers |
| **Document DB** | MongoDB 7 — 5 collections with validators, compound, text and TTL indexes |

---

## 1. Prerequisites

| Software | Version | Check with |
|---|---|---|
| Python | 3.11 or newer | `python --version` |
| Node.js | 18 or newer | `node --version` |
| MySQL **or** MariaDB | 8.0 / 10.6+ | `mysql --version` |
| Docker Desktop | any recent | `docker --version` |

Docker is used only to run MongoDB. If you would rather install MongoDB
Community Server directly, see §7.

---

## 2. Get the datasets

Download these three Kaggle datasets and extract them **next to** the
`quantscore` folder (the loader finds them by content, so the default
`archive (3)` / `archive (4)` / `archive (5)` folder names are fine):

1. [S&P 500 Stock Data From Listing Day to 2023](https://www.kaggle.com/datasets/pavankrishnanarne/s-and-p-500-stock-data-from-listing-day-to-2023) — 503 per-ticker OHLCV files
2. [S&P 500 Companies with Financial Information](https://www.kaggle.com/datasets/franoisgeorgesjulien/s-and-p-500-companies-with-financial-information) — `constituents-financials_csv.csv`
3. [Daily Financial News for 6000+ Stocks](https://www.kaggle.com/datasets/miguelaenlle/massive-stock-news-analysis-db-for-nlpbacktests) — three headline CSVs

Expected layout:

```
INF2003 DATABASE/group/
├── archive (3)/           raw_analyst_ratings.csv, raw_partner_headlines.csv, …
├── archive (4)/           constituents-financials_csv.csv
├── archive (5)/           A.csv, AAPL.csv, … (503 files)
└── quantscore/            ← this repository
```

If you put them elsewhere, set `DATA_DIR` in `.env` to that folder.

---

## 3. Configure

```bash
cd quantscore
cp .env.example .env
```

### Choose a relational database

**Default — MySQL in Docker. Nothing to configure.** `docker-compose.yml`
runs MySQL on port 3307, and `.env.example` already points at it:

```
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
MYSQL_USER=root
MYSQL_PASSWORD=quantscore
```

**Alternative — a local MySQL or MariaDB install.** Comment out the `mysql`
service in `docker-compose.yml`, then create an application account:

```bash
mysql -u root -p < backend/sql/00_create_user.sql
```

and set `MYSQL_PORT=3306`, `MYSQL_USER=quantscore`,
`MYSQL_PASSWORD=quantscore` in `.env`.

> **Why a separate account rather than root?** On Windows, MariaDB usually
> configures `root@localhost` to authenticate through Windows SSPI rather
> than with a password. The MariaDB command-line client speaks that
> protocol; the Python driver does not, and fails with
> `(2059, "Authentication plugin 'auth_gssapi_client' not configured")`.
> No password in `.env` fixes that, because root is not using password
> authentication at all. This is why the Docker MySQL is the default.

Generate a real JWT secret before sharing the app:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 4. Install and load

```bash
# 4.1 Start MySQL, MongoDB and mongo-express
docker compose up -d

# 4.2 Python environment
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -r backend/requirements.txt

# 4.3 Build the schema and load every dataset (one command)
python etl/run_all.py
```

`run_all.py` runs five steps and prints what each one did:

| Step | What it does |
|---|---|
| 1 | Creates the database, 12 tables, all constraints and indexes, then the views, triggers and stored procedures |
| 2 | Loads sectors, 500+ companies, fundamentals and ~600k daily price rows, then calls `sp_refresh_latest_prices()` |
| 3 | Scores every headline with the finance lexicon and loads them into MongoDB, plus company profiles and sample notes |
| 4 | Mirrors both datasets into the other engine so the benchmark compares like with like |
| 5 | Creates demo users, a portfolio, a watchlist and a trade history |

The full load takes roughly 10–20 minutes, most of it step 3. To resume after
an interruption: `python etl/run_all.py --from 3`. To re-run one step:
`python etl/run_all.py --only 2`.

---

## 5. Run

Two terminals:

```bash
# Terminal 1 — API on http://127.0.0.1:8000
python backend/run.py
```

```bash
# Terminal 2 — UI on http://localhost:5173
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**.

- Interactive API docs: http://127.0.0.1:8000/docs
- Browse MongoDB: http://localhost:8081
- Demo login: **`demo`** / **`demo1234`**

---

## 6. What to look at

| Page | Feature | Owner |
|---|---|---|
| Stock search | Every ratio shown against its sector average | Desmond |
| QuantScore | Four-factor score with adjustable weights and a full breakdown | Damien |
| Screener | Multi-filter SQL screener with aggregates and side-by-side comparison | Adora |
| Portfolio | Simulated trading with risk analytics (volatility, Sharpe, beta, VaR, drawdown, HHI) | Au Myat |
| Market sentiment | MongoDB aggregation pipelines over the headline corpus | Calson |
| SQL vs NoSQL | Seven timed scenarios across both engines, plus query plans | Team |
| Database design | Live catalogue of tables, keys, indexes, views, triggers and collections | Team |

### Database features worth demonstrating

**Relational**
- Composite primary key `(stock_id, price_date)` acting as the covering index for the time-series
- `CHECK` constraints on prices, quantities, email format and the 52-week range
- `ON DELETE CASCADE` / `RESTRICT` / `SET NULL` used deliberately per relationship
- Many-to-many via `watchlist_stocks`
- Window functions: `LAG`, `ROW_NUMBER`, `RANK`, `PERCENT_RANK`, and `STDDEV_SAMP` over a 30-row moving frame
- CTEs inside `sp_refresh_latest_prices()`
- Seven layered views, each with one responsibility
- Two triggers enforcing rules a `CHECK` cannot express (no short selling, no margin)
- `sp_execute_trade()` — explicit transaction, `SELECT … FOR UPDATE` row lock, `EXIT HANDLER` with `ROLLBACK` and `RESIGNAL`
- `FULLTEXT` index for headline search
- Every query parameterised; identifiers chosen from allow-lists only

**Document**
- `$jsonSchema` validator on `news_articles`
- Compound index `{ticker: 1, published_at: -1}` matching the access pattern
- Text index for search, TTL index for self-expiring activity logs
- Aggregation pipelines: `$group`, `$facet`, `$bucket`, `$dateTrunc`, `$lookup`
- Variable-schema `company_profiles` — sector-dependent fields with no migrations

### Try breaking it

On the Portfolio page:
- **Sell more shares than you own** → `INSUFFICIENT_HOLDINGS`, rolled back by the trigger
- **Buy beyond your cash balance** → `INSUFFICIENT_CASH`, rolled back
- **Buy an unknown ticker** → `UNKNOWN_TICKER`

In all three cases nothing is written and the cash balance is untouched — the
procedure's `EXIT HANDLER` rolls the whole transaction back.

---

## 7. Alternatives and troubleshooting

**MongoDB without Docker.** Install MongoDB Community Server, let it run as a
service on port 27017, and leave `MONGO_URI=mongodb://localhost:27017`.

**MySQL without a local install.** Uncomment the `mysql` service in
`docker-compose.yml`, run `docker compose up -d`, then set `MYSQL_PORT=3307`
and `MYSQL_PASSWORD=quantscore` in `.env`.

| Symptom | Cause and fix |
|---|---|
| `(2059) Authentication plugin 'auth_gssapi_client' not configured` | Root uses Windows SSPI, not a password. Run `backend/sql/00_create_user.sql` and use the `quantscore` account (see §3) |
| `Access denied for user 'root'` | `MYSQL_PASSWORD` in `.env` is wrong |
| `Cannot reach MongoDB` | `docker compose up -d`, then `docker compose ps` |
| `could not locate …` during the ETL | Datasets not extracted, or `DATA_DIR` points at the wrong folder |
| Sidebar shows "MySQL down" | The API cannot reach the database — check `.env` and the service |
| Benchmark scenarios error | Step 4 has not run: `python etl/run_all.py --only 4` |
| UI loads but every panel is empty | Steps 2–3 have not run |

**Reset everything:**

```bash
docker compose down -v
python etl/run_all.py
```

---

## 8. Repository layout

```
quantscore/
├── backend/
│   ├── sql/
│   │   ├── 01_schema.sql        tables, constraints, indexes
│   │   └── 02_programs.sql      views, triggers, stored procedures
│   ├── app/
│   │   ├── config.py            environment configuration
│   │   ├── main.py              FastAPI application
│   │   ├── schemas.py           request validation
│   │   ├── core/security.py     bcrypt hashing, JWT, authorisation
│   │   ├── db/mysql.py          parameterised SQL access, DDL runner
│   │   ├── db/mongo.py          collections, validators, indexes
│   │   ├── services/            the five features + benchmark harness
│   │   └── routers/             HTTP endpoints
│   └── run.py                   dev server
├── etl/
│   ├── run_all.py               orchestrator
│   ├── step1_schema.py … step5_seed.py
│   └── common.py                dataset discovery
├── frontend/
│   └── src/{pages,components,lib}
├── docker-compose.yml
├── .env.example
└── README.md
```
