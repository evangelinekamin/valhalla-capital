"""Specialized type-safe fetch methods for each data type."""

from typing import List, Optional

from ..models import (
    AftermarketQuote,
    AnalystEstimate,
    AnalystGrade,
    BalanceSheet,
    CashFlowStatement,
    CompanyProfile,
    DCFValuation,
    DividendRecord,
    EarningsEvent,
    EarningsTranscript,
    EnterpriseValue,
    Executive,
    FinancialRatios,
    FinancialScores,
    IncomeStatement,
    InsiderTrade,
    InstitutionalHolder,
    KeyMetrics,
    NewsArticle,
    PriceTarget,
    PriceTargetSummary,
    Quote,
    SECFiling,
    StockSplit,
)
from .base import DataFetcher
from .endpoints import Endpoint


class SpecializedFetcher:
    """Type-safe fetch methods for FMP data types.

    Wraps DataFetcher and returns properly typed Pydantic models.
    """

    def __init__(self, fetcher: DataFetcher):
        """Initialize specialized fetcher.

        Args:
            fetcher: Base data fetcher instance
        """
        self.fetcher = fetcher

    # Quote data

    async def fetch_quote(self, symbol: str) -> Optional[Quote]:
        """Fetch real-time quote.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Quote object or None
        """
        data = await self.fetcher.fetch_list(
            Endpoint.QUOTE,
            query_params={"symbol": symbol}
        )
        if data and len(data) > 0:
            return Quote(**data[0])
        return None

    async def fetch_aftermarket_quote(self, symbol: str) -> Optional[AftermarketQuote]:
        """Fetch after-hours quote.

        Args:
            symbol: Stock ticker symbol

        Returns:
            AftermarketQuote object or None
        """
        data = await self.fetcher.fetch_list(
            Endpoint.AFTERMARKET_QUOTE,
            query_params={"symbol": symbol}
        )
        if data and len(data) > 0:
            return AftermarketQuote(**data[0])
        return None

    # Profile data

    async def fetch_profile(self, symbol: str) -> Optional[CompanyProfile]:
        """Fetch company profile.

        Args:
            symbol: Stock ticker symbol

        Returns:
            CompanyProfile object or None
        """
        data = await self.fetcher.fetch_list(
            Endpoint.PROFILE,
            query_params={"symbol": symbol}
        )
        if data and len(data) > 0:
            return CompanyProfile(**data[0])
        return None

    async def fetch_executives(self, symbol: str) -> List[Executive]:
        """Fetch executive officers.

        Args:
            symbol: Stock ticker symbol

        Returns:
            List of Executive objects
        """
        data = await self.fetcher.fetch_list(
            Endpoint.EXECUTIVES,
            query_params={"symbol": symbol}
        )
        return [Executive(**item) for item in data]

    # Events

    async def fetch_dividends(self, symbol: str) -> List[DividendRecord]:
        """Fetch dividend history.

        Args:
            symbol: Stock ticker symbol

        Returns:
            List of DividendRecord objects
        """
        data = await self.fetcher.fetch(
            Endpoint.DIVIDENDS_HISTORICAL,
            query_params={"symbol": symbol}
        )
        # Stable API returns a flat list; fall back to nested format
        if isinstance(data, list):
            return [DividendRecord(**item) for item in data]
        if isinstance(data, dict):
            historical = data.get("historical", [])
            return [DividendRecord(**item) for item in historical]
        return []

    async def fetch_splits(self, symbol: str) -> List[StockSplit]:
        """Fetch stock split history.

        Args:
            symbol: Stock ticker symbol

        Returns:
            List of StockSplit objects
        """
        data = await self.fetcher.fetch(
            Endpoint.STOCK_SPLIT_HISTORICAL,
            query_params={"symbol": symbol}
        )
        # Stable API returns a flat list; fall back to nested format
        if isinstance(data, list):
            return [StockSplit(**item) for item in data]
        if isinstance(data, dict):
            historical = data.get("historical", [])
            return [StockSplit(**item) for item in historical]
        return []

    async def fetch_earnings_calendar(
        self,
        symbol: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[EarningsEvent]:
        """Fetch earnings calendar.

        Args:
            symbol: Optional stock ticker symbol
            from_date: Optional start date (YYYY-MM-DD)
            to_date: Optional end date (YYYY-MM-DD)

        Returns:
            List of EarningsEvent objects
        """
        query_params = {}
        if symbol:
            query_params["symbol"] = symbol
        if from_date:
            query_params["from"] = from_date
        if to_date:
            query_params["to"] = to_date

        data = await self.fetcher.fetch_list(
            Endpoint.EARNINGS_CALENDAR,
            query_params=query_params
        )
        return [EarningsEvent(**item) for item in data]

    # Fundamentals

    async def fetch_income_statements(
        self,
        symbol: str,
        period: str = "quarter",
        limit: int = 4,
    ) -> List[IncomeStatement]:
        """Fetch income statements.

        Args:
            symbol: Stock ticker symbol
            period: 'quarter' or 'annual'
            limit: Number of periods to fetch

        Returns:
            List of IncomeStatement objects
        """
        data = await self.fetcher.fetch_list(
            Endpoint.INCOME_STATEMENT,
            query_params={"symbol": symbol, "period": period, "limit": limit}
        )
        return [IncomeStatement(**item) for item in data]

    async def fetch_balance_sheets(
        self,
        symbol: str,
        period: str = "quarter",
        limit: int = 4,
    ) -> List[BalanceSheet]:
        """Fetch balance sheets.

        Args:
            symbol: Stock ticker symbol
            period: 'quarter' or 'annual'
            limit: Number of periods to fetch

        Returns:
            List of BalanceSheet objects
        """
        data = await self.fetcher.fetch_list(
            Endpoint.BALANCE_SHEET,
            query_params={"symbol": symbol, "period": period, "limit": limit}
        )
        return [BalanceSheet(**item) for item in data]

    async def fetch_cash_flow_statements(
        self,
        symbol: str,
        period: str = "quarter",
        limit: int = 4,
    ) -> List[CashFlowStatement]:
        """Fetch cash flow statements.

        Args:
            symbol: Stock ticker symbol
            period: 'quarter' or 'annual'
            limit: Number of periods to fetch

        Returns:
            List of CashFlowStatement objects
        """
        data = await self.fetcher.fetch_list(
            Endpoint.CASH_FLOW,
            query_params={"symbol": symbol, "period": period, "limit": limit}
        )
        return [CashFlowStatement(**item) for item in data]

    async def fetch_key_metrics(
        self,
        symbol: str,
        period: str = "quarter",
        limit: int = 4,
    ) -> List[KeyMetrics]:
        """Fetch key financial metrics.

        Args:
            symbol: Stock ticker symbol
            period: 'quarter' or 'annual'
            limit: Number of periods to fetch

        Returns:
            List of KeyMetrics objects
        """
        data = await self.fetcher.fetch_list(
            Endpoint.KEY_METRICS,
            query_params={"symbol": symbol, "period": period, "limit": limit}
        )
        return [KeyMetrics(**item) for item in data]

    async def fetch_financial_ratios(
        self,
        symbol: str,
        period: str = "quarter",
        limit: int = 4,
    ) -> List[FinancialRatios]:
        """Fetch financial ratios.

        Args:
            symbol: Stock ticker symbol
            period: 'quarter' or 'annual'
            limit: Number of periods to fetch

        Returns:
            List of FinancialRatios objects
        """
        data = await self.fetcher.fetch_list(
            Endpoint.FINANCIAL_RATIOS,
            query_params={"symbol": symbol, "period": period, "limit": limit}
        )
        return [FinancialRatios(**item) for item in data]

    async def fetch_financial_scores(self, symbol: str) -> Optional[FinancialScores]:
        """Fetch financial scores (Piotroski, Altman Z).

        Args:
            symbol: Stock ticker symbol

        Returns:
            FinancialScores object or None
        """
        data = await self.fetcher.fetch_list(
            Endpoint.FINANCIAL_SCORES,
            query_params={"symbol": symbol}
        )
        if data and len(data) > 0:
            return FinancialScores(**data[0])
        return None

    # Valuation

    async def fetch_dcf(self, symbol: str) -> Optional[DCFValuation]:
        """Fetch DCF valuation.

        Args:
            symbol: Stock ticker symbol

        Returns:
            DCFValuation object or None
        """
        data = await self.fetcher.fetch_list(
            Endpoint.DCF,
            query_params={"symbol": symbol}
        )
        if data and len(data) > 0:
            return DCFValuation(**data[0])
        return None

    async def fetch_enterprise_values(
        self,
        symbol: str,
        period: str = "quarter",
        limit: int = 4,
    ) -> List[EnterpriseValue]:
        """Fetch enterprise value history.

        Args:
            symbol: Stock ticker symbol
            period: 'quarter' or 'annual'
            limit: Number of periods to fetch

        Returns:
            List of EnterpriseValue objects
        """
        data = await self.fetcher.fetch_list(
            Endpoint.ENTERPRISE_VALUE,
            query_params={"symbol": symbol, "period": period, "limit": limit}
        )
        return [EnterpriseValue(**item) for item in data]

    # Analyst data

    async def fetch_analyst_estimates(
        self,
        symbol: str,
        period: str = "quarter",
        limit: int = 4,
    ) -> List[AnalystEstimate]:
        """Fetch analyst earnings/revenue estimates.

        Args:
            symbol: Stock ticker symbol
            period: 'quarter' or 'annual'
            limit: Number of periods to fetch

        Returns:
            List of AnalystEstimate objects
        """
        data = await self.fetcher.fetch_list(
            Endpoint.ANALYST_ESTIMATES,
            query_params={"symbol": symbol, "period": period, "limit": limit}
        )
        return [AnalystEstimate(**item) for item in data]

    async def fetch_price_targets(self, symbol: str) -> List[PriceTarget]:
        """Fetch analyst price targets.

        Args:
            symbol: Stock ticker symbol

        Returns:
            List of PriceTarget objects
        """
        data = await self.fetcher.fetch_list(
            Endpoint.PRICE_TARGET,
            query_params={"symbol": symbol}
        )
        return [PriceTarget(**item) for item in data]

    async def fetch_price_target_summary(self, symbol: str) -> Optional[PriceTargetSummary]:
        """Fetch price target summary.

        Args:
            symbol: Stock ticker symbol

        Returns:
            PriceTargetSummary object or None
        """
        data = await self.fetcher.fetch_list(
            Endpoint.PRICE_TARGET_SUMMARY,
            query_params={"symbol": symbol}
        )
        if data and len(data) > 0:
            return PriceTargetSummary(**data[0])
        return None

    async def fetch_analyst_grades(self, symbol: str, limit: int = 30) -> List[AnalystGrade]:
        """Fetch analyst upgrades/downgrades.

        Args:
            symbol: Stock ticker symbol
            limit: Number of records to fetch

        Returns:
            List of AnalystGrade objects
        """
        data = await self.fetcher.fetch_list(
            Endpoint.ANALYST_UPGRADES_DOWNGRADES,
            query_params={"symbol": symbol, "limit": limit}
        )
        return [AnalystGrade(**item) for item in data]

    # Ownership

    async def fetch_institutional_holders(self, symbol: str) -> List[InstitutionalHolder]:
        """Fetch institutional ownership.

        Args:
            symbol: Stock ticker symbol

        Returns:
            List of InstitutionalHolder objects
        """
        data = await self.fetcher.fetch_list(
            Endpoint.INSTITUTIONAL_HOLDERS,
            query_params={"symbol": symbol}
        )
        return [InstitutionalHolder(**item) for item in data]

    async def fetch_insider_trades(
        self,
        symbol: str,
        limit: int = 100,
    ) -> List[InsiderTrade]:
        """Fetch insider trading activity.

        Args:
            symbol: Stock ticker symbol
            limit: Number of trades to fetch

        Returns:
            List of InsiderTrade objects
        """
        data = await self.fetcher.fetch_list(
            Endpoint.INSIDER_TRADING,
            query_params={"symbol": symbol, "limit": limit}
        )
        return [InsiderTrade(**item) for item in data]

    # Transcripts

    async def fetch_transcript(
        self,
        symbol: str,
        year: int,
        quarter: int,
    ) -> Optional[EarningsTranscript]:
        """Fetch single earnings transcript.

        Args:
            symbol: Stock ticker symbol
            year: Fiscal year
            quarter: Fiscal quarter (1-4)

        Returns:
            EarningsTranscript object or None
        """
        data = await self.fetcher.fetch_list(
            Endpoint.EARNING_CALL_TRANSCRIPT,
            query_params={"symbol": symbol, "year": year, "quarter": quarter}
        )
        if data and len(data) > 0:
            return EarningsTranscript(**data[0])
        return None

    # SEC Filings

    async def fetch_sec_filings(
        self,
        symbol: str,
        filing_type: Optional[str] = None,
        limit: int = 5,
    ) -> List[SECFiling]:
        """Fetch SEC filings.

        Args:
            symbol: Stock ticker symbol
            filing_type: Optional filing type (10-K, 10-Q, 8-K, etc.)
            limit: Number of filings to fetch

        Returns:
            List of SECFiling objects
        """
        query_params = {"symbol": symbol, "limit": limit}
        if filing_type:
            query_params["type"] = filing_type

        data = await self.fetcher.fetch_list(
            Endpoint.SEC_FILINGS,
            query_params=query_params
        )
        return [SECFiling(**item) for item in data]

    # News

    async def fetch_news(
        self,
        symbol: Optional[str] = None,
        limit: int = 10,
    ) -> List[NewsArticle]:
        """Fetch stock news.

        Args:
            symbol: Optional stock ticker symbol
            limit: Number of articles to fetch

        Returns:
            List of NewsArticle objects
        """
        query_params = {"limit": limit}
        if symbol:
            query_params["symbols"] = symbol

        data = await self.fetcher.fetch_list(
            Endpoint.STOCK_NEWS,
            query_params=query_params
        )
        return [NewsArticle(**item) for item in data]

    # Historical prices

    async def fetch_historical_prices(
        self,
        symbol: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[dict]:
        """Fetch historical price data.

        Args:
            symbol: Stock ticker symbol
            from_date: Optional start date (YYYY-MM-DD)
            to_date: Optional end date (YYYY-MM-DD)

        Returns:
            List of price records
        """
        query_params = {"symbol": symbol}
        if from_date:
            query_params["from"] = from_date
        if to_date:
            query_params["to"] = to_date

        data = await self.fetcher.fetch(
            Endpoint.HISTORICAL_PRICES,
            query_params=query_params
        )

        # Stable API returns a flat list; fall back to nested format
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("historical", [])
        return []
