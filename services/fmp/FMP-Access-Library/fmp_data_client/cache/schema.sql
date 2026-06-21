-- FMP Data Client Cache Schema

-- Main ticker cache table
CREATE TABLE IF NOT EXISTS ticker_cache (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    period_key VARCHAR(50) DEFAULT NULL,
    data JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    INDEX idx_symbol (symbol),
    INDEX idx_data_type (data_type),
    INDEX idx_expires (expires_at),
    UNIQUE KEY unique_cache_entry (symbol, data_type, period_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Transcript summaries cache
CREATE TABLE IF NOT EXISTS transcript_summaries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    year INT NOT NULL,
    quarter INT NOT NULL,
    summary JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model_used VARCHAR(100) DEFAULT NULL,
    INDEX idx_symbol (symbol),
    UNIQUE KEY unique_transcript (symbol, year, quarter)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- SEC filing summaries cache
CREATE TABLE IF NOT EXISTS filing_summaries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    accession_number VARCHAR(50) NOT NULL,
    filing_type VARCHAR(20) NOT NULL,
    filing_date DATE NOT NULL,
    summary JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model_used VARCHAR(100) DEFAULT NULL,
    INDEX idx_symbol (symbol),
    INDEX idx_filing_type (filing_type),
    UNIQUE KEY unique_filing (accession_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Cache statistics table
CREATE TABLE IF NOT EXISTS cache_stats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    total_requests INT DEFAULT 0,
    cache_hits INT DEFAULT 0,
    cache_misses INT DEFAULT 0,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_symbol (symbol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
