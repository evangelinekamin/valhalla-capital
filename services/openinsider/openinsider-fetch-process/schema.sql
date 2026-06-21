-- OpenInsider Cluster Buys Database Schema

-- Main cluster buys data
CREATE TABLE IF NOT EXISTS cluster_buys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker VARCHAR(10) NOT NULL,
    company_name VARCHAR(255),
    industry VARCHAR(255),
    insider_count INTEGER NOT NULL,
    filing_date DATETIME NOT NULL,
    trade_date DATE NOT NULL,
    trade_type VARCHAR(50),
    avg_price DECIMAL(10, 2),
    total_qty BIGINT,
    total_owned BIGINT,
    ownership_change_pct VARCHAR(10),
    total_value BIGINT,
    transaction_code VARCHAR(10),
    perf_1d DECIMAL(6, 2),
    perf_1w DECIMAL(6, 2),
    perf_1m DECIMAL(6, 2),
    perf_6m DECIMAL(6, 2),
    source_url TEXT,
    first_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    UNIQUE(ticker, trade_date, filing_date)
);

-- Individual insider transactions (Phase 2)
CREATE TABLE IF NOT EXISTS insider_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_buy_id INTEGER,
    ticker VARCHAR(10) NOT NULL,
    insider_name VARCHAR(255) NOT NULL,
    insider_title VARCHAR(255),
    insider_type VARCHAR(50),
    trade_date DATE NOT NULL,
    trade_type VARCHAR(50),
    price DECIMAL(10, 2),
    qty BIGINT,
    owned_after BIGINT,
    ownership_change_pct DECIMAL(6, 2),
    value BIGINT,
    form_type VARCHAR(20),
    sec_link TEXT,
    scraped_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cluster_buy_id) REFERENCES cluster_buys(id),
    UNIQUE(ticker, insider_name, trade_date, trade_type)
);

-- Scrape monitoring log
CREATE TABLE IF NOT EXISTS scrape_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scrape_timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    scrape_type VARCHAR(50) NOT NULL,
    records_found INTEGER DEFAULT 0,
    records_new INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    duration_seconds DECIMAL(6, 2),
    status VARCHAR(20) CHECK(status IN ('SUCCESS', 'PARTIAL', 'FAILED')),
    error_message TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_cluster_buys_ticker ON cluster_buys(ticker);
CREATE INDEX IF NOT EXISTS idx_cluster_buys_trade_date ON cluster_buys(trade_date);
CREATE INDEX IF NOT EXISTS idx_cluster_buys_filing_date ON cluster_buys(filing_date);
CREATE INDEX IF NOT EXISTS idx_cluster_buys_is_active ON cluster_buys(is_active);
CREATE INDEX IF NOT EXISTS idx_insider_transactions_ticker ON insider_transactions(ticker);
CREATE INDEX IF NOT EXISTS idx_insider_transactions_trade_date ON insider_transactions(trade_date);
CREATE INDEX IF NOT EXISTS idx_scrape_log_timestamp ON scrape_log(scrape_timestamp);

-- View for recent active clusters
CREATE VIEW IF NOT EXISTS recent_clusters AS
SELECT
    ticker,
    company_name,
    industry,
    insider_count,
    filing_date,
    trade_date,
    avg_price,
    total_qty,
    total_value,
    perf_1d,
    perf_1w,
    perf_1m,
    perf_6m
FROM cluster_buys
WHERE is_active = 1
ORDER BY filing_date DESC
LIMIT 100;
