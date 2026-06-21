#!/usr/bin/env python3
"""Basic usage example for FMP Data Client.

Before running:
1. Set environment variable: export FMP_API_KEY=your_api_key_here
2. Optional: export FMP_TIER=premium (default: starter)
3. Install: pip install -e .
"""

import asyncio

from fmp_data_client import FMPDataClient, DataRequest, FMPConfig, Tier


async def example_quote():
    """Example: Get a simple quote."""
    print("\n=== Example 1: Get Quote ===")

    # Create client from environment variables
    async with FMPDataClient.from_env() as client:
        quote = await client.get_quote("AAPL")

        if quote:
            print(f"Symbol: {quote.symbol}")
            print(f"Price: ${quote.price:.2f}")
            print(f"Change: {quote.change:+.2f} ({quote.change_percent:+.2f}%)")
            print(f"Volume: {quote.volume:,}")
            print(f"Day Range: ${quote.day_low:.2f} - ${quote.day_high:.2f}")


async def example_profile():
    """Example: Get company profile."""
    print("\n=== Example 2: Get Company Profile ===")

    async with FMPDataClient.from_env() as client:
        profile = await client.get_profile("AAPL")

        if profile:
            print(f"Company: {profile.name}")
            print(f"Sector: {profile.sector}")
            print(f"Industry: {profile.industry}")
            print(f"CEO: {profile.ceo}")
            print(f"Employees: {profile.employees:,}")
            print(f"Market Cap: {profile.market_cap_formatted}")
            print(f"Website: {profile.website}")
            print(f"\nDescription: {profile.description[:200]}...")


async def example_comprehensive():
    """Example: Get comprehensive data."""
    print("\n=== Example 3: Comprehensive Data Request ===")

    # Create custom configuration
    config = FMPConfig(
        api_key="your_api_key_here",  # Replace with your API key
        tier=Tier.STARTER,
        cache_enabled=False,  # Disable cache for this example
        summarization_enabled=False,
    )

    async with FMPDataClient(config) as client:
        # Build comprehensive request
        request = DataRequest(
            symbol="AAPL",
            include_quote=True,
            include_profile=True,
            include_fundamentals=True,
            fundamentals_periods=4,
            fundamentals_period_type="quarter",
            include_dividends=True,
            include_historical_prices=True,
            historical_days=30,
        )

        print(f"Fetching data for {request.symbol}...")
        print(f"Enabled features: {len(request.get_enabled_features())}")

        data = await client.get_ticker_data(request)

        # Display summary
        print(f"\nData Summary for {data.symbol}:")
        summary = data.summary()
        for key, value in summary.items():
            if key != "symbol":
                print(f"  {key}: {value}")

        # Display latest fundamentals if available
        if data.income_statements:
            latest_income = data.get_latest_income_statement()
            if latest_income:
                print(f"\nLatest Income Statement ({latest_income.period}):")
                print(f"  Revenue: ${latest_income.revenue:,.0f}")
                print(f"  Net Income: ${latest_income.net_income:,.0f}")
                print(f"  EPS: ${latest_income.eps:.2f}")
                print(f"  Gross Margin: {latest_income.gross_profit_ratio*100:.1f}%")


async def example_multiple_symbols():
    """Example: Fetch data for multiple symbols."""
    print("\n=== Example 4: Multiple Symbols ===")

    async with FMPDataClient.from_env() as client:
        symbols = ["AAPL", "MSFT", "GOOGL"]

        # Fetch quotes for all symbols concurrently
        tasks = [client.get_quote(symbol) for symbol in symbols]
        quotes = await asyncio.gather(*tasks)

        print("\nQuick Market Overview:")
        for quote in quotes:
            if quote:
                print(
                    f"{quote.symbol:6} ${quote.price:8.2f}  "
                    f"{quote.change_percent:+6.2f}%  "
                    f"Vol: {quote.volume:,}"
                )


async def main():
    """Run all examples."""
    print("=" * 60)
    print("FMP Data Client - Basic Examples")
    print("=" * 60)

    try:
        await example_quote()
        await example_profile()
        await example_comprehensive()
        await example_multiple_symbols()

        print("\n" + "=" * 60)
        print("Examples completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\nError: {e}")
        print("\nMake sure to set FMP_API_KEY environment variable")
        print("Example: export FMP_API_KEY=your_key_here")


if __name__ == "__main__":
    asyncio.run(main())
