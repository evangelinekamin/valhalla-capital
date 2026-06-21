"""
Tests for Yellowbrick web scraper.

Tests for the Yellowbrick Playwright-based web scraper.

Uses mocked Playwright to avoid launching real browsers in tests.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Sample HTML with embedded Next.js data
SAMPLE_HTML_WITH_PITCHES = """
<!DOCTYPE html>
<html>
<head><title>Yellowbrick Feed</title></head>
<body>
<script>
self.__next_f.push([1,"some data here"])
</script>
<script>
self.__next_f.push([1,"more data with \\"initialStockPitches\\":[{\\"id\\":126819,\\"givenTicker\\":\\"DBO.TO\\",\\"sentiment\\":\\"bullish\\",\\"title\\":\\"Test Pitch\\",\\"author\\":{\\"authorName\\":\\"Test Author\\",\\"isProfessional\\":true}}] and more data"])
</script>
<article class="pitch-card">Content here</article>
</body>
</html>
"""

SAMPLE_HTML_MULTIPLE_PITCHES = """
<!DOCTYPE html>
<html>
<body>
<script>
self.__next_f.push([1,"initialStockPitches\\":[{\\"id\\":1,\\"givenTicker\\":\\"AAPL\\",\\"sentiment\\":\\"bullish\\",\\"author\\":{\\"authorName\\":\\"Author1\\",\\"isProfessional\\":true}},{\\"id\\":2,\\"givenTicker\\":\\"GOOGL\\",\\"sentiment\\":\\"bearish\\",\\"author\\":{\\"authorName\\":\\"Author2\\",\\"isProfessional\\":false}}]"])
</script>
</body>
</html>
"""

SAMPLE_HTML_NO_PITCHES = """
<!DOCTYPE html>
<html>
<head><title>Yellowbrick</title></head>
<body>
<script>self.__next_f.push([1,"some other data"])</script>
<div>No pitches here</div>
</body>
</html>
"""

SAMPLE_HTML_EMPTY = """
<!DOCTYPE html>
<html>
<body>
<p>Empty page</p>
</body>
</html>
"""


@pytest.fixture
def mock_playwright():
    """Create mock Playwright objects."""
    with patch("yellowbrick.scraper.sync_playwright") as mock_sync:
        # Create mock chain
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        # The scraper uses sync_playwright().start(), not context manager
        mock_sync.return_value.start.return_value = mock_playwright_instance

        yield {
            "sync_playwright": mock_sync,
            "playwright": mock_playwright_instance,
            "browser": mock_browser,
            "context": mock_context,
            "page": mock_page,
        }


@pytest.fixture
def sample_cookies_file(tmp_path):
    """Create sample cookie file."""
    cookie_file = tmp_path / "cookies.json"
    cookies = [
        {
            "name": "session_token",
            "value": "test_token",
            "domain": ".joinyellowbrick.com",
            "path": "/",
        }
    ]
    cookie_file.write_text(json.dumps(cookies))
    return cookie_file


class TestScraperInit:
    """Test cases for YellowbrickScraper initialization."""

    def test_init_with_auth(self, sample_cookies_file):
        """Should initialize with YellowbrickAuth."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        assert scraper.auth is auth
        assert scraper.headless is True  # Default
        assert scraper.timeout == 30000  # Default

    def test_init_headless_option(self, sample_cookies_file):
        """Should accept headless configuration."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth, headless=False)

        assert scraper.headless is False

    def test_init_timeout_option(self, sample_cookies_file):
        """Should accept timeout configuration."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth, timeout=60000)

        assert scraper.timeout == 60000


class TestExtractJsonFromScripts:
    """Test cases for extracting JSON from script tags."""

    def test_extract_finds_initial_stock_pitches(self, sample_cookies_file):
        """Should find and parse initialStockPitches JSON."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        # Mock page with script content
        mock_page = MagicMock()
        mock_page.content.return_value = SAMPLE_HTML_WITH_PITCHES

        result = scraper._extract_json_from_scripts(mock_page)

        assert len(result) == 1
        assert result[0]["id"] == 126819
        assert result[0]["givenTicker"] == "DBO.TO"

    def test_extract_multiple_pitches(self, sample_cookies_file):
        """Should extract multiple pitches from JSON array."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        mock_page = MagicMock()
        mock_page.content.return_value = SAMPLE_HTML_MULTIPLE_PITCHES

        result = scraper._extract_json_from_scripts(mock_page)

        assert len(result) == 2
        assert result[0]["givenTicker"] == "AAPL"
        assert result[1]["givenTicker"] == "GOOGL"

    def test_extract_returns_empty_list_when_no_pitches(self, sample_cookies_file):
        """Should return empty list when no pitches found."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        mock_page = MagicMock()
        mock_page.content.return_value = SAMPLE_HTML_NO_PITCHES

        result = scraper._extract_json_from_scripts(mock_page)

        assert result == []

    def test_extract_handles_empty_page(self, sample_cookies_file):
        """Should handle empty page gracefully."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        mock_page = MagicMock()
        mock_page.content.return_value = SAMPLE_HTML_EMPTY

        result = scraper._extract_json_from_scripts(mock_page)

        assert result == []

    def test_extract_handles_malformed_json(self, sample_cookies_file):
        """Should handle malformed JSON gracefully."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        malformed_html = """
        <script>
        self.__next_f.push([1,"initialStockPitches\\":[{malformed json here}]"])
        </script>
        """

        mock_page = MagicMock()
        mock_page.content.return_value = malformed_html

        result = scraper._extract_json_from_scripts(mock_page)

        # Should return empty list on parse error, not crash
        assert result == []


class TestScrapeFeed:
    """Test cases for scrape_feed method."""

    def test_scrape_feed_returns_pitch_list(
        self, sample_cookies_file, mock_playwright
    ):
        """Should return list of Pitch objects."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.models import Pitch
        from yellowbrick.scraper import YellowbrickScraper

        # Setup mocks
        mock_playwright["page"].content.return_value = SAMPLE_HTML_WITH_PITCHES
        mock_playwright["page"].wait_for_selector = MagicMock()

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        result = scraper.scrape_feed(
            "https://www.joinyellowbrick.com/feeds/big_money",
            feed_type="big_money",
        )

        assert len(result) == 1
        assert isinstance(result[0], Pitch)
        assert result[0].ticker == "DBO.TO"

    def test_scrape_feed_navigates_to_url(
        self, sample_cookies_file, mock_playwright
    ):
        """Should navigate to the provided URL."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        mock_playwright["page"].content.return_value = SAMPLE_HTML_WITH_PITCHES
        mock_playwright["page"].wait_for_selector = MagicMock()

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        feed_url = "https://www.joinyellowbrick.com/feeds/elite"
        scraper.scrape_feed(feed_url, feed_type="elite")

        mock_playwright["page"].goto.assert_called_with(
            feed_url, timeout=30000
        )

    def test_scrape_feed_injects_cookies(
        self, sample_cookies_file, mock_playwright
    ):
        """Should inject cookies into browser context."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        mock_playwright["page"].content.return_value = SAMPLE_HTML_WITH_PITCHES
        mock_playwright["page"].wait_for_selector = MagicMock()

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        scraper.scrape_feed(
            "https://www.joinyellowbrick.com/feeds/big_money",
            feed_type="big_money",
        )

        # Should have called add_cookies on context
        mock_playwright["context"].add_cookies.assert_called_once()

    def test_scrape_feed_launches_headless_browser(
        self, sample_cookies_file, mock_playwright
    ):
        """Should launch browser in headless mode by default."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        mock_playwright["page"].content.return_value = SAMPLE_HTML_WITH_PITCHES
        mock_playwright["page"].wait_for_selector = MagicMock()

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth, headless=True)

        scraper.scrape_feed(
            "https://www.joinyellowbrick.com/feeds/big_money",
            feed_type="big_money",
        )

        mock_playwright["playwright"].chromium.launch.assert_called_with(
            headless=True
        )

    def test_scrape_feed_launches_visible_browser(
        self, sample_cookies_file, mock_playwright
    ):
        """Should launch visible browser when headless=False."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        mock_playwright["page"].content.return_value = SAMPLE_HTML_WITH_PITCHES
        mock_playwright["page"].wait_for_selector = MagicMock()

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth, headless=False)

        scraper.scrape_feed(
            "https://www.joinyellowbrick.com/feeds/big_money",
            feed_type="big_money",
        )

        mock_playwright["playwright"].chromium.launch.assert_called_with(
            headless=False
        )

    def test_scrape_feed_returns_empty_on_no_pitches(
        self, sample_cookies_file, mock_playwright
    ):
        """Should return empty list when no pitches found."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        mock_playwright["page"].content.return_value = SAMPLE_HTML_NO_PITCHES
        mock_playwright["page"].wait_for_selector = MagicMock()

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        result = scraper.scrape_feed(
            "https://www.joinyellowbrick.com/feeds/big_money",
            feed_type="big_money",
        )

        assert result == []

    def test_scrape_feed_waits_for_content(
        self, sample_cookies_file, mock_playwright
    ):
        """Should wait for page content to load."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        mock_playwright["page"].content.return_value = SAMPLE_HTML_WITH_PITCHES
        mock_playwright["page"].wait_for_selector = MagicMock()

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth, timeout=45000)

        scraper.scrape_feed(
            "https://www.joinyellowbrick.com/feeds/big_money",
            feed_type="big_money",
        )

        # Should wait for article selector
        mock_playwright["page"].wait_for_selector.assert_called_with(
            "article", timeout=45000
        )


class TestScrapeFeedErrorHandling:
    """Test cases for error handling in scrape_feed."""

    def test_scrape_feed_handles_timeout(
        self, sample_cookies_file, mock_playwright
    ):
        """Should handle timeout gracefully."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        mock_playwright["page"].goto.side_effect = PlaywrightTimeout("Timeout")

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        result = scraper.scrape_feed(
            "https://www.joinyellowbrick.com/feeds/big_money",
            feed_type="big_money",
        )

        # Should return empty list on timeout
        assert result == []

    def test_scrape_feed_handles_navigation_error(
        self, sample_cookies_file, mock_playwright
    ):
        """Should handle navigation errors gracefully."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        mock_playwright["page"].goto.side_effect = Exception("Network error")

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        result = scraper.scrape_feed(
            "https://www.joinyellowbrick.com/feeds/big_money",
            feed_type="big_money",
        )

        assert result == []

    def test_scrape_feed_handles_wait_timeout(
        self, sample_cookies_file, mock_playwright
    ):
        """Should handle wait_for_selector timeout."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        mock_playwright["page"].wait_for_selector.side_effect = PlaywrightTimeout(
            "Wait timeout"
        )
        mock_playwright["page"].content.return_value = SAMPLE_HTML_NO_PITCHES

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        # Should still try to extract pitches even if wait times out
        result = scraper.scrape_feed(
            "https://www.joinyellowbrick.com/feeds/big_money",
            feed_type="big_money",
        )

        assert isinstance(result, list)


class TestScraperCleanup:
    """Test cases for resource cleanup."""

    def test_close_cleans_up_resources(
        self, sample_cookies_file, mock_playwright
    ):
        """Should close browser on cleanup."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        mock_playwright["page"].content.return_value = SAMPLE_HTML_WITH_PITCHES
        mock_playwright["page"].wait_for_selector = MagicMock()

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        # Scrape to initialize browser
        scraper.scrape_feed(
            "https://www.joinyellowbrick.com/feeds/big_money",
            feed_type="big_money",
        )

        scraper.close()

        mock_playwright["browser"].close.assert_called_once()

    def test_close_handles_no_browser(self, sample_cookies_file):
        """Should handle close when browser never initialized."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        # Should not raise exception
        scraper.close()

    def test_context_manager_support(
        self, sample_cookies_file, mock_playwright
    ):
        """Should support context manager for automatic cleanup."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        mock_playwright["page"].content.return_value = SAMPLE_HTML_WITH_PITCHES
        mock_playwright["page"].wait_for_selector = MagicMock()

        auth = YellowbrickAuth(sample_cookies_file)

        with YellowbrickScraper(auth) as scraper:
            scraper.scrape_feed(
                "https://www.joinyellowbrick.com/feeds/big_money",
                feed_type="big_money",
            )

        mock_playwright["browser"].close.assert_called_once()


class TestIntegrationWithParser:
    """Test cases for integration with parser module."""

    def test_scrape_returns_parsed_pitch_objects(
        self, sample_cookies_file, mock_playwright
    ):
        """Should return properly parsed Pitch objects."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.models import Pitch
        from yellowbrick.scraper import YellowbrickScraper

        mock_playwright["page"].content.return_value = SAMPLE_HTML_WITH_PITCHES
        mock_playwright["page"].wait_for_selector = MagicMock()

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        result = scraper.scrape_feed(
            "https://www.joinyellowbrick.com/feeds/big_money",
            feed_type="big_money",
        )

        assert len(result) == 1
        pitch = result[0]

        assert isinstance(pitch, Pitch)
        assert pitch.ticker == "DBO.TO"
        assert pitch.feed_type == "big_money"
        assert pitch.pitch_id == "126819"
        assert pitch.author == "Test Author"
        assert pitch.pitch_type == "bullish"

    def test_scrape_feed_type_propagates_to_pitches(
        self, sample_cookies_file, mock_playwright
    ):
        """Should pass feed_type to parser for all pitches."""
        from yellowbrick.authenticator import YellowbrickAuth
        from yellowbrick.scraper import YellowbrickScraper

        mock_playwright["page"].content.return_value = SAMPLE_HTML_MULTIPLE_PITCHES
        mock_playwright["page"].wait_for_selector = MagicMock()

        auth = YellowbrickAuth(sample_cookies_file)
        scraper = YellowbrickScraper(auth)

        result = scraper.scrape_feed(
            "https://www.joinyellowbrick.com/feeds/elite",
            feed_type="elite",
        )

        assert len(result) == 2
        assert all(pitch.feed_type == "elite" for pitch in result)
