-- FMP Data Client Cache Database Initialization
-- This script runs when MySQL container is first created

USE fmp_cache;

-- Create cache table for FMP API responses
CREATE TABLE IF NOT EXISTS api_cache (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    cache_key VARCHAR(512) NOT NULL UNIQUE,
    endpoint VARCHAR(255) NOT NULL,
    symbol VARCHAR(50),
    response_data LONGTEXT NOT NULL,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    hit_count INT UNSIGNED DEFAULT 0,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_cache_key (cache_key),
    INDEX idx_endpoint (endpoint),
    INDEX idx_symbol (symbol),
    INDEX idx_expires_at (expires_at),
    INDEX idx_cached_at (cached_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create cache statistics table for monitoring
CREATE TABLE IF NOT EXISTS cache_stats (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    stat_date DATE NOT NULL UNIQUE,
    total_requests BIGINT UNSIGNED DEFAULT 0,
    cache_hits BIGINT UNSIGNED DEFAULT 0,
    cache_misses BIGINT UNSIGNED DEFAULT 0,
    avg_response_time_ms DECIMAL(10,2),
    total_cache_size_mb DECIMAL(10,2),
    INDEX idx_stat_date (stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create ticker cache table (used by cache layer)
CREATE TABLE IF NOT EXISTS ticker_cache (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    data_type VARCHAR(100) NOT NULL,
    period_key VARCHAR(50),
    data LONGTEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    UNIQUE KEY idx_symbol_type_period (symbol, data_type, period_key),
    INDEX idx_symbol (symbol),
    INDEX idx_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create API keys table for persistent storage
CREATE TABLE IF NOT EXISTS api_keys (
    api_key VARCHAR(128) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    tier VARCHAR(50) NOT NULL DEFAULT 'STARTER',
    rate_limit INT UNSIGNED NOT NULL DEFAULT 60,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert default demo API key
INSERT INTO api_keys (api_key, name, tier, rate_limit, enabled)
VALUES ('demo-api-key-12345', 'Demo Client', 'STARTER', 60, TRUE)
ON DUPLICATE KEY UPDATE api_key = api_key;

-- Create API key usage tracking table (optional - for production)
CREATE TABLE IF NOT EXISTS api_key_usage (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    api_key_hash VARCHAR(128) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,
    request_count INT UNSIGNED DEFAULT 1,
    last_request TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_api_key_hash (api_key_hash),
    INDEX idx_endpoint (endpoint),
    INDEX idx_last_request (last_request)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create stored procedure to clean up expired cache entries
DELIMITER //
CREATE PROCEDURE cleanup_expired_cache()
BEGIN
    DELETE FROM api_cache
    WHERE expires_at IS NOT NULL
    AND expires_at < NOW();

    SELECT ROW_COUNT() AS deleted_rows;
END //
DELIMITER ;

-- Create event to run cache cleanup daily at 3 AM
SET GLOBAL event_scheduler = ON;

CREATE EVENT IF NOT EXISTS daily_cache_cleanup
ON SCHEDULE EVERY 1 DAY
STARTS (TIMESTAMP(CURRENT_DATE) + INTERVAL 1 DAY + INTERVAL 3 HOUR)
DO CALL cleanup_expired_cache();

-- Insert initial cache stats record
INSERT INTO cache_stats (stat_date, total_requests, cache_hits, cache_misses)
VALUES (CURDATE(), 0, 0, 0)
ON DUPLICATE KEY UPDATE stat_date = stat_date;

-- Grant necessary permissions to application user
GRANT SELECT, INSERT, UPDATE, DELETE ON fmp_cache.* TO 'fmp_user'@'%';
FLUSH PRIVILEGES;

-- Display initialization success message
SELECT 'FMP Data Client database initialized successfully' AS message;
