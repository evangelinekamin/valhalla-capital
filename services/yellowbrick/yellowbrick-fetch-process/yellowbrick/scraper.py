"""
Playwright-based web scraper for Yellowbrick pitches.

Extracts pitch data from Yellowbrick feed pages by parsing embedded Next.js JSON.
Uses cookie-based authentication via YellowbrickAuth.

IMPORTANT: This module follows immutability principles:
- All methods return new objects
- Errors are handled gracefully (empty lists returned, not exceptions)
- Resources are properly cleaned up
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from yellowbrick.authenticator import YellowbrickAuth
from yellowbrick.models import Pitch
from yellowbrick.parser import parse_pitches_list


class YellowbrickScraper:
    """
    Playwright-based scraper for Yellowbrick feed pages.

    Extracts pitch data from embedded Next.js JSON in script tags.

    Usage:
        auth = YellowbrickAuth(Path("cookies.json"))
        scraper = YellowbrickScraper(auth, headless=True)

        pitches = scraper.scrape_feed(
            "https://www.joinyellowbrick.com/feeds/big_money",
            feed_type="big_money"
        )

        scraper.close()

    Or using context manager:
        with YellowbrickScraper(auth) as scraper:
            pitches = scraper.scrape_feed(url, feed_type)
    """

    def __init__(
        self,
        auth: YellowbrickAuth,
        headless: bool = True,
        timeout: int = 30000,
    ) -> None:
        """
        Initialize scraper with authentication and configuration.

        Args:
            auth: YellowbrickAuth instance for cookie injection.
            headless: Run browser in headless mode (default True).
            timeout: Navigation timeout in milliseconds (default 30000).
        """
        self.auth = auth
        self.headless = headless
        self.timeout = timeout

        # Browser instance (initialized on first scrape)
        self._playwright = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "YellowbrickScraper":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit with cleanup."""
        self.close()

    def _ensure_browser(self) -> None:
        """Initialize browser if not already running."""
        if self._browser is None:
            try:
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(headless=self.headless)
                self._context = self._browser.new_context()

                # Inject cookies
                self.auth.inject_cookies(self._context)
            except Exception as e:
                # Clean up any partially initialized resources
                logger.error("Failed to initialize browser: %s", e)
                self._cleanup_partial_browser()
                raise

    def scrape_feed(self, feed_url: str, feed_type: str) -> list[Pitch]:
        """
        Scrape a Yellowbrick feed page and extract pitches.

        Args:
            feed_url: Full URL to the feed page
                      (e.g., "https://www.joinyellowbrick.com/feeds/big_money")
            feed_type: Feed type identifier ("big_money" or "elite")

        Returns:
            List of parsed Pitch objects. Returns empty list on error.
        """
        try:
            self._ensure_browser()

            page = self._context.new_page()

            try:
                # Navigate to feed page
                page.goto(feed_url, timeout=self.timeout)

                # Wait for content to load
                try:
                    page.wait_for_selector("article", timeout=self.timeout)
                except PlaywrightTimeout:
                    # Continue even if selector times out
                    pass

                # Extract JSON from script tags
                raw_pitches = self._extract_json_from_scripts(page)

                if not raw_pitches:
                    return []

                # Parse using existing parser
                return parse_pitches_list(raw_pitches, feed_type)

            finally:
                page.close()

        except PlaywrightTimeout:
            logger.error("Timeout scraping feed: %s", feed_url)
            return []
        except Exception:
            logger.error("Error scraping feed: %s", feed_url, exc_info=True)
            return []

    def _extract_json_from_scripts(self, page: Any) -> list[dict[str, Any]]:
        """
        Extract initialStockPitches JSON from page script tags.

        Parses Next.js embedded data format:
        self.__next_f.push([1,"...initialStockPitches\\":[{...}]..."])

        Args:
            page: Playwright Page instance

        Returns:
            List of raw pitch dictionaries, or empty list if not found/parse error.
        """
        try:
            html_content = page.content()

            # Pattern to find initialStockPitches array
            # The data is escaped JSON within script tags
            # Format: initialStockPitches\\":[{...}]

            # Try escaped format (Next.js push format) - this is the most common
            # Use non-greedy match to get the full array
            escaped_pattern = r'initialStockPitches\\":\s*(\[.+?\])'

            match = re.search(escaped_pattern, html_content, re.DOTALL)

            if match:
                try:
                    # Get the escaped JSON string
                    escaped_json = match.group(1)
                    # Replace escaped quotes
                    unescaped = escaped_json.replace('\\"', '"')
                    return json.loads(unescaped)
                except json.JSONDecodeError:
                    pass

            # Fallback: Try unescaped format
            pattern = r'"initialStockPitches":\s*(\[.+?\])'

            match = re.search(pattern, html_content, re.DOTALL)

            if match:
                try:
                    pitches_json = match.group(1)
                    return json.loads(pitches_json)
                except json.JSONDecodeError:
                    pass

            return []

        except Exception:
            logger.error("Error extracting JSON from page scripts", exc_info=True)
            return []

    def _cleanup_partial_browser(self) -> None:
        """
        Clean up partially initialized browser resources.

        Used when browser initialization fails partway through.
        """
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            finally:
                self._browser = None

        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            finally:
                self._playwright = None

        self._context = None

    def close(self) -> None:
        """
        Clean up browser resources.

        Safe to call multiple times or when browser was never initialized.
        """
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                logger.warning("Error during browser cleanup", exc_info=True)
            finally:
                self._browser = None

        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                logger.warning("Error during playwright cleanup", exc_info=True)
            finally:
                self._playwright = None

        self._context = None
