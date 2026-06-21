"""Data request model - defines what data to fetch for a ticker."""

from typing import List, Optional

from pydantic import Field, field_validator

from .base import FMPBaseModel


class DataRequest(FMPBaseModel):
    """Request specification for ticker data.

    This is THE MOST CRITICAL MODEL - it defines what data to fetch
    for a given ticker symbol. All boolean flags default to False,
    allowing users to opt-in to specific data types.
    """

    # Required field
    symbol: str = Field(..., description="Stock ticker symbol (e.g., 'AAPL')")

    # Quote data
    include_quote: bool = Field(default=False, description="Include real-time quote")
    include_aftermarket_quote: bool = Field(
        default=False, description="Include after-hours quote"
    )

    # Company profile
    include_profile: bool = Field(
        default=False, description="Include company profile"
    )
    include_executives: bool = Field(
        default=False, description="Include executive information"
    )

    # Corporate events
    include_dividends: bool = Field(
        default=False, description="Include dividend history"
    )
    include_splits: bool = Field(default=False, description="Include stock splits")
    include_earnings_calendar: bool = Field(
        default=False, description="Include earnings calendar"
    )

    # Fundamental data
    include_fundamentals: bool = Field(
        default=False, description="Include all fundamental statements"
    )
    include_income_statement: bool = Field(
        default=False, description="Include income statements"
    )
    include_balance_sheet: bool = Field(
        default=False, description="Include balance sheets"
    )
    include_cash_flow: bool = Field(
        default=False, description="Include cash flow statements"
    )
    include_key_metrics: bool = Field(
        default=False, description="Include key financial metrics"
    )
    include_ratios: bool = Field(
        default=False, description="Include financial ratios"
    )
    include_financial_scores: bool = Field(
        default=False, description="Include financial scores (Piotroski, Altman)"
    )

    # Fundamental configuration
    fundamentals_periods: int = Field(
        default=4,
        ge=1,
        le=20,
        description="Number of periods to fetch for fundamentals (1-20)",
    )
    fundamentals_period_type: str = Field(
        default="quarter",
        description="Period type: 'quarter' or 'annual'",
    )

    # Valuation data
    include_dcf: bool = Field(
        default=False, description="Include DCF valuation"
    )
    include_enterprise_value: bool = Field(
        default=False, description="Include enterprise value metrics"
    )

    # Analyst data
    include_analyst_estimates: bool = Field(
        default=False, description="Include analyst estimates"
    )
    include_price_targets: bool = Field(
        default=False, description="Include analyst price targets"
    )
    include_analyst_grades: bool = Field(
        default=False, description="Include analyst upgrades/downgrades"
    )

    # Ownership data
    include_institutional_holders: bool = Field(
        default=False, description="Include institutional ownership"
    )
    include_insider_trades: bool = Field(
        default=False, description="Include insider trading activity"
    )
    insider_trades_days: int = Field(
        default=90,
        ge=1,
        le=365,
        description="Days of insider trades to fetch (1-365)",
    )

    # Historical price data
    include_historical_prices: bool = Field(
        default=False, description="Include historical price data"
    )
    historical_days: int = Field(
        default=90,
        ge=1,
        le=3650,
        description="Days of historical prices to fetch (1-3650)",
    )

    # Earnings transcripts
    include_transcripts: bool = Field(
        default=False, description="Include earnings call transcripts"
    )
    transcript_count: int = Field(
        default=4,
        ge=1,
        le=20,
        description="Number of transcripts to fetch (1-20)",
    )
    summarize_transcripts: bool = Field(
        default=False,
        description="Generate AI summaries for transcripts (requires LLM)",
    )

    # SEC filings
    include_sec_filings: bool = Field(
        default=False, description="Include SEC filings"
    )
    sec_filing_types: Optional[List[str]] = Field(
        default=None,
        description="Filing types to fetch (e.g., ['10-K', '10-Q']). None = all types",
    )
    sec_filing_count: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Number of filings to fetch per type (1-50)",
    )
    summarize_filings: bool = Field(
        default=False,
        description="Generate AI summaries for filings (requires LLM)",
    )

    # News
    include_news: bool = Field(
        default=False, description="Include recent news articles"
    )
    news_count: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of news articles to fetch (1-100)",
    )

    # Analysis options
    include_institutional_analysis: bool = Field(
        default=False,
        description="Include institutional ownership analysis and holder classification",
    )

    @field_validator("fundamentals_period_type")
    @classmethod
    def validate_period_type(cls, v: str) -> str:
        """Validate period type is either 'quarter' or 'annual'."""
        v = v.lower()
        if v not in ("quarter", "annual"):
            raise ValueError("Period type must be 'quarter' or 'annual'")
        return v

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """Normalize symbol to uppercase and strip whitespace."""
        return v.strip().upper()

    @field_validator("sec_filing_types")
    @classmethod
    def validate_filing_types(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Normalize filing types to uppercase."""
        if v is None:
            return None
        return [ft.upper().strip() for ft in v]

    def enable_all_fundamentals(self) -> None:
        """Convenience method to enable all fundamental data flags."""
        self.include_fundamentals = True
        self.include_income_statement = True
        self.include_balance_sheet = True
        self.include_cash_flow = True
        self.include_key_metrics = True
        self.include_ratios = True
        self.include_financial_scores = True

    def enable_all_analyst_data(self) -> None:
        """Convenience method to enable all analyst data flags."""
        self.include_analyst_estimates = True
        self.include_price_targets = True
        self.include_analyst_grades = True

    def enable_full_analysis(self) -> None:
        """Enable comprehensive analysis including all data types."""
        self.include_quote = True
        self.include_profile = True
        self.include_executives = True
        self.enable_all_fundamentals()
        self.enable_all_analyst_data()
        self.include_institutional_holders = True
        self.include_insider_trades = True
        self.include_institutional_analysis = True
        self.include_historical_prices = True
        self.include_dcf = True
        self.include_enterprise_value = True
        self.include_dividends = True
        self.include_splits = True
        self.include_earnings_calendar = True

    def requires_llm(self) -> bool:
        """Check if this request requires LLM capabilities.

        Returns:
            True if LLM summarization is requested
        """
        return self.summarize_transcripts or self.summarize_filings

    def get_enabled_features(self) -> List[str]:
        """Get list of enabled feature names.

        Returns:
            List of feature names that are enabled
        """
        features = []
        for field_name, field_info in self.model_fields.items():
            if field_name.startswith("include_") or field_name.startswith("summarize_"):
                value = getattr(self, field_name)
                if value:
                    features.append(field_name)
        return features
