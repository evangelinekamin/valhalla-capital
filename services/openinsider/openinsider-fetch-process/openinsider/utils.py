"""Utility functions for logging and alerts."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

import requests

from openinsider.config import CONFIG


def setup_logging(log_config: dict) -> None:
    """Configure logging for the application."""
    log_file = Path(log_config["file"])
    log_file.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=log_config.get("max_bytes", 10 * 1024 * 1024),
        backupCount=log_config.get("backup_count", 5),
    )
    file_handler.setFormatter(logging.Formatter(log_config["format"]))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_config["format"]))

    logging.basicConfig(
        level=getattr(logging, log_config["level"]),
        handlers=[file_handler, console_handler],
    )


def send_discord_alert(message: str, webhook_url: Optional[str] = None) -> bool:
    """Send alert to Discord webhook."""
    url = webhook_url or CONFIG["discord"]["webhook_url"]

    if not url:
        logging.warning("Discord webhook URL not configured, skipping alert")
        return False

    try:
        response = requests.post(
            url,
            json={"content": message},
            timeout=10,
        )
        response.raise_for_status()
        logging.info(f"Discord alert sent: {message}")
        return True
    except Exception as e:
        logging.error(f"Failed to send Discord alert: {e}")
        return False
