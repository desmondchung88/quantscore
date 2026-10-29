-- =====================================================================
--  QuantScore - views, triggers and stored programs
--
--  Demonstrates: window functions (ROW_NUMBER, LAG, STDDEV_SAMP over a
--  moving frame, AVG OVER PARTITION), common table expressions, layered
--  views, non-standard integrity constraints enforced by triggers, and
--  an ACID stored procedure with explicit row locking and rollback.
-- =====================================================================

USE quantscore;

-- =====================================================================
--  A.  MATERIALISED-VIEW REFRESH
--      One pass over stock_prices computes, per stock: the latest bar,
--      the close 1/3/6/12 months back (LAG over trading days), and the
--      30-day realised volatility of daily returns.
-- =====================================================================

DROP PROCEDURE IF EXISTS sp_refresh_latest_prices;
DELIMITER $$
CREATE PROCEDURE sp_refresh_latest_prices()
    COMMENT 'Rebuild stock_latest_price from the stock_prices time-series'
BEGIN
    DELETE FROM stock_latest_price;

    INSERT INTO stock_latest_price
        (stock_id, price_date, close_price, volume,
         close_1m, close_3m, close_6m, close_1y,
         ret_1m, ret_3m, ret_6m, ret_1y, vol_30d)
    WITH daily AS (
        SELECT
            stock_id,
            price_date,
            close_price,
            volume,
            close_price / NULLIF(LAG(close_price) OVER w, 0) - 1 AS daily_ret
        FROM stock_prices
        WINDOW w AS (PARTITION BY stock_id ORDER BY price_date)
    ),
    enriched AS (
        SELECT
            stock_id,
            price_date,
            close_price,
            volume,
            ROW_NUMBER()           OVER w2 AS rn_desc,
            LAG(close_price, 21)   OVER w3 AS c1m,
            LAG(close_price, 63)   OVER w3 AS c3m,
            LAG(close_price, 126)  OVER w3 AS c6m,
            LAG(close_price, 252)  OVER w3 AS c1y,
            STDDEV_SAMP(daily_ret) OVER (PARTITION BY stock_id
                                         ORDER BY price_date
                                         ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)
                                   AS vol30
        FROM daily
        WINDOW w2 AS (PARTITION BY stock_id ORDER BY price_date DESC),
               w3 AS (PARTITION BY stock_id ORDER BY price_date)
    )
    SELECT
        stock_id,
        price_date,
        close_price,
        volume,
        c1m, c3m, c6m, c1y,
        close_price / NULLIF(c1m, 0) - 1,
        close_price / NULLIF(c3m, 0) - 1,
        close_price / NULLIF(c6m, 0) - 1,
        close_price / NULLIF(c1y, 0) - 1,
        vol30 * SQRT(252)                      -- annualised
    FROM enriched
    WHERE rn_desc = 1;
END$$
DELIMITER ;

-- =====================================================================
--  B.  VIEWS
-- =====================================================================

-- ---------------------------------------------------------------------
-- v_latest_snapshot -- the most recent fundamentals row per stock.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_latest_snapshot AS
SELECT fs.*
FROM financial_snapshots fs
WHERE fs.as_of_date = (
        SELECT MAX(f2.as_of_date)
        FROM financial_snapshots f2
        WHERE f2.stock_id = fs.stock_id
      );

-- ---------------------------------------------------------------------
-- v_stock_metrics -- one wide row per stock: identity, sector,
-- fundamentals and derived price statistics. The single source of
-- truth for search, screener and scoring.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_stock_metrics AS
SELECT
    s.stock_id,
    s.ticker,
    s.company_name,
    s.sector_id,
    COALESCE(sec.sector_name, 'Unclassified') AS sector_name,
    s.sec_filings_url,
    fs.as_of_date,
    fs.snapshot_price,
    fs.pe_ratio,
    fs.eps,
    fs.dividend_yield,
    fs.market_cap,
    fs.ebitda,
    fs.price_sales_ratio,
    fs.price_book_ratio,
    fs.week52_low,
    fs.week52_high,
    lp.price_date   AS last_price_date,
    lp.close_price  AS last_close,
    lp.volume       AS last_volume,
    lp.ret_1m,
    lp.ret_3m,
    lp.ret_6m,
    lp.ret_1y,
    lp.vol_30d,
    -- derived, transparent ratios
    CASE WHEN fs.snapshot_price > 0 THEN fs.eps / fs.snapshot_price END        AS earnings_yield,
    CASE WHEN fs.market_cap   > 0 THEN fs.ebitda / fs.market_cap END           AS ebitda_to_mktcap,
    CASE WHEN fs.week52_high > fs.week52_low
         THEN (fs.snapshot_price - fs.week52_low)
              / (fs.week52_high - fs.week52_low) END                           AS range_position
FROM stocks s
LEFT JOIN sectors           sec ON sec.sector_id = s.sector_id
LEFT JOIN v_latest_snapshot fs  ON fs.stock_id   = s.stock_id
LEFT JOIN stock_latest_price lp ON lp.stock_id   = s.stock_id
WHERE s.is_active = TRUE;

-- ---------------------------------------------------------------------
-- v_sector_averages -- sector benchmark used by the search screen to
-- give every ratio context ("P/E 18.4 vs sector 24.1").
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_sector_averages AS
SELECT
    sector_id,
    sector_name,
    COUNT(*)                                                   AS company_count,
    COUNT(as_of_date)                                          AS scored_count,
    AVG(CASE WHEN pe_ratio          > 0 THEN pe_ratio          END) AS avg_pe,
    AVG(CASE WHEN price_sales_ratio > 0 THEN price_sales_ratio END) AS avg_ps,
    AVG(CASE WHEN price_book_ratio  > 0 THEN price_book_ratio  END) AS avg_pb,
    AVG(CASE WHEN dividend_yield   >= 0 THEN dividend_yield    END) AS avg_div_yield,
    AVG(CASE WHEN earnings_yield    > 0 THEN earnings_yield    END) AS avg_earnings_yield,
    AVG(CASE WHEN ebitda_to_mktcap  > 0 THEN ebitda_to_mktcap  END) AS avg_ebitda_to_mktcap,
    AVG(ret_1y)                                                AS avg_ret_1y,
    AVG(vol_30d)                                               AS avg_vol_30d,
    AVG(market_cap)                                            AS avg_market_cap,
    SUM(market_cap)                                            AS total_market_cap
FROM v_stock_metrics
GROUP BY sector_id, sector_name;

-- ---------------------------------------------------------------------
-- v_stock_metrics_peer -- every stock alongside its sector benchmark,
-- computed with window aggregates so the comparison costs one pass.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_stock_metrics_peer AS
SELECT
    m.*,
    AVG(CASE WHEN m.pe_ratio          > 0 THEN m.pe_ratio          END) OVER p AS sec_avg_pe,
    AVG(CASE WHEN m.price_sales_ratio > 0 THEN m.price_sales_ratio END) OVER p AS sec_avg_ps,
    AVG(CASE WHEN m.price_book_ratio  > 0 THEN m.price_book_ratio  END) OVER p AS sec_avg_pb,
    AVG(CASE WHEN m.dividend_yield   >= 0 THEN m.dividend_yield    END) OVER p AS sec_avg_div,
    AVG(CASE WHEN m.earnings_yield    > 0 THEN m.earnings_yield    END) OVER p AS sec_avg_ey,
    AVG(CASE WHEN m.ebitda_to_mktcap  > 0 THEN m.ebitda_to_mktcap  END) OVER p AS sec_avg_ebm,
    AVG(m.ret_1y)                                                       OVER p AS sec_avg_ret1y,
    -- Peers means "companies we can actually score", not every row.
    COUNT(m.as_of_date)                                                 OVER p AS sec_peers
FROM v_stock_metrics m
WINDOW p AS (PARTITION BY m.sector_id);

-- ---------------------------------------------------------------------
-- v_stock_scores -- the transparent four-factor QuantScore.
--
-- Every sub-score is a bounded ratio against the sector mean:
--     lower-is-better:  100 * peer / (peer + value)
--     higher-is-better: 100 * value / (value + peer)
-- so 50 means "exactly the sector average", 100 means "far better than
-- the sector", 0 means "far worse". No magic constants, no black box.
--
-- Those ratios only stay inside [0, 100] while both terms are positive.
-- Real companies break that: a loss-making company has negative EPS and
-- therefore a negative earnings yield, which flips the sign of the
-- denominator and sends the ratio off to several hundred. So each
-- component is guarded explicitly:
--   * a ratio that is undefined (P/E with no earnings) scores 50 --
--     neutral, because the company is not expensive, it simply has no
--     earnings to be expensive against. The profitability factor is
--     where the loss shows up.
--   * a higher-is-better measure that is actually negative scores 0.
--   * range_position is clamped to [0, 1]; a price can close outside
--     its own trailing 52-week range.
--
-- Weights: Valuation 30, Profitability 25, Growth 25, Dividend 20.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_stock_scores AS
SELECT
    p.stock_id,
    p.ticker,
    p.company_name,
    p.sector_id,
    p.sector_name,
    p.market_cap,
    p.pe_ratio,
    p.price_sales_ratio,
    p.price_book_ratio,
    p.dividend_yield,
    p.eps,
    p.earnings_yield,
    p.ebitda_to_mktcap,
    p.ret_1m,
    p.ret_3m,
    p.ret_6m,
    p.ret_1y,
    p.vol_30d,
    p.range_position,
    p.last_close,
    p.sec_avg_pe,
    p.sec_avg_ps,
    p.sec_avg_pb,
    p.sec_avg_div,
    p.sec_peers,

    -- ---- Valuation: cheap P/E, P/S and P/B relative to peers --------
    ROUND(
        0.50 * CASE WHEN p.pe_ratio > 0 AND p.sec_avg_pe > 0
                    THEN 100 * p.sec_avg_pe / (p.sec_avg_pe + p.pe_ratio)
                    ELSE 50 END
      + 0.25 * CASE WHEN p.price_sales_ratio > 0 AND p.sec_avg_ps > 0
                    THEN 100 * p.sec_avg_ps / (p.sec_avg_ps + p.price_sales_ratio)
                    ELSE 50 END
      + 0.25 * CASE WHEN p.price_book_ratio > 0 AND p.sec_avg_pb > 0
                    THEN 100 * p.sec_avg_pb / (p.sec_avg_pb + p.price_book_ratio)
                    ELSE 50 END
    , 2)                                                           AS valuation_score,

    -- ---- Profitability: earnings yield and EBITDA on market cap ----
    ROUND(
        0.60 * CASE WHEN p.earnings_yield IS NULL OR p.sec_avg_ey IS NULL THEN 50
                    WHEN p.earnings_yield <= 0 THEN 0
                    ELSE 100 * p.earnings_yield
                         / (p.earnings_yield + p.sec_avg_ey) END
      + 0.40 * CASE WHEN p.ebitda_to_mktcap IS NULL OR p.sec_avg_ebm IS NULL THEN 50
                    WHEN p.ebitda_to_mktcap <= 0 THEN 0
                    ELSE 100 * p.ebitda_to_mktcap
                         / (p.ebitda_to_mktcap + p.sec_avg_ebm) END
    , 2)                                                           AS profitability_score,

    -- ---- Growth: 12-month return vs sector + position in 52w range --
    ROUND(
        0.65 * CASE WHEN p.ret_1y IS NULL OR p.sec_avg_ret1y IS NULL THEN 50
                    WHEN GREATEST(1 + p.ret_1y, 0)
                       + GREATEST(1 + p.sec_avg_ret1y, 0) = 0 THEN 50
                    ELSE 100 * GREATEST(1 + p.ret_1y, 0)
                         / (GREATEST(1 + p.ret_1y, 0)
                            + GREATEST(1 + p.sec_avg_ret1y, 0)) END
      + 0.35 * CASE WHEN p.range_position IS NULL THEN 50
                    ELSE 100 * LEAST(1, GREATEST(0, p.range_position)) END
    , 2)                                                           AS growth_score,

    -- ---- Dividend: yield relative to the sector mean ---------------
    ROUND(
        CASE WHEN p.dividend_yield IS NULL OR p.dividend_yield <= 0 THEN 0
             WHEN p.sec_avg_div IS NULL OR p.sec_avg_div <= 0 THEN 50
             ELSE 100 * p.dividend_yield
                  / (p.dividend_yield + p.sec_avg_div) END
    , 2)                                                           AS dividend_score
FROM v_stock_metrics_peer p
-- Only score companies that have fundamentals. The price extract runs to
-- 2023 while the fundamentals extract is a 2018 snapshot, so around a
-- hundred tickers have prices but nothing to value them on. Scoring those
-- from COALESCE defaults would invent a number, so they are left out of
-- the scoring views and remain searchable, chartable and tradeable.
WHERE p.as_of_date IS NOT NULL;

-- ---------------------------------------------------------------------
-- v_stock_scores_total -- adds the weighted composite and a letter
-- grade. Kept as its own layer so the weights appear in exactly one
-- place and the sub-scores stay independently inspectable.
--
-- The grade is a quintile of the scored universe (NTILE(5)), not a fixed
-- cut-off. Absolute thresholds would be arbitrary: the composite mean is
-- about 48, not 50, because every company that pays no dividend scores
-- zero on that factor. A quintile says something defensible -- "top 20%
-- of the S&P 500 on this weighting" -- and re-calibrates itself if the
-- underlying data is reloaded.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_stock_scores_total AS
SELECT
    sc.*,
    ROUND(  sc.valuation_score     * 0.30
          + sc.profitability_score * 0.25
          + sc.growth_score        * 0.25
          + sc.dividend_score      * 0.20, 2)                      AS total_score,
    CASE NTILE(5) OVER (
            ORDER BY   sc.valuation_score     * 0.30
                     + sc.profitability_score * 0.25
                     + sc.growth_score        * 0.25
                     + sc.dividend_score      * 0.20 DESC)
        WHEN 1 THEN 'A'
        WHEN 2 THEN 'B'
        WHEN 3 THEN 'C'
        WHEN 4 THEN 'D'
        ELSE        'E'
    END                                                            AS grade
FROM v_stock_scores sc;

-- ---------------------------------------------------------------------
-- v_portfolio_holdings -- net position per portfolio derived purely
-- from the transaction ledger (BUY adds, SELL subtracts). Average cost
-- is the cost basis of the BUY leg only.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_portfolio_holdings AS
SELECT
    t.portfolio_id,
    t.stock_id,
    s.ticker,
    s.company_name,
    COALESCE(sec.sector_name, 'Unclassified')                       AS sector_name,
    SUM(CASE WHEN t.transaction_type = 'BUY'  THEN t.quantity
             ELSE -t.quantity END)                                  AS net_quantity,
    SUM(CASE WHEN t.transaction_type = 'BUY'  THEN t.quantity * t.execution_price
             ELSE 0 END)
      / NULLIF(SUM(CASE WHEN t.transaction_type = 'BUY' THEN t.quantity END), 0)
                                                                    AS avg_cost,
    SUM(CASE WHEN t.transaction_type = 'BUY'  THEN t.quantity * t.execution_price
             ELSE -t.quantity * t.execution_price END)              AS net_invested,
    SUM(t.fees)                                                     AS total_fees,
    COUNT(*)                                                        AS trade_count,
    MAX(t.executed_at)                                              AS last_traded_at,
    lp.close_price                                                  AS last_close
FROM transactions t
JOIN stocks s                ON s.stock_id   = t.stock_id
LEFT JOIN sectors sec        ON sec.sector_id = s.sector_id
LEFT JOIN stock_latest_price lp ON lp.stock_id = t.stock_id
GROUP BY t.portfolio_id, t.stock_id, s.ticker, s.company_name,
         sec.sector_name, lp.close_price
HAVING net_quantity > 0.000001;

-- ---------------------------------------------------------------------
-- v_portfolio_summary -- headline numbers per portfolio.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_portfolio_summary AS
SELECT
    pf.portfolio_id,
    pf.user_id,
    pf.name,
    pf.currency_code,
    pf.initial_cash,
    pf.cash_balance,
    COALESCE(h.positions, 0)                                        AS positions,
    COALESCE(h.market_value, 0)                                     AS market_value,
    COALESCE(h.cost_basis, 0)                                       AS cost_basis,
    pf.cash_balance + COALESCE(h.market_value, 0)                   AS total_value,
    pf.cash_balance + COALESCE(h.market_value, 0) - pf.initial_cash AS total_pnl,
    CASE WHEN pf.initial_cash > 0
         THEN (pf.cash_balance + COALESCE(h.market_value, 0) - pf.initial_cash)
              / pf.initial_cash END                                 AS total_return
FROM portfolios pf
LEFT JOIN (
    SELECT portfolio_id,
           COUNT(*)                                AS positions,
           SUM(net_quantity * COALESCE(last_close, avg_cost)) AS market_value,
           SUM(net_quantity * avg_cost)            AS cost_basis
    FROM v_portfolio_holdings
    GROUP BY portfolio_id
) h ON h.portfolio_id = pf.portfolio_id;

-- =====================================================================
--  C.  TRIGGERS -- non-standard integrity constraints
--
--  These invariants cannot be written as CHECK constraints because
--  they span rows and tables. Enforcing them in the database means
--  they hold no matter which client inserts the row.
-- =====================================================================

DROP TRIGGER IF EXISTS trg_txn_before_insert;
DELIMITER $$
CREATE TRIGGER trg_txn_before_insert
BEFORE INSERT ON transactions
FOR EACH ROW
BEGIN
    DECLARE v_held      DECIMAL(20,6);
    DECLARE v_cash      DECIMAL(20,2);
    DECLARE v_cost      DECIMAL(20,2);

    IF NEW.transaction_type = 'SELL' THEN
        -- Invariant 1: no short selling. Cannot sell more than held.
        SELECT COALESCE(SUM(CASE WHEN transaction_type = 'BUY'  THEN quantity
                                 ELSE -quantity END), 0)
          INTO v_held
          FROM transactions
         WHERE portfolio_id = NEW.portfolio_id
           AND stock_id     = NEW.stock_id;

        IF v_held < NEW.quantity THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'INSUFFICIENT_HOLDINGS: cannot sell more shares than held';
        END IF;
    ELSE
        -- Invariant 2: no margin. A BUY must be fully funded by cash.
        SET v_cost = NEW.quantity * NEW.execution_price + NEW.fees;

        SELECT cash_balance INTO v_cash
          FROM portfolios
         WHERE portfolio_id = NEW.portfolio_id;

        IF v_cash IS NULL THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'PORTFOLIO_NOT_FOUND';
        END IF;

        IF v_cash < v_cost THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'INSUFFICIENT_CASH: trade cost exceeds cash balance';
        END IF;
    END IF;
END$$
DELIMITER ;

DROP TRIGGER IF EXISTS trg_txn_after_insert;
DELIMITER $$
CREATE TRIGGER trg_txn_after_insert
AFTER INSERT ON transactions
FOR EACH ROW
BEGIN
    -- Keep the cash balance consistent with the ledger on every path.
    IF NEW.transaction_type = 'BUY' THEN
        UPDATE portfolios
           SET cash_balance = cash_balance - (NEW.quantity * NEW.execution_price + NEW.fees)
         WHERE portfolio_id = NEW.portfolio_id;
    ELSE
        UPDATE portfolios
           SET cash_balance = cash_balance + (NEW.quantity * NEW.execution_price - NEW.fees)
         WHERE portfolio_id = NEW.portfolio_id;
    END IF;
END$$
DELIMITER ;

-- =====================================================================
--  D.  TRADE EXECUTION -- the ACID showcase.
--
--  One statement from the client; inside, the procedure
--    1. opens an explicit transaction,
--    2. takes a row lock on the portfolio (SELECT ... FOR UPDATE) so two
--       concurrent trades on the same portfolio serialise,
--    3. resolves the ticker and the last traded price,
--    4. inserts the ledger row, which fires the integrity triggers,
--    5. COMMITs, or ROLLBACKs the whole thing on any SQL exception and
--       re-raises the error to the caller.
--  Either all of it happens or none of it does.
-- =====================================================================

DROP PROCEDURE IF EXISTS sp_execute_trade;
DELIMITER $$
CREATE PROCEDURE sp_execute_trade(
    IN  p_portfolio_id BIGINT,
    IN  p_ticker       VARCHAR(10),
    IN  p_side         VARCHAR(4),
    IN  p_quantity     DECIMAL(20,6),
    IN  p_fee_rate     DECIMAL(10,6),
    OUT p_transaction_id BIGINT,
    OUT p_price        DECIMAL(20,6),
    OUT p_cash_after   DECIMAL(20,2)
)
    COMMENT 'Atomically execute a simulated BUY/SELL against a portfolio'
BEGIN
    DECLARE v_stock_id BIGINT;
    DECLARE v_fees     DECIMAL(20,6);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'INVALID_QUANTITY';
    END IF;
    IF p_side NOT IN ('BUY', 'SELL') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'INVALID_SIDE';
    END IF;

    START TRANSACTION;

    -- Serialise concurrent trades on the same portfolio.
    SELECT cash_balance INTO p_cash_after
      FROM portfolios
     WHERE portfolio_id = p_portfolio_id
       FOR UPDATE;

    IF p_cash_after IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PORTFOLIO_NOT_FOUND';
    END IF;

    SELECT stock_id INTO v_stock_id
      FROM stocks
     WHERE ticker = UPPER(p_ticker)
       AND is_active = TRUE;

    IF v_stock_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'UNKNOWN_TICKER';
    END IF;

    SELECT close_price INTO p_price
      FROM stock_latest_price
     WHERE stock_id = v_stock_id;

    IF p_price IS NULL THEN
        SELECT snapshot_price INTO p_price
          FROM v_latest_snapshot
         WHERE stock_id = v_stock_id;
    END IF;

    IF p_price IS NULL OR p_price <= 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'NO_PRICE_AVAILABLE';
    END IF;

    SET v_fees = ROUND(p_quantity * p_price * COALESCE(p_fee_rate, 0), 6);

    INSERT INTO transactions
        (portfolio_id, stock_id, transaction_type, quantity, execution_price, fees)
    VALUES
        (p_portfolio_id, v_stock_id, p_side, p_quantity, p_price, v_fees);

    SET p_transaction_id = LAST_INSERT_ID();

    SELECT cash_balance INTO p_cash_after
      FROM portfolios
     WHERE portfolio_id = p_portfolio_id;

    COMMIT;
END$$
DELIMITER ;

-- =====================================================================
--  E.  SECTOR RE-BENCHMARK -- a reporting procedure that returns the
--      sector league table ordered by aggregate QuantScore.
-- =====================================================================

DROP PROCEDURE IF EXISTS sp_sector_leaderboard;
DELIMITER $$
CREATE PROCEDURE sp_sector_leaderboard(IN p_min_market_cap DECIMAL(24,2))
    COMMENT 'Sector league table weighted by market capitalisation'
BEGIN
    SELECT
        sector_name,
        COUNT(*)                                          AS companies,
        ROUND(AVG(total_score), 2)                        AS avg_score,
        ROUND(SUM(total_score * market_cap)
              / NULLIF(SUM(market_cap), 0), 2)            AS cap_weighted_score,
        ROUND(AVG(valuation_score), 2)                    AS avg_valuation,
        ROUND(AVG(profitability_score), 2)                AS avg_profitability,
        ROUND(AVG(growth_score), 2)                       AS avg_growth,
        ROUND(AVG(dividend_score), 2)                     AS avg_dividend,
        SUM(market_cap)                                   AS total_market_cap
    FROM v_stock_scores_total
    WHERE market_cap >= COALESCE(p_min_market_cap, 0)
    GROUP BY sector_name
    ORDER BY cap_weighted_score DESC;
END$$
DELIMITER ;
