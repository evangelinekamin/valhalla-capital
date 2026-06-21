"""
Yellowbrick Scraper Utilities

Logging setup, Discord notifications, and helper functions.
"""

import sys
import logging
from typing import Optional
from pathlib import Path


def setup_logging(log_level: str = 'INFO', log_file: Optional[Path] = None) -> None:
    """
    Configure logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional path to log file
    """
    handlers = [logging.StreamHandler(sys.stdout)]

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers,
    )


def send_discord_alert(message: str, webhook_url: Optional[str]) -> bool:
    """
    Send alert to Discord webhook.

    Args:
        message: Message to send
        webhook_url: Discord webhook URL (if None, returns False)

    Returns:
        True if sent successfully, False otherwise
    """
    if not webhook_url:
        return False

    try:
        import requests

        response = requests.post(
            webhook_url,
            json={'content': message},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Failed to send Discord alert: {e}")
        return False
