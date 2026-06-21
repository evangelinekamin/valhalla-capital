"""Main FMP Data Client - orchestrates all components."""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

from .cache import MySQLCache
from .config import FMPConfig
from .fetcher import DataFetcher, SpecializedFetcher
from .models import (
    AftermarketQuote,
    CompanyProfile,
    DataRequest,
    Quote,
    TickerData,
)


class FMPDataClient:
    """Main client for accessing FMP data.

    Orchestrates fetching, caching, and optional summarization of financial data.
    """

    def __init__(self, config: FMPConfig):
        """Initialize FMP Data Client.

        Args:
            config: FMP configuration
        """
        self.config = config

        # Initialize fetcher
        self.fetcher = DataFetcher(config)
        self.specialized_fetcher = SpecializedFetcher(self.fetcher)

        # Initialize cache (if enabled)
        self.cache: Optional[MySQLCache] = None
        if config.cache_enabled:
            self.cache = MySQLCache(config)

        # Summarizer will be initialized if needed
        self.summarizer = None

    @classmethod
    def from_env(cls) -> "FMPDataClient":
        """Create client from environment variables.

        Returns:
            FMPDataClient instance
        """
        config = FMPConfig.from_env()
        return cls(config)

    async def __aenter__(self) -> "FMPDataClient":
        """Enter async context manager."""
        await self.fetcher.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager."""
        await self.fetcher.close()
        if self.cache:
            self.cache.close()

    # Core method - get comprehensive ticker data

    async def get_ticker_data(self, request: DataRequest) -> TickerData:
        """Get comprehensive data for a ticker based on request.

        This is the MAIN METHOD that orchestrates fetching all requested data types.

        Args:
            request: Data request specification

        Returns:
            TickerData with all requested data populated
        """
        symbol = request.symbol
        tasks = []
        task_names = []

        # Helper to add task
        def add_task(coro, name: str):
            tasks.append(coro)
            task_names.append(name)

        # Quote data
        if request.include_quote:
            add_task(self._fetch_quote(symbol), "quote")

        if request.include_aftermarket_quote:
            add_task(self._fetch_aftermarket_quote(symbol), "aftermarket_quote")

        # Profile
        if request.include_profile:
            add_task(self._fetch_profile(symbol), "profile")

        if request.include_executives:
            add_task(self._fetch_executives(symbol), "executives")

        # Events
        if request.include_dividends:
            add_task(self._fetch_dividends(symbol), "dividends")

        if request.include_splits:
            add_task(self._fetch_splits(symbol), "splits")

        if request.include_earnings_calendar:
            add_task(self._fetch_earnings_calendar(symbol), "earnings_calendar")

        # Fundamentals
        if request.include_income_statement or request.include_fundamentals:
            add_task(
                self._fetch_income_statements(
                    symbol,
                    request.fundamentals_period_type,
                    request.fundamentals_periods,
                ),
                "income_statements",
            )

        if request.include_balance_sheet or request.include_fundamentals:
            add_task(
                self._fetch_balance_sheets(
                    symbol,
                    request.fundamentals_period_type,
                    request.fundamentals_periods,
                ),
                "balance_sheets",
            )

        if request.include_cash_flow or request.include_fundamentals:
            add_task(
                self._fetch_cash_flow_statements(
                    symbol,
                    request.fundamentals_period_type,
                    request.fundamentals_periods,
                ),
                "cash_flow_statements",
            )

        if request.include_key_metrics or request.include_fundamentals:
            add_task(
                self._fetch_key_metrics(
                    symbol,
                    request.fundamentals_period_type,
                    request.fundamentals_periods,
                ),
                "key_metrics",
            )

        if request.include_ratios or request.include_fundamentals:
            add_task(
                self._fetch_financial_ratios(
                    symbol,
                    request.fundamentals_period_type,
                    request.fundamentals_periods,
                ),
                "financial_ratios",
            )

        if request.include_financial_scores or request.include_fundamentals:
            add_task(self._fetch_financial_scores(symbol), "financial_scores")

        # Valuation
        if request.include_dcf:
            add_task(self._fetch_dcf(symbol), "dcf_valuation")

        if request.include_enterprise_value:
            add_task(
                self._fetch_enterprise_values(
                    symbol,
                    request.fundamentals_period_type,
                    request.fundamentals_periods,
                ),
                "enterprise_values",
            )

        # Analyst data
        if request.include_analyst_estimates:
            add_task(
                self._fetch_analyst_estimates(
                    symbol,
                    request.fundamentals_period_type,
                    request.fundamentals_periods,
                ),
                "analyst_estimates",
            )

        if request.include_price_targets:
            add_task(self._fetch_price_targets(symbol), "price_targets")
            add_task(self._fetch_price_target_summary(symbol), "price_target_summary")

        if request.include_analyst_grades:
            add_task(self._fetch_analyst_grades(symbol), "analyst_grades")

        # Ownership
        if request.include_institutional_holders:
            add_task(self._fetch_institutional_holders(symbol), "institutional_holders")

        if request.include_insider_trades:
            add_task(
                self._fetch_insider_trades(symbol, request.insider_trades_days),
                "insider_trades",
            )

        # Historical prices
        if request.include_historical_prices:
            add_task(
                self._fetch_historical_prices(symbol, request.historical_days),
                "historical_prices",
            )

        # Transcripts
        if request.include_transcripts:
            add_task(
                self._fetch_transcripts(symbol, request.transcript_count),
                "transcripts",
            )

        # SEC filings
        if request.include_sec_filings:
            add_task(
                self._fetch_sec_filings(
                    symbol,
                    request.sec_filing_types,
                    request.sec_filing_count,
                ),
                "sec_filings",
            )

        # News
        if request.include_news:
            add_task(self._fetch_news(symbol, request.news_count), "news")

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build TickerData from results
        ticker_data_dict = {"symbol": symbol, "fetched_at": datetime.now().isoformat()}

        for name, result in zip(task_names, results):
            if isinstance(result, Exception):
                # Log error but continue
                logger.warning("Error fetching %s for %s: %s", name, symbol, result)
                continue
            ticker_data_dict[name] = result

        return TickerData(**ticker_data_dict)

    # Fetch methods with caching

    async def _fetch_quote(self, symbol: str) -> Optional[Quote]:
        """Fetch quote with caching."""
        cache_key = f"{symbol}_quote"
        if self.cache:
            cached = await self.cache.get(symbol, "quote")
            if cached:
                return Quote(**cached)

        quote = await self.specialized_fetcher.fetch_quote(symbol)

        if quote and self.cache:
            await self.cache.set(symbol, "quote", quote.to_dict())

        return quote

    async def _fetch_aftermarket_quote(self, symbol: str) -> Optional[AftermarketQuote]:
        """Fetch aftermarket quote with caching."""
        if self.cache:
            cached = await self.cache.get(symbol, "aftermarket_quote")
            if cached:
                return AftermarketQuote(**cached)

        quote = await self.specialized_fetcher.fetch_aftermarket_quote(symbol)

        if quote and self.cache:
            await self.cache.set(symbol, "aftermarket_quote", quote.to_dict())

        return quote

    async def _fetch_profile(self, symbol: str) -> Optional[CompanyProfile]:
        """Fetch profile with caching."""
        if self.cache:
            cached = await self.cache.get(symbol, "profile")
            if cached:
                return CompanyProfile(**cached)

        profile = await self.specialized_fetcher.fetch_profile(symbol)

        if profile and self.cache:
            await self.cache.set(symbol, "profile", profile.to_dict())

        return profile

    async def _fetch_executives(self, symbol: str):
        """Fetch executives with caching."""
        if self.cache:
            cached = await self.cache.get(symbol, "executives")
            if cached:
                from .models import Executive
                return [Executive(**item) for item in cached]

        executives = await self.specialized_fetcher.fetch_executives(symbol)

        if executives and self.cache:
            await self.cache.set(
                symbol, "executives", [e.to_dict() for e in executives]
            )

        return executives

    async def _fetch_dividends(self, symbol: str):
        """Fetch dividends with caching."""
        if self.cache:
            cached = await self.cache.get(symbol, "dividends")
            if cached:
                from .models import DividendRecord
                return [DividendRecord(**item) for item in cached]

        dividends = await self.specialized_fetcher.fetch_dividends(symbol)

        if dividends and self.cache:
            await self.cache.set(
                symbol, "dividends", [d.to_dict() for d in dividends]
            )

        return dividends

    async def _fetch_splits(self, symbol: str):
        """Fetch splits with caching."""
        if self.cache:
            cached = await self.cache.get(symbol, "splits")
            if cached:
                from .models import StockSplit
                return [StockSplit(**item) for item in cached]

        splits = await self.specialized_fetcher.fetch_splits(symbol)

        if splits and self.cache:
            await self.cache.set(
                symbol, "splits", [s.to_dict() for s in splits]
            )

        return splits

    async def _fetch_earnings_calendar(self, symbol: str):
        """Fetch earnings calendar."""
        calendar = await self.specialized_fetcher.fetch_earnings_calendar(symbol)
        return calendar

    async def _fetch_income_statements(self, symbol: str, period: str, limit: int):
        """Fetch income statements with caching."""
        period_key = f"{period}_{limit}"
        if self.cache:
            cached = await self.cache.get(symbol, "income_statements", period_key)
            if cached:
                from .models import IncomeStatement
                return [IncomeStatement(**item) for item in cached]

        statements = await self.specialized_fetcher.fetch_income_statements(
            symbol, period, limit
        )

        if statements and self.cache:
            await self.cache.set(
                symbol,
                "income_statements",
                [s.to_dict() for s in statements],
                period_key,
            )

        return statements

    async def _fetch_balance_sheets(self, symbol: str, period: str, limit: int):
        """Fetch balance sheets with caching."""
        period_key = f"{period}_{limit}"
        if self.cache:
            cached = await self.cache.get(symbol, "balance_sheets", period_key)
            if cached:
                from .models import BalanceSheet
                return [BalanceSheet(**item) for item in cached]

        sheets = await self.specialized_fetcher.fetch_balance_sheets(
            symbol, period, limit
        )

        if sheets and self.cache:
            await self.cache.set(
                symbol,
                "balance_sheets",
                [s.to_dict() for s in sheets],
                period_key,
            )

        return sheets

    async def _fetch_cash_flow_statements(self, symbol: str, period: str, limit: int):
        """Fetch cash flow statements with caching."""
        period_key = f"{period}_{limit}"
        if self.cache:
            cached = await self.cache.get(symbol, "cash_flow_statements", period_key)
            if cached:
                from .models import CashFlowStatement
                return [CashFlowStatement(**item) for item in cached]

        statements = await self.specialized_fetcher.fetch_cash_flow_statements(
            symbol, period, limit
        )

        if statements and self.cache:
            await self.cache.set(
                symbol,
                "cash_flow_statements",
                [s.to_dict() for s in statements],
                period_key,
            )

        return statements

    async def _fetch_key_metrics(self, symbol: str, period: str, limit: int):
        """Fetch key metrics with caching."""
        period_key = f"{period}_{limit}"
        if self.cache:
            cached = await self.cache.get(symbol, "key_metrics", period_key)
            if cached:
                from .models import KeyMetrics
                return [KeyMetrics(**item) for item in cached]

        metrics = await self.specialized_fetcher.fetch_key_metrics(
            symbol, period, limit
        )

        if metrics and self.cache:
            await self.cache.set(
                symbol,
                "key_metrics",
                [m.to_dict() for m in metrics],
                period_key,
            )

        return metrics

    async def _fetch_financial_ratios(self, symbol: str, period: str, limit: int):
        """Fetch financial ratios with caching."""
        period_key = f"{period}_{limit}"
        if self.cache:
            cached = await self.cache.get(symbol, "financial_ratios", period_key)
            if cached:
                from .models import FinancialRatios
                return [FinancialRatios(**item) for item in cached]

        ratios = await self.specialized_fetcher.fetch_financial_ratios(
            symbol, period, limit
        )

        if ratios and self.cache:
            await self.cache.set(
                symbol,
                "financial_ratios",
                [r.to_dict() for r in ratios],
                period_key,
            )

        return ratios

    async def _fetch_financial_scores(self, symbol: str):
        """Fetch financial scores with caching."""
        if self.cache:
            cached = await self.cache.get(symbol, "financial_scores")
            if cached:
                from .models import FinancialScores
                return [FinancialScores(**cached)]

        score = await self.specialized_fetcher.fetch_financial_scores(symbol)

        if score and self.cache:
            await self.cache.set(symbol, "financial_scores", score.to_dict())

        return [score] if score else []

    async def _fetch_dcf(self, symbol: str):
        """Fetch DCF valuation with caching."""
        if self.cache:
            cached = await self.cache.get(symbol, "dcf_valuation")
            if cached:
                from .models import DCFValuation
                return DCFValuation(**cached)

        dcf = await self.specialized_fetcher.fetch_dcf(symbol)

        if dcf and self.cache:
            await self.cache.set(symbol, "dcf_valuation", dcf.to_dict())

        return dcf

    async def _fetch_enterprise_values(self, symbol: str, period: str, limit: int):
        """Fetch enterprise values with caching."""
        period_key = f"{period}_{limit}"
        if self.cache:
            cached = await self.cache.get(symbol, "enterprise_values", period_key)
            if cached:
                from .models import EnterpriseValue
                return [EnterpriseValue(**item) for item in cached]

        values = await self.specialized_fetcher.fetch_enterprise_values(
            symbol, period, limit
        )

        if values and self.cache:
            await self.cache.set(
                symbol,
                "enterprise_values",
                [v.to_dict() for v in values],
                period_key,
            )

        return values

    async def _fetch_analyst_estimates(self, symbol: str, period: str, limit: int):
        """Fetch analyst estimates."""
        return await self.specialized_fetcher.fetch_analyst_estimates(
            symbol, period, limit
        )

    async def _fetch_price_targets(self, symbol: str):
        """Fetch price targets."""
        return await self.specialized_fetcher.fetch_price_targets(symbol)

    async def _fetch_price_target_summary(self, symbol: str):
        """Fetch price target summary."""
        return await self.specialized_fetcher.fetch_price_target_summary(symbol)

    async def _fetch_analyst_grades(self, symbol: str):
        """Fetch analyst grades."""
        return await self.specialized_fetcher.fetch_analyst_grades(symbol)

    async def _fetch_institutional_holders(self, symbol: str):
        """Fetch institutional holders."""
        return await self.specialized_fetcher.fetch_institutional_holders(symbol)

    async def _fetch_insider_trades(self, symbol: str, days: int):
        """Fetch insider trades."""
        return await self.specialized_fetcher.fetch_insider_trades(symbol)

    async def _fetch_historical_prices(self, symbol: str, days: int):
        """Fetch historical prices."""
        from datetime import date, timedelta

        to_date = date.today()
        from_date = to_date - timedelta(days=days)

        return await self.specialized_fetcher.fetch_historical_prices(
            symbol,
            from_date.isoformat(),
            to_date.isoformat(),
        )

    async def _fetch_transcripts(self, symbol: str, count: int):
        """Fetch transcripts."""
        # Note: Implementation simplified - would need to determine quarters
        return []

    async def _fetch_sec_filings(self, symbol: str, types: Optional[List[str]], count: int):
        """Fetch SEC filings."""
        return await self.specialized_fetcher.fetch_sec_filings(
            symbol, types[0] if types else None, count
        )

    async def _fetch_news(self, symbol: str, count: int):
        """Fetch news."""
        return await self.specialized_fetcher.fetch_news(symbol, count)

    # Convenience methods

    async def get_quote(self, symbol: str) -> Optional[Quote]:
        """Get real-time quote for a symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Quote object or None
        """
        request = DataRequest(symbol=symbol, include_quote=True)
        data = await self.get_ticker_data(request)
        return data.quote

    async def get_profile(self, symbol: str) -> Optional[CompanyProfile]:
        """Get company profile for a symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            CompanyProfile object or None
        """
        request = DataRequest(symbol=symbol, include_profile=True)
        data = await self.get_ticker_data(request)
        return data.profile

    # Cache management

    async def get_cache_info(self, symbol: Optional[str] = None) -> Dict:
        """Get cache information.

        Args:
            symbol: Optional stock ticker symbol for per-symbol stats

        Returns:
            Dictionary with cache statistics
        """
        if not self.cache:
            return {"enabled": False}
        return await self.cache.get_cache_info(symbol)

    async def clear_cache(self, symbol: Optional[str] = None) -> bool:
        """Clear cache.

        Args:
            symbol: Optional symbol to clear (clears all if None)

        Returns:
            True if successful
        """
        if not self.cache:
            return False
        return await self.cache.clear_cache(symbol)

    # Rate limiting

    def get_rate_limit_status(self) -> Dict:
        """Get current rate limit status.

        Returns:
            Dictionary with rate limit information
        """
        return self.fetcher.get_rate_limit_status()

    def set_rate_limit(self, calls_per_minute: int) -> None:
        """Update rate limit.

        Args:
            calls_per_minute: New rate limit
        """
        self.fetcher.set_rate_limit(calls_per_minute)
