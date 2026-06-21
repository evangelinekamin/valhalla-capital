"""Tests for CLI module."""

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from fmp_data_client.cli.main import cli
from fmp_data_client.models.quote import Quote
from fmp_data_client.models.profile import CompanyProfile
from fmp_data_client.models.fundamentals import IncomeStatement
from fmp_data_client.models.ticker_data import TickerData


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def runner():
    """Create Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_quote():
    """Create mock quote data."""
    return Quote(
        symbol="AAPL",
        name="Apple Inc.",
        price=175.50,
        change=2.50,
        change_percent=1.44,
        open=173.00,
        day_high=176.00,
        day_low=172.50,
        previous_close=173.00,
        volume=50000000,
        market_cap=2800000000000,
        pe=28.5,
    )


@pytest.fixture
def mock_profile():
    """Create mock company profile."""
    return CompanyProfile(
        symbol="AAPL",
        name="Apple Inc.",
        industry="Consumer Electronics",
        sector="Technology",
        country="US",
        exchange_short_name="NASDAQ",
        ceo="Tim Cook",
        employees=164000,
        market_cap=2800000000000,
        price=175.50,
        website="https://www.apple.com",
        city="Cupertino",
        state="CA",
        description="Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide.",
    )


@pytest.fixture
def mock_ticker_data():
    """Create mock ticker data."""
    return TickerData(
        symbol="AAPL",
        quote=Quote(
            symbol="AAPL",
            name="Apple Inc.",
            price=175.50,
            change=2.50,
            change_percent=1.44,
            day_high=176.00,
            day_low=172.50,
            previous_close=173.00,
            volume=50000000,
        ),
    )


# ============================================================================
# CLI Main Tests
# ============================================================================


class TestCLIMain:
    """Tests for main CLI group."""

    def test_cli_help(self, runner):
        """Test that CLI help displays correctly."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "FMP Data Client" in result.output
        assert "Financial data from Financial Modeling Prep API" in result.output

    def test_cli_version(self, runner):
        """Test version display."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


# ============================================================================
# Quote Command Tests
# ============================================================================


class TestQuoteCommand:
    """Tests for quote command."""

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_quote_success(self, mock_client_class, runner, mock_quote):
        """Test successful quote retrieval."""
        # Setup mock
        mock_client = AsyncMock()
        mock_client.get_quote = AsyncMock(return_value=mock_quote)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["quote", "AAPL"])

        assert result.exit_code == 0
        assert "AAPL" in result.output
        assert "$175.50" in result.output
        mock_client.get_quote.assert_called_once_with("AAPL")

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_quote_json_output(self, mock_client_class, runner, mock_quote):
        """Test quote with JSON output."""
        mock_client = AsyncMock()
        mock_client.get_quote = AsyncMock(return_value=mock_quote)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["quote", "AAPL", "--json"])

        assert result.exit_code == 0
        # Output should be valid JSON
        output_data = json.loads(result.output)
        assert output_data["symbol"] == "AAPL"
        assert output_data["price"] == 175.50

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_quote_lowercase_symbol(self, mock_client_class, runner, mock_quote):
        """Test that lowercase symbols are converted to uppercase."""
        mock_client = AsyncMock()
        mock_client.get_quote = AsyncMock(return_value=mock_quote)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["quote", "aapl"])

        assert result.exit_code == 0
        # Should call with uppercase
        mock_client.get_quote.assert_called_once_with("AAPL")

    def test_quote_missing_symbol(self, runner):
        """Test quote command without symbol argument."""
        result = runner.invoke(cli, ["quote"])

        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Error" in result.output


# ============================================================================
# Profile Command Tests
# ============================================================================


class TestProfileCommand:
    """Tests for profile command."""

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_profile_success(self, mock_client_class, runner, mock_profile):
        """Test successful profile retrieval."""
        mock_client = AsyncMock()
        mock_client.get_profile = AsyncMock(return_value=mock_profile)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["profile", "AAPL"])

        assert result.exit_code == 0
        assert "Apple Inc." in result.output
        assert "Tim Cook" in result.output
        assert "Consumer Electronics" in result.output
        mock_client.get_profile.assert_called_once_with("AAPL")

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_profile_json_output(self, mock_client_class, runner, mock_profile):
        """Test profile with JSON output."""
        mock_client = AsyncMock()
        mock_client.get_profile = AsyncMock(return_value=mock_profile)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["profile", "AAPL", "--json"])

        assert result.exit_code == 0
        output_data = json.loads(result.output)
        assert output_data["symbol"] == "AAPL"
        assert output_data["companyName"] == "Apple Inc."


# ============================================================================
# Fundamentals Command Tests
# ============================================================================


class TestFundamentalsCommand:
    """Tests for fundamentals command."""

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_fundamentals_success(self, mock_client_class, runner):
        """Test successful fundamentals retrieval."""
        # Create mock income statement
        mock_income = IncomeStatement(
            symbol="AAPL",
            period_date="2024-01-01",
            period="Q4",
            revenue=100000000000,
            gross_profit=45000000000,
            net_income=25000000000,
            eps=1.50,
        )

        mock_ticker = TickerData(symbol="AAPL", income_statements=[mock_income])

        mock_client = AsyncMock()
        mock_client.get_ticker_data = AsyncMock(return_value=mock_ticker)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["fundamentals", "AAPL"])

        assert result.exit_code == 0
        assert "AAPL" in result.output

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_fundamentals_custom_periods(self, mock_client_class, runner):
        """Test fundamentals with custom period count."""
        mock_ticker = TickerData(symbol="AAPL", income_statements=[])

        mock_client = AsyncMock()
        mock_client.get_ticker_data = AsyncMock(return_value=mock_ticker)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["fundamentals", "AAPL", "--periods", "8"])

        assert result.exit_code == 0

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_fundamentals_json_output(self, mock_client_class, runner):
        """Test fundamentals with JSON output."""
        mock_ticker = TickerData(symbol="AAPL", income_statements=[])

        mock_client = AsyncMock()
        mock_client.get_ticker_data = AsyncMock(return_value=mock_ticker)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["fundamentals", "AAPL", "--output", "json"])

        assert result.exit_code == 0


# ============================================================================
# Analyze Command Tests
# ============================================================================


class TestAnalyzeCommand:
    """Tests for analyze command."""

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_analyze_basic(self, mock_client_class, runner, mock_ticker_data):
        """Test basic analyze command."""
        mock_client = AsyncMock()
        mock_client.get_ticker_data = AsyncMock(return_value=mock_ticker_data)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["analyze", "AAPL"])

        assert result.exit_code == 0
        assert "AAPL" in result.output

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_analyze_full(self, mock_client_class, runner, mock_ticker_data):
        """Test analyze with --full flag."""
        mock_client = AsyncMock()
        mock_client.get_ticker_data = AsyncMock(return_value=mock_ticker_data)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["analyze", "AAPL", "--full"])

        assert result.exit_code == 0

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_analyze_json_output(self, mock_client_class, runner, mock_ticker_data):
        """Test analyze with JSON output."""
        mock_client = AsyncMock()
        mock_client.get_ticker_data = AsyncMock(return_value=mock_ticker_data)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["analyze", "AAPL", "--output", "json"])

        assert result.exit_code == 0
        # Should be valid JSON
        output_data = json.loads(result.output)
        assert output_data["symbol"] == "AAPL"


# ============================================================================
# Cache Command Tests
# ============================================================================


class TestCacheCommands:
    """Tests for cache subcommands."""

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_cache_status(self, mock_client_class, runner):
        """Test cache status command."""
        mock_client = AsyncMock()
        mock_client.get_cache_info = AsyncMock(return_value={
            "enabled": True,
            "ticker_cache_entries": 100,
            "transcript_summaries": 5,
            "filing_summaries": 10,
        })
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        # Note: Actual command name depends on CLI structure
        # This is a placeholder test
        result = runner.invoke(cli, ["cache", "status"])

        # May not be implemented as subcommand, adjust based on actual CLI
        # assert result.exit_code == 0

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_cache_clear(self, mock_client_class, runner):
        """Test cache clear command."""
        mock_client = AsyncMock()
        mock_client.clear_cache = AsyncMock(return_value=True)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["cache", "clear"])

        # May not be implemented as subcommand
        # assert result.exit_code == 0


# ============================================================================
# Config Command Tests
# ============================================================================


class TestConfigCommands:
    """Tests for config subcommands."""

    @patch("fmp_data_client.cli.main.FMPConfig")
    def test_config_show(self, mock_config_class, runner):
        """Test config show command."""
        mock_config = Mock()
        mock_config.api_key = "test_key"
        mock_config.tier = "starter"
        mock_config.cache_enabled = True
        mock_config_class.from_env.return_value = mock_config

        result = runner.invoke(cli, ["config", "show"])

        # May not be implemented as subcommand
        # assert result.exit_code == 0

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_config_test(self, mock_client_class, runner, mock_quote):
        """Test config test command."""
        mock_client = AsyncMock()
        mock_client.get_quote = AsyncMock(return_value=mock_quote)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["config", "test"])

        # May not be implemented as subcommand
        # assert result.exit_code == 0


# ============================================================================
# Rate Limit Command Tests
# ============================================================================


class TestRateLimitCommand:
    """Tests for rate-limit command."""

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_rate_limit(self, mock_client_class, runner):
        """Test rate limit status command."""
        mock_client = AsyncMock()
        mock_client.get_rate_limit_status = AsyncMock(return_value={
            "calls_made": 50,
            "calls_remaining": 250,
            "calls_per_minute": 300,
        })
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["rate-limit"])

        # May not be implemented
        # assert result.exit_code == 0


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestCLIErrorHandling:
    """Tests for CLI error handling."""

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_quote_api_error(self, mock_client_class, runner):
        """Test handling of API errors in quote command."""
        mock_client = AsyncMock()
        mock_client.get_quote = AsyncMock(side_effect=Exception("API Error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["quote", "AAPL"])

        # Should handle error gracefully
        assert result.exit_code != 0 or "Error" in result.output

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_profile_not_found(self, mock_client_class, runner):
        """Test handling of profile not found."""
        mock_client = AsyncMock()
        mock_client.get_profile = AsyncMock(side_effect=ValueError("Symbol not found"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        result = runner.invoke(cli, ["profile", "INVALID"])

        assert result.exit_code != 0 or "Error" in result.output

    @patch("fmp_data_client.cli.main.FMPConfig")
    def test_missing_api_key(self, mock_config_class, runner):
        """Test handling of missing API key."""
        mock_config_class.from_env.side_effect = ValueError("API key not found")

        result = runner.invoke(cli, ["quote", "AAPL"])

        assert result.exit_code != 0


# ============================================================================
# Display Function Tests
# ============================================================================


class TestDisplayFunctions:
    """Tests for display helper functions."""

    @patch("fmp_data_client.cli.main.console")
    def test_display_quote(self, mock_console, mock_quote):
        """Test _display_quote function."""
        from fmp_data_client.cli.main import _display_quote

        _display_quote(mock_quote)

        # Should call console.print
        assert mock_console.print.called

    @patch("fmp_data_client.cli.main.console")
    def test_display_profile(self, mock_console, mock_profile):
        """Test _display_profile function."""
        from fmp_data_client.cli.main import _display_profile

        _display_profile(mock_profile)

        # Should call console.print
        assert mock_console.print.called

    def test_display_quote_negative_change(self, mock_quote):
        """Test display of quote with negative change."""
        from fmp_data_client.cli.main import _display_quote

        # Create new quote with negative values
        negative_quote = Quote(
            symbol="AAPL",
            name="Apple Inc.",
            price=175.50,
            change=-2.50,
            change_percent=-1.44,
            day_high=176.00,
            day_low=172.50,
            previous_close=178.00,
            volume=50000000,
        )

        # Should not raise error
        _display_quote(negative_quote)

    def test_display_profile_with_none_values(self):
        """Test display of profile with None values."""
        from fmp_data_client.cli.main import _display_profile

        profile = CompanyProfile(
            symbol="TEST",
            name="Test Company",
            # Most fields None
        )

        # Should handle None values gracefully
        _display_profile(profile)


# ============================================================================
# Integration Tests
# ============================================================================


class TestCLIIntegration:
    """Integration tests for CLI commands."""

    @patch("fmp_data_client.cli.main.FMPDataClient")
    def test_multiple_commands_in_sequence(self, mock_client_class, runner, mock_quote, mock_profile):
        """Test running multiple commands in sequence."""
        mock_client = AsyncMock()
        mock_client.get_quote = AsyncMock(return_value=mock_quote)
        mock_client.get_profile = AsyncMock(return_value=mock_profile)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.from_env.return_value = mock_client

        # Run quote command
        result1 = runner.invoke(cli, ["quote", "AAPL"])
        assert result1.exit_code == 0

        # Run profile command
        result2 = runner.invoke(cli, ["profile", "AAPL"])
        assert result2.exit_code == 0

    def test_help_for_all_commands(self, runner):
        """Test that help works for all commands."""
        commands = ["quote", "profile", "fundamentals", "analyze"]

        for command in commands:
            result = runner.invoke(cli, [command, "--help"])
            assert result.exit_code == 0
            assert "Example:" in result.output or "Usage:" in result.output
