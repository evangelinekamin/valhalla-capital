"""Command-line interface for FMP Data Client."""

import asyncio
import json
import sys
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from fmp_data_client import FMPDataClient
from fmp_data_client.config import FMPConfig
from fmp_data_client.models.request import DataRequest

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="fmp-client")
def cli():
    """
    FMP Data Client - Financial data from Financial Modeling Prep API.

    A comprehensive Python client for fetching and analyzing financial market data.
    """
    pass


@cli.command()
@click.argument("symbol")
@click.option("--json", "output_json", is_flag=True, help="Output in JSON format")
def quote(symbol: str, output_json: bool):
    """
    Get real-time quote for a symbol.

    Example:
        fmp quote AAPL
        fmp quote MSFT --json
    """

    async def _get_quote():
        async with FMPDataClient.from_env() as client:
            quote_data = await client.get_quote(symbol.upper())

            if output_json:
                click.echo(quote_data.model_dump_json(indent=2, by_alias=True))
            else:
                _display_quote(quote_data)

    asyncio.run(_get_quote())


def _display_quote(quote):
    """Display quote in a formatted table."""
    table = Table(title=f"{quote.symbol} - {quote.name or 'Quote'}")

    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    # Price info
    change_color = "green" if quote.is_positive_change else "red"
    table.add_row("Price", f"${quote.price:.2f}")
    table.add_row(
        "Change",
        f"[{change_color}]{quote.change:+.2f} ({quote.change_percent:+.2f}%)[/{change_color}]",
    )

    # Trading info
    table.add_row("Open", f"${quote.open:.2f}" if quote.open else "N/A")
    table.add_row(
        "High / Low", f"${quote.day_high:.2f} / ${quote.day_low:.2f}" if quote.day_high else "N/A"
    )
    table.add_row(
        "Volume", f"{quote.volume:,}" if quote.volume else "N/A"
    )

    # Valuation
    if quote.market_cap:
        if quote.market_cap >= 1e12:
            market_cap_str = f"${quote.market_cap / 1e12:.2f}T"
        elif quote.market_cap >= 1e9:
            market_cap_str = f"${quote.market_cap / 1e9:.2f}B"
        elif quote.market_cap >= 1e6:
            market_cap_str = f"${quote.market_cap / 1e6:.2f}M"
        else:
            market_cap_str = f"${quote.market_cap:,.0f}"
    else:
        market_cap_str = "N/A"
    table.add_row("Market Cap", market_cap_str)
    table.add_row("P/E Ratio", f"{quote.pe:.2f}" if quote.pe else "N/A")

    console.print(table)


@cli.command()
@click.argument("symbol")
@click.option("--json", "output_json", is_flag=True, help="Output in JSON format")
def profile(symbol: str, output_json: bool):
    """
    Get company profile information.

    Example:
        fmp profile AAPL
        fmp profile GOOGL --json
    """

    async def _get_profile():
        async with FMPDataClient.from_env() as client:
            profile_data = await client.get_profile(symbol.upper())

            if output_json:
                click.echo(profile_data.model_dump_json(indent=2, by_alias=True))
            else:
                _display_profile(profile_data)

    asyncio.run(_get_profile())


def _display_profile(profile):
    """Display company profile in a formatted table."""
    table = Table(title=f"{profile.symbol} - {profile.name}")

    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    # Company info
    table.add_row("Industry", profile.industry or "N/A")
    table.add_row("Sector", profile.sector or "N/A")
    table.add_row("Country", profile.country or "N/A")
    table.add_row("Exchange", profile.exchange or "N/A")

    # Leadership
    table.add_row("CEO", profile.ceo or "N/A")
    table.add_row("Employees", f"{profile.employees:,}" if profile.employees else "N/A")

    # Valuation
    table.add_row("Market Cap", profile.market_cap_formatted)
    table.add_row("Price", f"${profile.price:.2f}" if profile.price else "N/A")

    # Contact
    table.add_row("Website", profile.website or "N/A")
    table.add_row("Location", f"{profile.city}, {profile.state}" if profile.city else "N/A")

    console.print(table)

    if profile.description:
        console.print(f"\n[bold]Description:[/bold]")
        console.print(profile.description[:500] + "..." if len(profile.description) > 500 else profile.description)


@cli.command()
@click.argument("symbol")
@click.option("--periods", default=4, help="Number of periods to fetch (default: 4)")
@click.option("--output", "-o", type=click.Choice(["table", "json"]), default="table", help="Output format")
def fundamentals(symbol: str, periods: int, output: str):
    """
    Get fundamental financial data.

    Example:
        fmp fundamentals AAPL
        fmp fundamentals MSFT --periods 8 --output json
    """

    async def _get_fundamentals():
        async with FMPDataClient.from_env() as client:
            request = DataRequest(
                symbol=symbol.upper(),
                include_fundamentals=True,
                fundamentals_periods=periods,
            )

            data = await client.get_ticker_data(request)

            if output == "json":
                click.echo(data.model_dump_json(indent=2))
            else:
                _display_fundamentals(data)

    asyncio.run(_get_fundamentals())


def _display_fundamentals(data):
    """Display fundamental data in formatted tables."""
    if not data.income_statements:
        console.print("[red]No fundamental data available[/red]")
        return

    # Income Statement
    console.print(f"\n[bold cyan]{data.symbol} - Income Statements[/bold cyan]\n")
    income_table = Table()
    income_table.add_column("Period", style="cyan")
    income_table.add_column("Revenue", style="green")
    income_table.add_column("Gross Profit", style="green")
    income_table.add_column("Net Income", style="green")
    income_table.add_column("EPS", style="yellow")

    for stmt in data.income_statements[:4]:
        income_table.add_row(
            stmt.period_date.strftime("%Y-%m-%d"),
            f"${stmt.revenue / 1e9:.2f}B" if stmt.revenue else "N/A",
            f"${stmt.gross_profit / 1e9:.2f}B" if stmt.gross_profit else "N/A",
            f"${stmt.net_income / 1e9:.2f}B" if stmt.net_income else "N/A",
            f"${stmt.eps:.2f}" if stmt.eps else "N/A",
        )

    console.print(income_table)

    # Balance Sheet
    if data.balance_sheets:
        console.print(f"\n[bold cyan]{data.symbol} - Balance Sheets[/bold cyan]\n")
        balance_table = Table()
        balance_table.add_column("Period", style="cyan")
        balance_table.add_column("Total Assets", style="green")
        balance_table.add_column("Total Liabilities", style="red")
        balance_table.add_column("Total Equity", style="green")

        for bs in data.balance_sheets[:4]:
            balance_table.add_row(
                bs.date.strftime("%Y-%m-%d"),
                f"${bs.total_assets / 1e9:.2f}B" if bs.total_assets else "N/A",
                f"${bs.total_liabilities / 1e9:.2f}B" if bs.total_liabilities else "N/A",
                f"${bs.total_stockholders_equity / 1e9:.2f}B" if bs.total_stockholders_equity else "N/A",
            )

        console.print(balance_table)


@cli.command()
@click.argument("symbol")
@click.option("--full", is_flag=True, help="Include all data (slow, uses many API calls)")
@click.option("--output", "-o", type=click.Choice(["summary", "json"]), default="summary")
def analyze(symbol: str, full: bool, output: str):
    """
    Comprehensive analysis of a stock.

    Example:
        fmp analyze AAPL
        fmp analyze MSFT --full --output json
    """

    async def _analyze():
        async with FMPDataClient.from_env() as client:
            request = DataRequest(
                symbol=symbol.upper(),
                include_quote=True,
                include_profile=True,
                include_fundamentals=True,
                fundamentals_periods=4,
            )

            if full:
                request.enable_full_analysis()

            data = await client.get_ticker_data(request)

            if output == "json":
                click.echo(data.model_dump_json(indent=2))
            else:
                console.print(data.summary())

    asyncio.run(_analyze())


@cli.group()
def cache():
    """Cache management commands."""
    pass


@cache.command("status")
def cache_status():
    """Show cache status and statistics."""

    async def _cache_status():
        async with FMPDataClient.from_env() as client:
            info = await client.get_cache_info()

            table = Table(title="Cache Status")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="white")

            for key, value in info.items():
                table.add_row(str(key).title(), str(value))

            console.print(table)

    asyncio.run(_cache_status())


@cache.command("clear")
@click.confirmation_option(prompt="Are you sure you want to clear the cache?")
def cache_clear():
    """Clear all cached data."""

    async def _cache_clear():
        async with FMPDataClient.from_env() as client:
            await client.clear_cache()
            console.print("[green]Cache cleared successfully[/green]")

    asyncio.run(_cache_clear())


@cli.group()
def config():
    """Configuration management."""
    pass


@config.command("show")
def config_show():
    """Show current configuration."""
    try:
        cfg = FMPConfig.from_env()
        safe_config = cfg.model_dump_safe()

        table = Table(title="FMP Client Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="white")

        for key, value in safe_config.items():
            table.add_row(str(key), str(value))

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        sys.exit(1)


@config.command("test")
def config_test():
    """Test API connection."""

    async def _test_connection():
        try:
            async with FMPDataClient.from_env() as client:
                # Try to fetch a quote
                quote = await client.get_quote("AAPL")
                console.print("[green]✓ API connection successful![/green]")
                console.print(f"Test quote: AAPL @ ${quote.price:.2f}")

                # Show rate limit status
                status = client.get_rate_limit_status()
                console.print(f"\nRate limit: {status['calls_per_minute']} calls/minute")
                console.print(f"Available tokens: {status['tokens_remaining']:.0f}")

        except Exception as e:
            console.print(f"[red]✗ API connection failed: {e}[/red]")
            sys.exit(1)

    asyncio.run(_test_connection())


@cli.command()
def rate_limit():
    """Show current rate limit status."""

    async def _rate_limit():
        async with FMPDataClient.from_env() as client:
            status = client.get_rate_limit_status()

            table = Table(title="Rate Limit Status")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="white")

            table.add_row("Calls per Minute", str(status["calls_per_minute"]))
            table.add_row("Available Tokens", f"{status['tokens_remaining']:.2f}")
            table.add_row("Refill Rate", f"{status['refill_rate_per_second']:.2f} tokens/sec")

            console.print(table)

    asyncio.run(_rate_limit())


def main():
    """Main entry point for the CLI."""
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
