"""Tests for HTTP scraper."""

import pytest
import requests

from openinsider.scraper import OpenInsiderScraper


class TestScraperInitialization:
    """Tests for scraper initialization."""

    def test_default_initialization(self):
        """Test scraper initializes with default config."""
        scraper = OpenInsiderScraper()

        assert scraper.base_url == "http://openinsider.com"
        assert scraper.timeout == 30
        assert scraper.session is not None

    def test_custom_initialization(self):
        """Test scraper with custom parameters."""
        scraper = OpenInsiderScraper(
            base_url="http://test.com",
            timeout=60,
            user_agent="TestAgent/1.0",
        )

        assert scraper.base_url == "http://test.com"
        assert scraper.timeout == 60
        assert scraper.session.headers["User-Agent"] == "TestAgent/1.0"

    def test_context_manager(self):
        """Test scraper works as context manager."""
        with OpenInsiderScraper() as scraper:
            assert scraper.session is not None


class TestScrapeClusterBuys:
    """Tests for scrape_cluster_buys method."""

    def test_scrape_success(self, mocker, sample_html_table):
        """Test successful scrape returns cluster buys."""
        mock_response = mocker.Mock()
        mock_response.text = sample_html_table
        mock_response.status_code = 200

        mocker.patch("requests.Session.get", return_value=mock_response)

        scraper = OpenInsiderScraper()
        clusters = scraper.scrape_cluster_buys()

        assert len(clusters) == 2
        assert clusters[0].ticker == "AAPL"
        assert clusters[1].ticker == "MSFT"

    def test_scrape_timeout(self, mocker):
        """Test scrape handles timeout after retry exhaustion."""
        mocker.patch(
            "requests.Session.get",
            side_effect=requests.Timeout("Request timeout"),
        )
        mocker.patch("time.sleep")

        scraper = OpenInsiderScraper()

        with pytest.raises(requests.Timeout):
            scraper.scrape_cluster_buys()

    def test_scrape_http_error_404(self, mocker):
        """Test scrape handles 404 error."""
        mock_response = mocker.Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "404 Not Found"
        )

        mocker.patch("requests.Session.get", return_value=mock_response)

        scraper = OpenInsiderScraper()

        with pytest.raises(requests.HTTPError):
            scraper.scrape_cluster_buys()

    def test_scrape_http_error_500(self, mocker):
        """Test scrape handles 500 error after retry exhaustion."""
        mock_response = mocker.Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "500 Internal Server Error"
        )

        mocker.patch("requests.Session.get", return_value=mock_response)
        mocker.patch("time.sleep")

        scraper = OpenInsiderScraper()

        with pytest.raises(requests.HTTPError):
            scraper.scrape_cluster_buys()

    def test_scrape_connection_error(self, mocker):
        """Test scrape handles connection error after retry exhaustion."""
        mocker.patch(
            "requests.Session.get",
            side_effect=requests.ConnectionError("Connection refused"),
        )
        mocker.patch("time.sleep")

        scraper = OpenInsiderScraper()

        with pytest.raises(requests.ConnectionError):
            scraper.scrape_cluster_buys()

    def test_scrape_correct_url(self, mocker, sample_html_table):
        """Test scrape uses correct URL."""
        mock_get = mocker.patch("requests.Session.get")
        mock_response = mocker.Mock()
        mock_response.text = sample_html_table
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        scraper = OpenInsiderScraper(base_url="http://test.com")
        scraper.scrape_cluster_buys()

        mock_get.assert_called_once_with(
            "http://test.com/latest-cluster-buys",
            timeout=30,
        )

    def test_scrape_respects_timeout(self, mocker, sample_html_table):
        """Test scrape uses configured timeout."""
        mock_get = mocker.patch("requests.Session.get")
        mock_response = mocker.Mock()
        mock_response.text = sample_html_table
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        scraper = OpenInsiderScraper(timeout=60)
        scraper.scrape_cluster_buys()

        assert mock_get.call_args[1]["timeout"] == 60


class TestScrapeTickerDetails:
    """Tests for scrape_ticker_details method (Phase 2)."""

    def test_scrape_ticker_details_success(self, mocker):
        """Test ticker details scraping works (Phase 2)."""
        sample_html = """
        <table class="tinytable">
            <tbody>
                <tr>
                    <td></td><td>2026-01-28 16:00:00</td><td>2026-01-27</td>
                    <td>AAPL</td><td>John Doe</td><td>CEO</td>
                    <td>P</td><td>$100</td><td>1000</td><td>10000</td>
                    <td>+10%</td><td>$100000</td><td></td><td></td><td></td><td></td>
                </tr>
            </tbody>
        </table>
        """

        mock_response = mocker.Mock()
        mock_response.text = sample_html
        mock_response.status_code = 200
        mocker.patch("requests.Session.get", return_value=mock_response)

        scraper = OpenInsiderScraper()
        transactions = scraper.scrape_ticker_details("AAPL")

        assert len(transactions) == 1
        assert transactions[0]["insider_name"] == "John Doe"

    def test_scrape_ticker_details_does_not_sleep_internally(self, mocker):
        """Test ticker detail requests rely on caller-level rate limiting."""
        sample_html = """
        <table class="tinytable"><tbody>
            <tr>
                <td></td><td>2026-01-28 16:00:00</td><td>2026-01-27</td>
                <td>AAPL</td><td>John Doe</td><td>CEO</td>
                <td>P</td><td>$100</td><td>1000</td><td>10000</td>
                <td>+10%</td><td>$100000</td><td></td><td></td><td></td><td></td>
            </tr>
        </tbody></table>
        """

        mock_response = mocker.Mock()
        mock_response.text = sample_html
        mock_response.status_code = 200
        mocker.patch("requests.Session.get", return_value=mock_response)
        mock_sleep = mocker.patch("time.sleep")

        scraper = OpenInsiderScraper()
        scraper.scrape_ticker_details("AAPL")

        mock_sleep.assert_not_called()

    def test_scraper_close(self):
        """Test scraper session closes properly."""
        scraper = OpenInsiderScraper()
        scraper.close()

        assert scraper.session is not None


class TestRetryLogic:
    """Tests for exponential backoff retry logic."""

    def test_retry_on_connection_error_then_success(self, mocker, sample_html_table):
        """Test successful retry after transient connection failure."""
        mock_response = mocker.Mock()
        mock_response.text = sample_html_table
        mock_response.status_code = 200

        mocker.patch(
            "requests.Session.get",
            side_effect=[
                requests.ConnectionError("Connection reset"),
                mock_response,
            ],
        )
        mock_sleep = mocker.patch("time.sleep")

        scraper = OpenInsiderScraper()
        clusters = scraper.scrape_cluster_buys()

        assert len(clusters) == 2
        mock_sleep.assert_called_once_with(2.0)

    def test_retry_on_500_then_success(self, mocker, sample_html_table):
        """Test successful retry after 500 server error."""
        mock_500 = mocker.Mock()
        mock_500.status_code = 500

        mock_200 = mocker.Mock()
        mock_200.text = sample_html_table
        mock_200.status_code = 200

        mocker.patch(
            "requests.Session.get",
            side_effect=[mock_500, mock_200],
        )
        mock_sleep = mocker.patch("time.sleep")

        scraper = OpenInsiderScraper()
        clusters = scraper.scrape_cluster_buys()

        assert len(clusters) == 2
        mock_sleep.assert_called_once_with(2.0)

    def test_no_retry_on_404(self, mocker):
        """Test 4xx errors are not retried."""
        mock_response = mocker.Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")

        mocker.patch("requests.Session.get", return_value=mock_response)
        mock_sleep = mocker.patch("time.sleep")

        scraper = OpenInsiderScraper()

        with pytest.raises(requests.HTTPError):
            scraper.scrape_cluster_buys()

        mock_sleep.assert_not_called()

    def test_exponential_backoff_timing(self, mocker):
        """Test backoff doubles each attempt."""
        mocker.patch(
            "requests.Session.get",
            side_effect=requests.Timeout("Timeout"),
        )
        mock_sleep = mocker.patch("time.sleep")

        scraper = OpenInsiderScraper()

        with pytest.raises(requests.Timeout):
            scraper.scrape_cluster_buys()

        assert mock_sleep.call_count == 3
        mock_sleep.assert_any_call(2.0)
        mock_sleep.assert_any_call(4.0)
        mock_sleep.assert_any_call(8.0)
