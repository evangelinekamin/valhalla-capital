"""FMP Data Client - Comprehensive Python library for Financial Modeling Prep API.

This library provides:
- Type-safe data models for all FMP API endpoints
- Async API client with tier-aware access control
- MySQL-based caching with intelligent TTL policies
- LLM-powered summarization for transcripts and SEC filings (optional)
- Institutional ownership analysis and holder classification (optional)
- CLI and REST API interfaces (optional)

Basic usage:
    import asyncio
    from fmp_data_client import FMPDataClient, DataRequest

    async def main():
        async with FMPDataClient.from_env() as client:
            # Get a quote
            quote = await client.get_quote("AAPL")
            print(f"AAPL: ${quote.price}")

            # Get comprehensive data
            request = DataRequest(
                symbol="AAPL",
                include_quote=True,
                include_profile=True,
                include_fundamentals=True,
            )
            data = await client.get_ticker_data(request)

    asyncio.run(main())
"""

__version__ = "0.1.0"

from .client import FMPDataClient
from .config import FMPConfig, Tier
from .models import DataRequest, TickerData

# Optional imports - only available if dependencies are installed
try:
    from .summarizer import BaseSummarizer, TranscriptSummarizer, FilingSummarizer

    _summarizer_available = True
except ImportError:
    _summarizer_available = False

__all__ = [
    "__version__",
    "FMPDataClient",
    "FMPConfig",
    "Tier",
    "DataRequest",
    "TickerData",
]

if _summarizer_available:
    __all__.extend(["BaseSummarizer", "TranscriptSummarizer", "FilingSummarizer"])
