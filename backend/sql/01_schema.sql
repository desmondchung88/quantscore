-- =====================================================================
--  QuantScore - INF2003 Database Systems
--  Relational schema (MySQL 8 / MariaDB 10.6+)
--
--  Nine core entities + one many-to-many junction table + one
--  benchmark-only table.
--
--  Demonstrates: PK/FK referential integrity, CHECK constraints,
--  UNIQUE constraints, ENUM / DECIMAL / DATE / TIMESTAMP typing,
--  composite primary keys, composite + covering indexes, FULLTEXT
--  indexing, and 1-to-many / many-to-1 / many-to-many relationships.
-- =====================================================================

DROP DATABASE IF EXISTS quantscore;
CREATE DATABASE quantscore
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;
USE quantscore;

-- ---------------------------------------------------------------------
-- 1. data_imports -- provenance for every row loaded from a dataset
-- ---------------------------------------------------------------------
CREATE TABLE data_imports (
    import_id        BIGINT AUTO_INCREMENT PRIMARY KEY,
    dataset_name     VARCHAR(255)  NOT NULL,
    source_url       TEXT          NULL,
    dataset_version  VARCHAR(100)  NOT NULL DEFAULT 'v1',
    row_count        BIGINT        NOT NULL DEFAULT 0,
    imported_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_import UNIQUE (dataset_name, dataset_version),
    CONSTRAINT chk_import_rows CHECK (row_count >= 0)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 2. sectors -- lookup table (1 sector : many stocks)
-- ---------------------------------------------------------------------
CREATE TABLE sectors (
    sector_id    INT AUTO_INCREMENT PRIMARY KEY,
    sector_name  VARCHAR(80) NOT NULL,
    CONSTRAINT uq_sector_name UNIQUE (sector_name)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 3. stocks -- many stocks : 1 sector
-- ---------------------------------------------------------------------
CREATE TABLE stocks (
    stock_id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    ticker           VARCHAR(10)  NOT NULL,
    company_name     VARCHAR(255) NOT NULL,
    sector_id        INT          NULL,
    sec_filings_url  TEXT         NULL,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_stock_ticker UNIQUE (ticker),
    CONSTRAINT fk_stock_sector FOREIGN KEY (sector_id)
        REFERENCES sectors(sector_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT chk_ticker_len CHECK (CHAR_LENGTH(ticker) BETWEEN 1 AND 10)
) ENGINE=InnoDB;

CREATE INDEX idx_stocks_sector ON stocks(sector_id);
CREATE INDEX idx_stocks_name   ON stocks(company_name);

-- ---------------------------------------------------------------------
-- 4. financial_snapshots -- fundamentals as at a dataset snapshot date
--    (many snapshots : 1 stock)
-- ---------------------------------------------------------------------
CREATE TABLE financial_snapshots (
    snapshot_id        BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_id           BIGINT        NOT NULL,
    import_id          BIGINT        NULL,
    as_of_date         DATE          NOT NULL,
    snapshot_price     DECIMAL(20,6) NULL,
    pe_ratio           DECIMAL(20,6) NULL,
    eps                DECIMAL(20,6) NULL,
    dividend_yield     DECIMAL(20,6) NULL,
    market_cap         DECIMAL(24,2) NULL,
    ebitda             DECIMAL(24,2) NULL,
    price_sales_ratio  DECIMAL(20,6) NULL,
    price_book_ratio   DECIMAL(20,6) NULL,
    week52_low         DECIMAL(20,6) NULL,
    week52_high        DECIMAL(20,6) NULL,
    CONSTRAINT uq_snapshot UNIQUE (stock_id, as_of_date),
    CONSTRAINT fk_snap_stock FOREIGN KEY (stock_id)
        REFERENCES stocks(stock_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_snap_import FOREIGN KEY (import_id)
        REFERENCES data_imports(import_id) ON DELETE SET NULL,
    CONSTRAINT chk_snap_mktcap   CHECK (market_cap IS NULL OR market_cap >= 0),
    CONSTRAINT chk_snap_divyield CHECK (dividend_yield IS NULL OR dividend_yield >= 0),
    CONSTRAINT chk_snap_52w      CHECK (week52_low IS NULL OR week52_high IS NULL
                                        OR week52_high >= week52_low)
) ENGINE=InnoDB;

CREATE INDEX idx_snap_date   ON financial_snapshots(as_of_date);
CREATE INDEX idx_snap_pe     ON financial_snapshots(pe_ratio);
CREATE INDEX idx_snap_mktcap ON financial_snapshots(market_cap);

-- ---------------------------------------------------------------------
-- 5. stock_prices -- daily OHLCV time-series.
--    The composite PK (stock_id, price_date) is the clustered covering
--    index for every "one stock over a date range" query.
-- ---------------------------------------------------------------------
CREATE TABLE stock_prices (
    stock_id        BIGINT        NOT NULL,
    price_date      DATE          NOT NULL,
    import_id       BIGINT        NULL,
    open_price      DECIMAL(20,6) NULL,
    high_price      DECIMAL(20,6) NULL,
    low_price       DECIMAL(20,6) NULL,
    close_price     DECIMAL(20,6) NOT NULL,
    adjusted_close  DECIMAL(20,6) NULL,
    volume          BIGINT        NULL,
    PRIMARY KEY (stock_id, price_date),
    CONSTRAINT fk_price_stock FOREIGN KEY (stock_id)
        REFERENCES stocks(stock_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_price_import FOREIGN KEY (import_id)
        REFERENCES data_imports(import_id) ON DELETE SET NULL,
    CONSTRAINT chk_price_pos CHECK (close_price >= 0),
    CONSTRAINT chk_price_vol CHECK (volume IS NULL OR volume >= 0),
    CONSTRAINT chk_price_hl  CHECK (high_price IS NULL OR low_price IS NULL
                                    OR high_price >= low_price)
) ENGINE=InnoDB;

-- Secondary index for "whole market on one day" scans (sector heatmap,
-- benchmark queries). The PK already covers the per-stock access path.
CREATE INDEX idx_prices_date ON stock_prices(price_date, stock_id);

-- ---------------------------------------------------------------------
-- 6. users
-- ---------------------------------------------------------------------
CREATE TABLE users (
    user_id        BIGINT AUTO_INCREMENT PRIMARY KEY,
    username       VARCHAR(50)  NOT NULL,
    email          VARCHAR(254) NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    created_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_username UNIQUE (username),
    CONSTRAINT uq_email    UNIQUE (email),
    CONSTRAINT chk_email   CHECK (email LIKE '%_@_%._%'),
    CONSTRAINT chk_uname   CHECK (CHAR_LENGTH(username) >= 3)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 7. portfolios -- many portfolios : 1 user.
--    cash_balance is maintained transactionally by sp_execute_trade.
-- ---------------------------------------------------------------------
CREATE TABLE portfolios (
    portfolio_id   BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id        BIGINT        NOT NULL,
    name           VARCHAR(100)  NOT NULL,
    initial_cash   DECIMAL(20,2) NOT NULL DEFAULT 100000.00,
    cash_balance   DECIMAL(20,2) NOT NULL DEFAULT 100000.00,
    currency_code  CHAR(3)       NOT NULL DEFAULT 'USD',
    created_at     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_portfolio_per_user UNIQUE (user_id, name),
    CONSTRAINT fk_portfolio_user FOREIGN KEY (user_id)
        REFERENCES users(user_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_initial_cash CHECK (initial_cash > 0),
    CONSTRAINT chk_cash_nonneg  CHECK (cash_balance >= 0)
) ENGINE=InnoDB;

CREATE INDEX idx_portfolio_user ON portfolios(user_id);

-- ---------------------------------------------------------------------
-- 8. transactions -- the simulated BUY/SELL ledger.
--    many transactions : 1 portfolio, many transactions : 1 stock
-- ---------------------------------------------------------------------
CREATE TABLE transactions (
    transaction_id    BIGINT AUTO_INCREMENT PRIMARY KEY,
    portfolio_id      BIGINT        NOT NULL,
    stock_id          BIGINT        NOT NULL,
    transaction_type  ENUM('BUY','SELL') NOT NULL,
    quantity          DECIMAL(20,6) NOT NULL,
    execution_price   DECIMAL(20,6) NOT NULL,
    fees              DECIMAL(20,6) NOT NULL DEFAULT 0,
    executed_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_txn_portfolio FOREIGN KEY (portfolio_id)
        REFERENCES portfolios(portfolio_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_txn_stock FOREIGN KEY (stock_id)
        REFERENCES stocks(stock_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT chk_txn_qty   CHECK (quantity > 0),
    CONSTRAINT chk_txn_price CHECK (execution_price >= 0),
    CONSTRAINT chk_txn_fees  CHECK (fees >= 0)
) ENGINE=InnoDB;

CREATE INDEX idx_txn_portfolio_time  ON transactions(portfolio_id, executed_at);
CREATE INDEX idx_txn_portfolio_stock ON transactions(portfolio_id, stock_id);

-- ---------------------------------------------------------------------
-- 9. watchlists -- many watchlists : 1 user
-- ---------------------------------------------------------------------
CREATE TABLE watchlists (
    watchlist_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id       BIGINT       NOT NULL,
    name          VARCHAR(100) NOT NULL,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_watchlist_per_user UNIQUE (user_id, name),
    CONSTRAINT fk_watchlist_user FOREIGN KEY (user_id)
        REFERENCES users(user_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 10. watchlist_stocks -- MANY-TO-MANY junction (watchlists <-> stocks)
-- ---------------------------------------------------------------------
CREATE TABLE watchlist_stocks (
    watchlist_id  BIGINT    NOT NULL,
    stock_id      BIGINT    NOT NULL,
    added_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (watchlist_id, stock_id),
    CONSTRAINT fk_ws_watchlist FOREIGN KEY (watchlist_id)
        REFERENCES watchlists(watchlist_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_ws_stock FOREIGN KEY (stock_id)
        REFERENCES stocks(stock_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE INDEX idx_ws_stock ON watchlist_stocks(stock_id);

-- ---------------------------------------------------------------------
-- 11. stock_latest_price -- materialised-view pattern.
--     Rebuilt by sp_refresh_latest_prices() with window functions so
--     that the dashboard, screener and scoring views never have to
--     scan the 600k-row time-series.
-- ---------------------------------------------------------------------
CREATE TABLE stock_latest_price (
    stock_id     BIGINT        NOT NULL PRIMARY KEY,
    price_date   DATE          NOT NULL,
    close_price  DECIMAL(20,6) NOT NULL,
    volume       BIGINT        NULL,
    close_1m     DECIMAL(20,6) NULL,
    close_3m     DECIMAL(20,6) NULL,
    close_6m     DECIMAL(20,6) NULL,
    close_1y     DECIMAL(20,6) NULL,
    ret_1m       DECIMAL(12,6) NULL,
    ret_3m       DECIMAL(12,6) NULL,
    ret_6m       DECIMAL(12,6) NULL,
    ret_1y       DECIMAL(12,6) NULL,
    vol_30d      DECIMAL(12,6) NULL,
    refreshed_at TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_slp_stock FOREIGN KEY (stock_id)
        REFERENCES stocks(stock_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE INDEX idx_slp_ret1y ON stock_latest_price(ret_1y);

-- ---------------------------------------------------------------------
-- 12. bench_news -- SQL-side mirror of the MongoDB news corpus.
--     Used ONLY by the SQL-vs-NoSQL performance study, so that both
--     engines answer identical questions over identical data.
-- ---------------------------------------------------------------------
CREATE TABLE bench_news (
    news_id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    ticker           VARCHAR(10)   NOT NULL,
    headline         VARCHAR(512)  NOT NULL,
    publisher        VARCHAR(120)  NULL,
    published_at     DATETIME      NOT NULL,
    sentiment        DECIMAL(6,4)  NOT NULL DEFAULT 0,
    sentiment_label  ENUM('positive','neutral','negative') NOT NULL DEFAULT 'neutral',
    CONSTRAINT chk_bench_sent CHECK (sentiment BETWEEN -1 AND 1)
) ENGINE=InnoDB;

-- These deliberately mirror the MongoDB index set one-for-one
--   {ticker:1, published_at:-1}        -> idx_bench_ticker_time
--   {published_at:-1}                  -> idx_bench_time
--   {sentiment.label:1, published_at:-1} -> idx_bench_sentiment_time
--   text index on headline             -> ftx_bench_headline
-- so the performance study compares the engines, not the indexing.
CREATE INDEX idx_bench_ticker_time    ON bench_news(ticker, published_at);
CREATE INDEX idx_bench_time           ON bench_news(published_at);
CREATE INDEX idx_bench_sentiment_time ON bench_news(sentiment_label, published_at);
CREATE FULLTEXT INDEX ftx_bench_headline ON bench_news(headline);
