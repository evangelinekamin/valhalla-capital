"""
Yellowbrick Scraper Configuration

Loads environment variables and provides configuration objects.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env file
load_dotenv()


def get_env(key: str, default: Optional[str] = None, required: bool = False) -> str:
    """
    Get environment variable with optional default and validation.

    Args:
        key: Environment variable name
        default: Default value if not set
        required: Raise error if missing and no default

    Returns:
        Environment variable value

    Raises:
        ValueError: If required variable is missing
    """
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(f"Required environment variable {key} is not set")
    return value


def get_bool_env(key: str, default: bool = False) -> bool:
    """
    Get boolean environment variable.

    Args:
        key: Environment variable name
        default: Default value if not set

    Returns:
        Boolean value (true/false, yes/no, 1/0)
    """
    value = os.getenv(key, str(default)).lower()
    return value in ('true', 'yes', '1', 'on')


def get_int_env(key: str, default: int) -> int:
    """
    Get integer environment variable.

    Args:
        key: Environment variable name
        default: Default value if not set

    Returns:
        Integer value
    """
    value = os.getenv(key)
    if value is None:
        return default
    return int(value)


# Database configuration
DATABASE_PATH = Path(get_env('DATABASE_PATH', './data/yellowbrick.db'))
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Cookie file for authentication
COOKIE_FILE = Path(get_env('COOKIE_FILE', './data/session_cookies.json'))

# Feed URLs
BIG_MONEY_URL = get_env('BIG_MONEY_URL', 'https://www.joinyellowbrick.com/feeds/top_funds_us')
ELITE_URL = get_env('ELITE_URL', 'https://www.joinyellowbrick.com/feeds/elite_us')

# Playwright settings
PLAYWRIGHT_HEADLESS = get_bool_env('PLAYWRIGHT_HEADLESS', True)
PLAYWRIGHT_TIMEOUT = get_int_env('PLAYWRIGHT_TIMEOUT', 30000)

# Rate limiting
DELAY_BETWEEN_FEEDS = get_int_env('DELAY_BETWEEN_FEEDS', 5)

# Discord webhook (optional)
DISCORD_WEBHOOK_URL = get_env('DISCORD_WEBHOOK_URL')

# Logging configuration
LOG_LEVEL = get_env('LOG_LEVEL', 'INFO')
LOG_FILE = Path(get_env('LOG_FILE', './logs/yellowbrick.log'))
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Configuration dictionary for easy passing
CONFIG = {
    'database': {
        'path': DATABASE_PATH,
    },
    'auth': {
        'cookie_file': COOKIE_FILE,
    },
    'feeds': {
        'big_money': {
            'name': 'big_money',
            'url': BIG_MONEY_URL,
        },
        'elite': {
            'name': 'elite',
            'url': ELITE_URL,
        },
    },
    'playwright': {
        'headless': PLAYWRIGHT_HEADLESS,
        'timeout': PLAYWRIGHT_TIMEOUT,
    },
    'rate_limiting': {
        'delay_between_feeds': DELAY_BETWEEN_FEEDS,
    },
    'discord': {
        'enabled': DISCORD_WEBHOOK_URL is not None,
        'webhook_url': DISCORD_WEBHOOK_URL,
    },
    'logging': {
        'level': LOG_LEVEL,
        'file': LOG_FILE,
    },
}
