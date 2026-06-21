"""
Comprehensive stock analysis example using FMP Data Client.

This example demonstrates:
1. Fetching comprehensive data for a stock
2. Using LLM summarization for transcripts
3. Analyzing fundamentals and valuation
4. Working with institutional ownership
5. Caching and rate limiting
"""

import asyncio
import os
from fmp_data_client import FMPDataClient, DataRequest
from fmp_data_client.summarizer import TranscriptSummarizer


async def analyze_stock(symbol: str):
    """Perform comprehensive stock analysis."""

    print(f"\n{'='*60}")
    print(f"Comprehensive Analysis: {symbol}")
    print(f"{'='*60}\n")

    async with FMPDataClient.from_env() as client:
        # Create a comprehensive request
        request = DataRequest(symbol=symbol)
        request.enable_full_analysis()
        request.fundamentals_periods = 4

        print("Fetching data from FMP API...")
        data = await client.get_ticker_data(request)

        # Display summary
        print("\n" + data.summary())

        # Detailed sections
        print("\n--- VALUATION METRICS ---")
        if data.key_metrics_list:
            latest_metrics = data.key_metrics_list[0]
            print(f"P/E Ratio: {latest_metrics.pe_ratio:.2f}")
            print(f"Price to Sales: {latest_metrics.price_to_sales_ratio:.2f}")
            print(f"Price to Book: {latest_metrics.pb_ratio:.2f}")
            print(f"Debt to Equity: {latest_metrics.debt_to_equity:.2f}")
            print(f"ROE: {latest_metrics.roe:.2%}")

        # Financial trends
        print("\n--- REVENUE & EARNINGS TRENDS ---")
        if len(data.income_statements) >= 4:
            for stmt in data.income_statements[:4]:
                print(
                    f"{stmt.date.strftime('%Y-%m-%d')}: "
                    f"Revenue ${stmt.revenue/1e9:.2f}B, "
                    f"Net Income ${stmt.net_income/1e9:.2f}B, "
                    f"EPS ${stmt.eps:.2f}"
                )

        # Analyst sentiment
        print("\n--- ANALYST ESTIMATES ---")
        if data.analyst_estimates:
            for estimate in data.analyst_estimates[:2]:
                print(
                    f"{estimate.date.strftime('%Y-%m-%d')}: "
                    f"Est. Revenue ${estimate.estimated_revenue_avg/1e9:.2f}B, "
                    f"Est. EPS ${estimate.estimated_eps_avg:.2f}"
                )

        # Institutional ownership
        print("\n--- TOP INSTITUTIONAL HOLDERS ---")
        if data.institutional_holders:
            for holder in data.institutional_holders[:5]:
                change = holder.position_change_type
                print(
                    f"{holder.holder}: "
                    f"{holder.shares:,} shares ({holder.percent_held:.2f}%) - {change}"
                )

        # Recent news
        print("\n--- RECENT NEWS ---")
        if data.news:
            for article in data.news[:3]:
                print(f"- {article.title}")
                print(f"  {article.site} | {article.published_date.strftime('%Y-%m-%d')}")

        # Cache info
        cache_info = await client.get_cache_info()
        print(f"\n--- CACHE STATUS ---")
        print(f"Enabled: {cache_info['enabled']}")

        # Rate limit status
        rate_status = client.get_rate_limit_status()
        print(f"\n--- RATE LIMIT STATUS ---")
        print(f"Calls per minute: {rate_status['calls_per_minute']}")
        print(f"Available tokens: {rate_status['tokens_remaining']:.0f}")


async def analyze_transcript_with_llm(symbol: str, year: int, quarter: int):
    """Fetch and summarize an earnings transcript using LLM."""

    print(f"\n{'='*60}")
    print(f"Earnings Transcript Analysis: {symbol} Q{quarter} {year}")
    print(f"{'='*60}\n")

    async with FMPDataClient.from_env() as client:
        # Fetch transcript
        request = DataRequest(
            symbol=symbol,
            include_transcripts=True,
            transcripts_count=1,
        )

        print("Fetching transcript...")
        data = await client.get_ticker_data(request)

        if not data.earnings_transcripts:
            print("No transcripts available")
            return

        transcript = data.earnings_transcripts[0]

        # Check if summarization is enabled
        if not client.config.summarization_enabled:
            print("\nNote: LLM summarization is disabled. Enable it by setting:")
            print("  export FMP_SUMMARIZATION_ENABLED=true")
            print("  export ANTHROPIC_API_KEY=your_key")
            print("\nTranscript preview:")
            print(transcript.content[:500] + "...")
            return

        # Summarize with LLM
        print("Summarizing transcript with Claude...")
        summarizer = TranscriptSummarizer(client.config)

        summary = await summarizer.summarize_transcript(transcript)

        # Display summary
        print("\n--- EXECUTIVE SUMMARY ---")
        print(summary["executive_summary"])

        print("\n--- KEY METRICS ---")
        for metric in summary["key_metrics"]:
            print(f"  • {metric}")

        print("\n--- FORWARD GUIDANCE ---")
        print(summary["forward_guidance"])

        print("\n--- STRATEGIC THEMES ---")
        for theme in summary["strategic_themes"]:
            print(f"  • {theme}")

        if summary["sentiment"]:
            print("\n--- SENTIMENT ---")
            print(summary["sentiment"])

        if summary["qa_highlights"]:
            print("\n--- Q&A HIGHLIGHTS ---")
            for highlight in summary["qa_highlights"]:
                print(f"  • {highlight}")

        # Token usage
        usage = summarizer.get_token_usage()
        print(f"\n--- TOKEN USAGE ---")
        print(f"Input tokens: {usage['input_tokens']:,}")
        print(f"Output tokens: {usage['output_tokens']:,}")
        print(f"Total tokens: {usage['total_tokens']:,}")

        await summarizer.close()


async def compare_stocks(symbols: list[str]):
    """Compare multiple stocks side-by-side."""

    print(f"\n{'='*60}")
    print(f"Stock Comparison: {', '.join(symbols)}")
    print(f"{'='*60}\n")

    async with FMPDataClient.from_env() as client:
        # Fetch data for all symbols concurrently
        requests = [
            DataRequest(
                symbol=symbol,
                include_quote=True,
                include_profile=True,
                include_fundamentals=True,
                fundamentals_periods=1,
            )
            for symbol in symbols
        ]

        print("Fetching data for all symbols...")
        results = await asyncio.gather(*[client.get_ticker_data(req) for req in requests])

        # Display comparison table
        print(f"\n{'Symbol':<10} {'Price':<12} {'Market Cap':<15} {'P/E':<8} {'Revenue (TTM)':<15}")
        print("-" * 70)

        for data in results:
            price = f"${data.quote.price:.2f}" if data.quote else "N/A"
            mkt_cap = data.profile.market_cap_formatted if data.profile else "N/A"

            pe = "N/A"
            revenue = "N/A"
            if data.income_statements:
                latest = data.income_statements[0]
                revenue = f"${latest.revenue/1e9:.2f}B"
            if data.quote and data.quote.pe:
                pe = f"{data.quote.pe:.2f}"

            print(f"{data.symbol:<10} {price:<12} {mkt_cap:<15} {pe:<8} {revenue:<15}")


async def main():
    """Run all examples."""

    # Check for API key
    if not os.getenv("FMP_API_KEY"):
        print("Error: FMP_API_KEY environment variable is not set")
        print("\nPlease set your API key:")
        print("  export FMP_API_KEY=your_api_key_here")
        return

    # Example 1: Comprehensive analysis
    await analyze_stock("AAPL")

    # Example 2: Compare multiple stocks
    await compare_stocks(["AAPL", "MSFT", "GOOGL"])

    # Example 3: Transcript analysis with LLM (if enabled)
    if os.getenv("FMP_SUMMARIZATION_ENABLED") == "true":
        await analyze_transcript_with_llm("AAPL", 2024, 1)
    else:
        print("\n" + "="*60)
        print("Skipping transcript analysis (LLM not enabled)")
        print("="*60)
        print("\nTo enable LLM summarization:")
        print("  export FMP_SUMMARIZATION_ENABLED=true")
        print("  export ANTHROPIC_API_KEY=your_key")


if __name__ == "__main__":
    asyncio.run(main())
