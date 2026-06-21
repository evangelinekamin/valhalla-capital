"""
Yellowbrick Scraper Package

Production-ready scraper for joinyellowbrick.com institutional investor pitches.
"""

from yellowbrick.authenticator import YellowbrickAuth
from yellowbrick.database import YellowbrickDB
from yellowbrick.models import (
    FeedType,
    Pitch,
    ScrapeLog,
    ScrapeStatus,
)
from yellowbrick.parser import (
    determine_author_type,
    determine_pitch_type,
    extract_author_data,
    extract_company_data,
    extract_returns_data,
    parse_pitches_list,
    parse_raw_pitch,
)
from yellowbrick.scraper import YellowbrickScraper

__version__ = "1.0.0"

__all__ = [
    # Core components
    "YellowbrickAuth",
    "YellowbrickDB",
    "YellowbrickScraper",
    # Models
    "Pitch",
    "ScrapeLog",
    "FeedType",
    "ScrapeStatus",
    # Parser functions
    "parse_raw_pitch",
    "parse_pitches_list",
    "extract_company_data",
    "extract_returns_data",
    "extract_author_data",
    "determine_pitch_type",
    "determine_author_type",
]
