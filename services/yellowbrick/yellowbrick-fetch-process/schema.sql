-- Yellowbrick Scraper Database Schema
-- SQLite database for tracking institutional investor pitches

-- ============================================================================
-- Main pitches table
-- ============================================================================
CREATE TABLE IF NOT EXISTS yellowbrick_pitches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Core identification
    ticker VARCHAR(10) NOT NULL,
    feed_type VARCHAR(20) NOT NULL CHECK(feed_type IN ('big_money', 'elite')),
    pitch_id VARCHAR(100) UNIQUE,
    
    -- Pitch details
    author VARCHAR(255) NOT NULL,
    author_type VARCHAR(50),
    pitch_date DATETIME,
    pitch_type VARCHAR(50),
    
    -- Content
    title TEXT,
    summary TEXT,
    full_content TEXT,
    reasoning TEXT,
    target_price DECIMAL(10, 2),
    time_horizon VARCHAR(50),
    
    -- Metadata
    source_url TEXT,
    filing_type VARCHAR(50),
    position_size VARCHAR(50),
    metadata JSON,
    
    -- Tracking
    first_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    
    -- Indexes
    CHECK(ticker = UPPER(ticker))
);

CREATE INDEX IF NOT EXISTS idx_pitches_ticker ON yellowbrick_pitches(ticker);
CREATE INDEX IF NOT EXISTS idx_pitches_feed_type ON yellowbrick_pitches(feed_type);
CREATE INDEX IF NOT EXISTS idx_pitches_author ON yellowbrick_pitches(author);
CREATE INDEX IF NOT EXISTS idx_pitches_pitch_date ON yellowbrick_pitches(pitch_date);
CREATE INDEX IF NOT EXISTS idx_pitches_first_seen ON yellowbrick_pitches(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_pitches_active ON yellowbrick_pitches(is_active);

-- ============================================================================
-- Position tracking table (for monitoring changes over time)
-- ============================================================================
CREATE TABLE IF NOT EXISTS yellowbrick_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    pitch_id VARCHAR(100) NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    author VARCHAR(255) NOT NULL,
    
    -- Position tracking
    check_date DATE NOT NULL,
    position_status VARCHAR(20),
    shares BIGINT,
    value DECIMAL(15, 2),
    percent_of_portfolio DECIMAL(5, 2),
    
    -- Change tracking
    shares_change BIGINT,
    value_change DECIMAL(15, 2),
    
    FOREIGN KEY (pitch_id) REFERENCES yellowbrick_pitches(pitch_id)
);

CREATE INDEX IF NOT EXISTS idx_positions_ticker_date ON yellowbrick_positions(ticker, check_date);
CREATE INDEX IF NOT EXISTS idx_positions_author_date ON yellowbrick_positions(author, check_date);
CREATE INDEX IF NOT EXISTS idx_positions_pitch_id ON yellowbrick_positions(pitch_id);

-- ============================================================================
-- Scrape log table (monitoring and debugging)
-- ============================================================================
CREATE TABLE IF NOT EXISTS yellowbrick_scrape_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    scrape_timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    feed_type VARCHAR(20) NOT NULL,
    
    -- Results
    pitches_found INTEGER DEFAULT 0,
    pitches_new INTEGER DEFAULT 0,
    pitches_updated INTEGER DEFAULT 0,
    
    -- Performance
    duration_seconds DECIMAL(6, 2),
    status VARCHAR(20) NOT NULL CHECK(status IN ('SUCCESS', 'PARTIAL', 'FAILED', 'PENDING')),
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_scrape_log_timestamp ON yellowbrick_scrape_log(scrape_timestamp);
CREATE INDEX IF NOT EXISTS idx_scrape_log_feed_type ON yellowbrick_scrape_log(feed_type);
CREATE INDEX IF NOT EXISTS idx_scrape_log_status ON yellowbrick_scrape_log(status);

-- ============================================================================
-- Views for common queries
-- ============================================================================

-- Recent pitches (last 30 days)
CREATE VIEW IF NOT EXISTS v_recent_pitches AS
SELECT 
    ticker,
    author,
    feed_type,
    pitch_type,
    pitch_date,
    title,
    summary,
    target_price,
    time_horizon,
    first_seen_at
FROM yellowbrick_pitches
WHERE DATE(pitch_date) >= DATE('now', '-30 days')
  AND is_active = 1
ORDER BY pitch_date DESC;

-- Elite fund pitches only
CREATE VIEW IF NOT EXISTS v_elite_pitches AS
SELECT 
    ticker,
    author,
    pitch_type,
    pitch_date,
    title,
    summary,
    reasoning,
    target_price,
    source_url
FROM yellowbrick_pitches
WHERE feed_type = 'elite'
  AND is_active = 1
ORDER BY pitch_date DESC;

-- Scrape health summary
CREATE VIEW IF NOT EXISTS v_scrape_health AS
SELECT 
    feed_type,
    COUNT(*) as total_scrapes,
    SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as successful,
    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed,
    AVG(duration_seconds) as avg_duration,
    MAX(scrape_timestamp) as last_scrape,
    SUM(pitches_new) as total_new_pitches,
    SUM(pitches_updated) as total_updates
FROM yellowbrick_scrape_log
GROUP BY feed_type;

-- ============================================================================
-- Helper queries for researcher integration
-- ============================================================================

-- Find all pitches for a specific ticker
-- SELECT * FROM yellowbrick_pitches WHERE ticker = 'GOOGL' AND is_active = 1;

-- Get notable fund activity
-- SELECT author, COUNT(*) as pitch_count, 
--        GROUP_CONCAT(DISTINCT ticker) as tickers
-- FROM yellowbrick_pitches 
-- WHERE pitch_date >= DATE('now', '-90 days')
-- GROUP BY author
-- ORDER BY pitch_count DESC;

-- Find recent shorts/activist positions
-- SELECT * FROM yellowbrick_pitches 
-- WHERE pitch_type IN ('SHORT', 'ACTIVIST')
--   AND pitch_date >= DATE('now', '-30 days')
-- ORDER BY pitch_date DESC;

-- Check scrape health
-- SELECT * FROM v_scrape_health;

-- ============================================================================
-- Triggers for automatic timestamp updates
-- ============================================================================

CREATE TRIGGER IF NOT EXISTS update_pitch_timestamp 
AFTER UPDATE ON yellowbrick_pitches
BEGIN
    UPDATE yellowbrick_pitches 
    SET last_updated_at = CURRENT_TIMESTAMP 
    WHERE id = NEW.id;
END;
