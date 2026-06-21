"""Configuration management."""

import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()


def get_config() -> Dict[str, Any]:
    """Get application configuration."""
    project_root = Path(__file__).parent.parent

    return {
        "database": {
            "path": os.getenv("DATABASE_PATH", str(project_root / "data" / "openinsider.db")),
            "schema_path": str(project_root / "schema.sql"),
        },
        "scraper": {
            "base_url": os.getenv("SCRAPER_BASE_URL", "http://openinsider.com"),
            "timeout": int(os.getenv("SCRAPER_TIMEOUT", "30")),
            "user_agent": os.getenv(
                "USER_AGENT",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            ),
            "rate_limit_delay": float(os.getenv("RATE_LIMIT_DELAY", "2.0")),
            "max_retries": int(os.getenv("SCRAPER_MAX_RETRIES", "3")),
            "retry_backoff": float(os.getenv("SCRAPER_RETRY_BACKOFF", "2.0")),
        },
        "logging": {
            "level": os.getenv("LOG_LEVEL", "INFO"),
            "file": os.getenv("LOG_FILE", str(project_root / "logs" / "openinsider.log")),
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "max_bytes": int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024))),
            "backup_count": int(os.getenv("LOG_BACKUP_COUNT", "5")),
        },
        "discord": {
            "webhook_url": os.getenv("DISCORD_WEBHOOK_URL", ""),
            "alert_threshold": int(os.getenv("DISCORD_ALERT_THRESHOLD", "10")),
        },
    }


CONFIG = get_config()
