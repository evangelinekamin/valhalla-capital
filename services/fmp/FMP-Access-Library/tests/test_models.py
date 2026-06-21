"""Tests for data models."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from fmp_data_client.models.quote import Quote
from fmp_data_client.models.profile import CompanyProfile, Executive
from fmp_data_client.models.fundamentals import (
    IncomeStatement,
    BalanceSheet,
    CashFlowStatement,
    KeyMetrics,
)
from fmp_data_client.models.analyst import AnalystEstimate, PriceTarget
from fmp_data_client.models.ownership import InstitutionalHolder
from fmp_data_client.models.events import DividendRecord
from fmp_data_client.models.news import NewsArticle
from fmp_data_client.models.request import DataRequest
from fmp_data_client.models.ticker_data import TickerData

from tests.fixtures.mock_responses import (
    MOCK_QUOTE_RESPONSE,
    MOCK_PROFILE_RESPONSE,
    MOCK_INCOME_STATEMENT_RESPONSE,
    MOCK_BALANCE_SHEET_RESPONSE,
    MOCK_CASH_FLOW_RESPONSE,
    MOCK_KEY_METRICS_RESPONSE,
    MOCK_ANALYST_ESTIMATE_RESPONSE,
    MOCK_PRICE_TARGET_RESPONSE,
    MOCK_INSTITUTIONAL_HOLDER_RESPONSE,
    MOCK_DIVIDEND_RESPONSE,
    MOCK_NEWS_RESPONSE,
)


class TestQuote:
    """Test Quote model."""

    def test_parse_valid_quote(self) -> None:
        """Test parsing a valid quote response."""
        quote = Quote(**MOCK_QUOTE_RESPONSE[0])

        assert quote.symbol == "AAPL"
        assert quote.name == "Apple Inc."
        assert quote.price == 185.50
        assert quote.change_percent == 1.25
        assert quote.market_cap == 2850000000000
        assert quote.exchange == "NASDAQ"

    def test_quote_formatted_properties(self) -> None:
        """Test Quote formatted property methods."""
        quote = Quote(**MOCK_QUOTE_RESPONSE[0])

        # Test change direction
        assert quote.is_positive_change is True

        # Test market cap value
        assert quote.market_cap == 2850000000000

    def test_quote_missing_optional_fields(self) -> None:
        """Test Quote with missing optional fields."""
        minimal_quote = {
            "symbol": "TEST",
            "price": 100.0,
            "volume": 1000000,
            "change": 1.0,
            "changePercentage": 1.0,
            "dayHigh": 101.0,
            "dayLow": 99.0,
            "previousClose": 99.0,
        }
        quote = Quote(**minimal_quote)
        assert quote.symbol == "TEST"
        assert quote.price == 100.0
        assert quote.name is None


class TestCompanyProfile:
    """Test CompanyProfile model."""

    def test_parse_valid_profile(self) -> None:
        """Test parsing a valid company profile."""
        profile = CompanyProfile(**MOCK_PROFILE_RESPONSE[0])

        assert profile.symbol == "AAPL"
        assert profile.name == "Apple Inc."
        assert profile.industry == "Consumer Electronics"
        assert profile.sector == "Technology"
        assert profile.ceo == "Timothy Cook"
        assert profile.website == "https://www.apple.com"
        assert profile.country == "US"
        assert profile.employees == 164000

    def test_profile_formatted_properties(self) -> None:
        """Test CompanyProfile formatted properties."""
        profile = CompanyProfile(**MOCK_PROFILE_RESPONSE[0])

        # Test market cap formatting
        assert "T" in profile.market_cap_formatted or "B" in profile.market_cap_formatted

        # Test full address formatting
        assert profile.full_address is not None
        assert "Cupertino" in profile.full_address

    def test_profile_is_trading(self) -> None:
        """Test is_actively_trading property."""
        profile = CompanyProfile(**MOCK_PROFILE_RESPONSE[0])
        assert profile.is_actively_trading is True


class TestIncomeStatement:
    """Test IncomeStatement model."""

    def test_parse_valid_income_statement(self) -> None:
        """Test parsing a valid income statement."""
        stmt = IncomeStatement(**MOCK_INCOME_STATEMENT_RESPONSE[0])

        assert stmt.symbol == "AAPL"
        assert stmt.period_date.year == 2023
        assert stmt.period_date.month == 9
        assert stmt.revenue == 383285000000
        assert stmt.gross_profit == 169148000000
        assert stmt.net_income == 96995000000
        assert stmt.eps == 6.16

    def test_income_statement_margins(self) -> None:
        """Test margin calculations."""
        stmt = IncomeStatement(**MOCK_INCOME_STATEMENT_RESPONSE[0])

        assert stmt.gross_profit_ratio > 0.40
        assert stmt.operating_income_ratio > 0.25
        assert stmt.net_income_ratio > 0.20

    def test_income_statement_period(self) -> None:
        """Test period information."""
        stmt = IncomeStatement(**MOCK_INCOME_STATEMENT_RESPONSE[0])
        assert stmt.period == "FY"  # FY indicates annual period


class TestBalanceSheet:
    """Test BalanceSheet model."""

    def test_parse_valid_balance_sheet(self) -> None:
        """Test parsing a valid balance sheet."""
        bs = BalanceSheet(**MOCK_BALANCE_SHEET_RESPONSE[0])

        assert bs.symbol == "AAPL"
        assert bs.total_assets == 352583000000
        assert bs.total_liabilities == 268597000000
        assert bs.total_stockholders_equity == 62146000000

    def test_balance_sheet_ratios(self) -> None:
        """Test balance sheet ratio calculations."""
        bs = BalanceSheet(**MOCK_BALANCE_SHEET_RESPONSE[0])

        # Current ratio
        current_ratio = bs.total_current_assets / bs.total_current_liabilities
        assert current_ratio > 1.0

        # Debt to equity
        debt_to_equity = bs.total_debt / bs.total_stockholders_equity
        assert debt_to_equity > 0


class TestCashFlowStatement:
    """Test CashFlowStatement model."""

    def test_parse_valid_cash_flow(self) -> None:
        """Test parsing a valid cash flow statement."""
        cf = CashFlowStatement(**MOCK_CASH_FLOW_RESPONSE[0])

        assert cf.symbol == "AAPL"
        assert cf.operating_cash_flow == 110543000000
        assert cf.capital_expenditure == -10959000000
        assert cf.free_cash_flow == 99584000000

    def test_cash_flow_calculations(self) -> None:
        """Test cash flow calculations."""
        cf = CashFlowStatement(**MOCK_CASH_FLOW_RESPONSE[0])

        # FCF should be operating cash flow minus capex
        expected_fcf = cf.operating_cash_flow + cf.capital_expenditure
        assert cf.free_cash_flow == expected_fcf


class TestKeyMetrics:
    """Test KeyMetrics model."""

    def test_parse_valid_key_metrics(self) -> None:
        """Test parsing valid key metrics."""
        metrics = KeyMetrics(**MOCK_KEY_METRICS_RESPONSE[0])

        assert metrics.symbol == "AAPL"
        assert metrics.pe_ratio > 0
        assert metrics.price_to_sales > 0
        assert metrics.roe > 0
        assert metrics.debt_to_equity > 0

    def test_key_metrics_valuation(self) -> None:
        """Test valuation metrics."""
        metrics = KeyMetrics(**MOCK_KEY_METRICS_RESPONSE[0])

        assert metrics.market_cap > 0
        assert metrics.enterprise_value > 0
        assert metrics.ev_to_ebitda > 0


class TestAnalystEstimate:
    """Test AnalystEstimate model."""

    def test_parse_valid_analyst_estimate(self) -> None:
        """Test parsing valid analyst estimates."""
        estimate = AnalystEstimate(**MOCK_ANALYST_ESTIMATE_RESPONSE[0])

        assert estimate.symbol == "AAPL"
        assert estimate.estimated_revenue_avg > 0
        assert estimate.estimated_eps_avg > 0
        assert estimate.number_analyst_estimated_eps > 0

    def test_analyst_estimate_ranges(self) -> None:
        """Test estimate ranges are logical."""
        estimate = AnalystEstimate(**MOCK_ANALYST_ESTIMATE_RESPONSE[0])

        # Low should be less than average, average less than high
        assert estimate.estimated_revenue_low <= estimate.estimated_revenue_avg
        assert estimate.estimated_revenue_avg <= estimate.estimated_revenue_high

        assert estimate.estimated_eps_low <= estimate.estimated_eps_avg
        assert estimate.estimated_eps_avg <= estimate.estimated_eps_high


class TestPriceTarget:
    """Test PriceTarget model."""

    def test_parse_valid_price_target(self) -> None:
        """Test parsing valid price target."""
        target = PriceTarget(**MOCK_PRICE_TARGET_RESPONSE[0])

        assert target.symbol == "AAPL"
        assert target.analyst_name == "John Smith"
        assert target.analyst_company == "Goldman Sachs"
        assert target.price_target == 210.0
        assert target.price_when_posted == 185.50

    def test_price_target_upside(self) -> None:
        """Test upside calculation."""
        target = PriceTarget(**MOCK_PRICE_TARGET_RESPONSE[0])

        # Calculate expected upside
        expected_upside = (
            (target.price_target - target.price_when_posted) / target.price_when_posted
        ) * 100

        assert target.upside_potential == pytest.approx(expected_upside, rel=0.01)


class TestInstitutionalHolder:
    """Test InstitutionalHolder model."""

    def test_parse_valid_holder(self) -> None:
        """Test parsing valid institutional holder."""
        holder = InstitutionalHolder(**MOCK_INSTITUTIONAL_HOLDER_RESPONSE[0])

        assert holder.holder == "Vanguard Group Inc"
        assert holder.shares == 1295805031
        assert holder.percent_held == 8.43
        assert holder.value == 240000000000

    def test_holder_change_type(self) -> None:
        """Test position change detection."""
        holder_increase = InstitutionalHolder(**MOCK_INSTITUTIONAL_HOLDER_RESPONSE[0])
        assert holder_increase.position_change_type == "increased"

        holder_decrease = InstitutionalHolder(**MOCK_INSTITUTIONAL_HOLDER_RESPONSE[1])
        assert holder_decrease.position_change_type == "decreased"


class TestDividendRecord:
    """Test DividendRecord model."""

    def test_parse_valid_dividend(self) -> None:
        """Test parsing valid dividend record."""
        dividend = DividendRecord(**MOCK_DIVIDEND_RESPONSE[0])

        assert dividend.dividend == 0.24
        assert dividend.adj_dividend == 0.24
        assert dividend.dividend_date is not None
        assert dividend.record_date is not None

    def test_dividend_dates(self) -> None:
        """Test dividend date relationships."""
        dividend = DividendRecord(**MOCK_DIVIDEND_RESPONSE[0])

        # Declaration should be before record date
        assert dividend.declaration_date < dividend.record_date
        # Record date should be before payment date
        assert dividend.record_date < dividend.payment_date


class TestNewsArticle:
    """Test NewsArticle model."""

    def test_parse_valid_news(self) -> None:
        """Test parsing valid news article."""
        news = NewsArticle(**MOCK_NEWS_RESPONSE[0])

        assert news.symbol == "AAPL"
        assert news.title == "Apple Reports Record Q1 Earnings"
        assert news.site == "Reuters"
        assert isinstance(news.published_date, datetime)

    def test_news_text_preview(self) -> None:
        """Test news text preview."""
        news = NewsArticle(**MOCK_NEWS_RESPONSE[0])
        preview = news.text_preview(50)

        assert len(preview) <= 53  # 50 chars + "..."
        assert preview.endswith("...")


class TestDataRequest:
    """Test DataRequest model."""

    def test_minimal_request(self) -> None:
        """Test creating minimal data request."""
        request = DataRequest(symbol="AAPL")

        assert request.symbol == "AAPL"
        assert request.include_quote is False
        assert request.include_profile is False

    def test_full_request(self) -> None:
        """Test creating comprehensive data request."""
        request = DataRequest(
            symbol="AAPL",
            include_quote=True,
            include_profile=True,
            include_fundamentals=True,
            fundamentals_periods=4,
        )

        assert request.symbol == "AAPL"
        assert request.include_quote is True
        assert request.include_profile is True
        assert request.include_fundamentals is True
        assert request.fundamentals_periods == 4

    def test_enable_full_analysis(self) -> None:
        """Test enabling all analysis options."""
        request = DataRequest(symbol="AAPL")
        request.enable_full_analysis()

        assert request.include_quote is True
        assert request.include_profile is True
        assert request.include_fundamentals is True
        assert request.include_dcf is True
        assert request.include_enterprise_value is True
        assert request.include_analyst_estimates is True
        assert request.include_institutional_holders is True
        assert request.include_insider_trades is True
        assert request.include_historical_prices is True

    def test_validate_periods(self) -> None:
        """Test period validation."""
        # Valid periods
        request = DataRequest(symbol="AAPL", fundamentals_periods=4)
        assert request.fundamentals_periods == 4

        # Invalid periods should raise error
        with pytest.raises(ValidationError):
            DataRequest(symbol="AAPL", fundamentals_periods=101)


class TestTickerData:
    """Test TickerData aggregator model."""

    def test_create_empty_ticker_data(self) -> None:
        """Test creating empty ticker data."""
        data = TickerData(symbol="AAPL")

        assert data.symbol == "AAPL"
        assert data.quote is None
        assert data.profile is None
        assert data.income_statements == []

    def test_ticker_data_with_quote(self) -> None:
        """Test ticker data with quote."""
        quote = Quote(**MOCK_QUOTE_RESPONSE[0])
        data = TickerData(symbol="AAPL", quote=quote)

        assert data.quote is not None
        assert data.quote.symbol == "AAPL"
        assert data.quote.price == 185.50

    def test_get_latest_methods(self) -> None:
        """Test get_latest helper methods."""
        income_stmt = IncomeStatement(**MOCK_INCOME_STATEMENT_RESPONSE[0])
        balance_sheet = BalanceSheet(**MOCK_BALANCE_SHEET_RESPONSE[0])
        cash_flow = CashFlowStatement(**MOCK_CASH_FLOW_RESPONSE[0])

        data = TickerData(
            symbol="AAPL",
            income_statements=[income_stmt],
            balance_sheets=[balance_sheet],
            cash_flow_statements=[cash_flow],
        )

        assert data.get_latest_income_statement() == income_stmt
        assert data.get_latest_balance_sheet() == balance_sheet
        assert data.get_latest_cash_flow_statement() == cash_flow

    def test_ticker_data_summary(self) -> None:
        """Test summary generation."""
        quote = Quote(**MOCK_QUOTE_RESPONSE[0])
        profile = CompanyProfile(**MOCK_PROFILE_RESPONSE[0])

        data = TickerData(symbol="AAPL", quote=quote, profile=profile)
        summary = data.summary()

        assert summary["symbol"] == "AAPL"
        assert summary["has_quote"] is True
        assert summary["has_profile"] is True
