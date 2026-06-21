"""HTTP scraper for OpenInsider website."""

import logging
import time
from typing import List, Optional

import requests

from openinsider.config import CONFIG
from openinsider.models import ClusterBuy
from openinsider.parser import parse_cluster_table

logger = logging.getLogger(__name__)


class OpenInsiderScraper:
    """Scraper for OpenInsider cluster buys."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        user_agent: Optional[str] = None,
    ):
        """Initialize scraper."""
        self.base_url = base_url or CONFIG["scraper"]["base_url"]
        self.timeout = timeout or CONFIG["scraper"]["timeout"]
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent or CONFIG["scraper"]["user_agent"]

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def close(self) -> None:
        """Close HTTP session."""
        self.session.close()

    def _request_with_retry(self, url: str) -> requests.Response:
        """Make HTTP request with exponential backoff retry.

        Retries on connection errors, timeouts, and 5xx server errors.
        Does not retry on 4xx client errors.
        """
        max_retries = CONFIG["scraper"]["max_retries"]
        backoff = CONFIG["scraper"]["retry_backoff"]

        for attempt in range(max_retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout)

                if response.status_code >= 500 and attempt < max_retries:
                    wait = backoff * (2 ** attempt)
                    logger.warning(
                        f"Server error {response.status_code}, retrying in {wait:.1f}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                return response

            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < max_retries:
                    wait = backoff * (2 ** attempt)
                    logger.warning(
                        f"{type(e).__name__}, retrying in {wait:.1f}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait)
                    continue
                raise

        raise requests.RequestException(f"Max retries ({max_retries}) exceeded for {url}")

    def scrape_cluster_buys(self) -> List[ClusterBuy]:
        """
        Scrape main cluster buys table.

        Returns:
            List of ClusterBuy objects

        Raises:
            requests.RequestException: On HTTP errors after retries exhausted
        """
        url = f"{self.base_url}/latest-cluster-buys"
        logger.info(f"Scraping cluster buys from {url}")

        try:
            response = self._request_with_retry(url)

            clusters = parse_cluster_table(response.text, source_url=url)
            logger.info(f"Successfully scraped {len(clusters)} cluster buys")

            return clusters

        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response else "Unknown"
            logger.error(f"HTTP error {status_code}: {e}")
            raise
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during scraping: {e}", exc_info=True)
            raise

    def scrape_ticker_details(self, ticker: str) -> List[dict]:
        """
        Scrape individual insider details for a ticker (Phase 2).

        Args:
            ticker: Stock ticker symbol

        Returns:
            List of insider transactions

        Raises:
            requests.RequestException: On HTTP errors after retries exhausted
        """
        from openinsider.parser import parse_insider_detail_page

        url = f"{self.base_url}/{ticker}"
        logger.info(f"Scraping ticker details from {url}")

        try:
            response = self._request_with_retry(url)

            transactions = parse_insider_detail_page(response.text, ticker)
            logger.info(f"Successfully scraped {len(transactions)} transactions for {ticker}")

            return transactions

        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response else "Unknown"
            logger.error(f"HTTP error {status_code} for {ticker}: {e}")
            raise
        except requests.RequestException as e:
            logger.error(f"Request failed for {ticker}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error scraping {ticker}: {e}", exc_info=True)
            raise
