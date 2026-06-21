"""TickerData - Main response model aggregating all data types."""

from typing import List, Optional

from pydantic import Field, field_serializer

from .analyst import AnalystEstimate, AnalystGrade, PriceTarget, PriceTargetSummary
from .base import FMPBaseModel
from .events import DividendRecord, EarningsEvent, StockSplit
from .filings import FilingSummary, SECFiling
from .fundamentals import (
    BalanceSheet,
    CashFlowStatement,
    FinancialRatios,
    FinancialScores,
    IncomeStatement,
    KeyMetrics,
)
from .news import NewsArticle
from .ownership import HolderClassification, InsiderTrade, InstitutionalHolder
from .profile import CompanyProfile, Executive
from .quote import AftermarketQuote, Quote
from .transcripts import EarningsTranscript, TranscriptSummary
from .valuation import DCFValuation, EnterpriseValue


class TickerData(FMPBaseModel):
    """Complete aggregated data for a ticker.

    This is the MAIN RESPONSE MODEL that consolidates all data types.
    All fields are optional - only requested data types are populated.
    """

    # Required field
    symbol: str = Field(..., description="Stock ticker symbol")

    # Real-time quote data
    quote: Optional[Quote] = Field(
        None,
        description="Real-time quote"
    )
    aftermarket_quote: Optional[AftermarketQuote] = Field(
        None,
        description="After-hours quote"
    )

    # Company information
    profile: Optional[CompanyProfile] = Field(
        None,
        description="Company profile"
    )
    executives: Optional[List[Executive]] = Field(
        None,
        description="Executive officers"
    )

    # Corporate events
    dividends: Optional[List[DividendRecord]] = Field(
        None,
        description="Dividend history"
    )
    splits: Optional[List[StockSplit]] = Field(
        None,
        description="Stock split history"
    )
    earnings_calendar: Optional[List[EarningsEvent]] = Field(
        None,
        description="Earnings events"
    )

    # Fundamental statements
    income_statements: List[IncomeStatement] = Field(
        default_factory=list,
        description="Income statements"
    )
    balance_sheets: List[BalanceSheet] = Field(
        default_factory=list,
        description="Balance sheets"
    )
    cash_flow_statements: List[CashFlowStatement] = Field(
        default_factory=list,
        description="Cash flow statements"
    )

    # Financial metrics and ratios
    key_metrics: Optional[List[KeyMetrics]] = Field(
        None,
        description="Key financial metrics"
    )
    financial_ratios: Optional[List[FinancialRatios]] = Field(
        None,
        description="Financial ratios"
    )
    financial_scores: Optional[List[FinancialScores]] = Field(
        None,
        description="Financial scores (Piotroski, Altman Z)"
    )

    # Valuation
    dcf_valuation: Optional[DCFValuation] = Field(
        None,
        description="DCF valuation"
    )
    enterprise_values: Optional[List[EnterpriseValue]] = Field(
        None,
        description="Enterprise value history"
    )

    # Analyst data
    analyst_estimates: Optional[List[AnalystEstimate]] = Field(
        None,
        description="Analyst earnings/revenue estimates"
    )
    price_targets: Optional[List[PriceTarget]] = Field(
        None,
        description="Analyst price targets"
    )
    price_target_summary: Optional[PriceTargetSummary] = Field(
        None,
        description="Aggregated price target summary"
    )
    analyst_grades: Optional[List[AnalystGrade]] = Field(
        None,
        description="Analyst upgrades/downgrades"
    )

    # Ownership
    institutional_holders: Optional[List[InstitutionalHolder]] = Field(
        None,
        description="Institutional ownership"
    )
    insider_trades: Optional[List[InsiderTrade]] = Field(
        None,
        description="Insider trading activity"
    )

    # Historical prices
    historical_prices: Optional[List[dict]] = Field(
        None,
        description="Historical price data"
    )

    # Earnings transcripts
    transcripts: Optional[List[EarningsTranscript]] = Field(
        None,
        description="Earnings call transcripts"
    )
    transcript_summaries: Optional[List[TranscriptSummary]] = Field(
        None,
        description="AI-generated transcript summaries"
    )

    # SEC filings
    sec_filings: Optional[List[SECFiling]] = Field(
        None,
        description="SEC filings"
    )
    filing_summaries: Optional[List[FilingSummary]] = Field(
        None,
        description="AI-generated filing summaries"
    )

    # News
    news: Optional[List[NewsArticle]] = Field(
        None,
        description="Recent news articles"
    )

    # Analysis results
    institutional_analysis: Optional[dict] = Field(
        None,
        description="Institutional ownership analysis"
    )

    # Metadata
    fetched_at: Optional[str] = Field(
        None,
        description="Timestamp when data was fetched"
    )
    cache_hit: Optional[bool] = Field(
        None,
        description="Whether data came from cache"
    )

    def get_latest_income_statement(self) -> Optional[IncomeStatement]:
        """Get the most recent income statement.

        Returns:
            Latest income statement or None
        """
        if self.income_statements and len(self.income_statements) > 0:
            return self.income_statements[0]
        return None

    def get_latest_balance_sheet(self) -> Optional[BalanceSheet]:
        """Get the most recent balance sheet.

        Returns:
            Latest balance sheet or None
        """
        if self.balance_sheets and len(self.balance_sheets) > 0:
            return self.balance_sheets[0]
        return None

    def get_latest_cash_flow(self) -> Optional[CashFlowStatement]:
        """Get the most recent cash flow statement.

        Returns:
            Latest cash flow statement or None
        """
        if self.cash_flow_statements and len(self.cash_flow_statements) > 0:
            return self.cash_flow_statements[0]
        return None

    def get_latest_cash_flow_statement(self) -> Optional[CashFlowStatement]:
        """Alias for get_latest_cash_flow for consistency.

        Returns:
            Latest cash flow statement or None
        """
        return self.get_latest_cash_flow()

    def get_latest_key_metrics(self) -> Optional[KeyMetrics]:
        """Get the most recent key metrics.

        Returns:
            Latest key metrics or None
        """
        if self.key_metrics and len(self.key_metrics) > 0:
            return self.key_metrics[0]
        return None

    def get_latest_ratios(self) -> Optional[FinancialRatios]:
        """Get the most recent financial ratios.

        Returns:
            Latest financial ratios or None
        """
        if self.financial_ratios and len(self.financial_ratios) > 0:
            return self.financial_ratios[0]
        return None

    def has_fundamentals(self) -> bool:
        """Check if fundamental data is available.

        Returns:
            True if any fundamental data is present
        """
        return bool(
            self.income_statements or
            self.balance_sheets or
            self.cash_flow_statements or
            self.key_metrics or
            self.financial_ratios
        )

    def has_analyst_data(self) -> bool:
        """Check if analyst data is available.

        Returns:
            True if any analyst data is present
        """
        return bool(
            self.analyst_estimates or
            self.price_targets or
            self.price_target_summary or
            self.analyst_grades
        )

    def has_ownership_data(self) -> bool:
        """Check if ownership data is available.

        Returns:
            True if any ownership data is present
        """
        return bool(
            self.institutional_holders or
            self.insider_trades
        )

    def summary(self) -> dict:
        """Get a summary of available data.

        Returns:
            Dictionary with counts of available data types
        """
        return {
            "symbol": self.symbol,
            "has_quote": self.quote is not None,
            "has_profile": self.profile is not None,
            "income_statements_count": len(self.income_statements) if self.income_statements else 0,
            "balance_sheets_count": len(self.balance_sheets) if self.balance_sheets else 0,
            "cash_flow_statements_count": len(self.cash_flow_statements) if self.cash_flow_statements else 0,
            "key_metrics_count": len(self.key_metrics) if self.key_metrics else 0,
            "financial_ratios_count": len(self.financial_ratios) if self.financial_ratios else 0,
            "institutional_holders_count": len(self.institutional_holders) if self.institutional_holders else 0,
            "insider_trades_count": len(self.insider_trades) if self.insider_trades else 0,
            "analyst_estimates_count": len(self.analyst_estimates) if self.analyst_estimates else 0,
            "transcripts_count": len(self.transcripts) if self.transcripts else 0,
            "sec_filings_count": len(self.sec_filings) if self.sec_filings else 0,
            "news_count": len(self.news) if self.news else 0,
            "has_institutional_analysis": self.institutional_analysis is not None,
        }
