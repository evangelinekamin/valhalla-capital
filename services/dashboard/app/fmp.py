"""
Valhalla Capital Dashboard - FMP Price Client

Fetches live quotes from the FMP proxy on 247 to compute
unrealized P&L for portfolio positions. Includes an in-memory
TTL cache to avoid hammering the API on every page load.
"""

import logging
import time
from typing import Any

import httpx

from .config import DashboardConfig

logger = logging.getLogger(__name__)

# In-memory quote cache: {ticker: {data: {...}, fetched_at: float}}
_quote_cache: dict[str, dict] = {}
_CACHE_TTL = 300  # 5 minutes


async def fetch_quotes(
    config: DashboardConfig, tickers: list[str]
) -> dict[str, dict[str, Any]]:
    """
    Fetch live quotes for a list of tickers from the FMP proxy.
    Returns {ticker: {price, change, change_percent, ...}} for each ticker.
    Missing or failed tickers are silently omitted.
    Results are cached for 5 minutes.
    """
    if not config.fmp_proxy_url or not tickers:
        return {}

    now = time.monotonic()
    results: dict[str, dict[str, Any]] = {}
    to_fetch: list[str] = []

    for ticker in tickers:
        cached = _quote_cache.get(ticker)
        if cached and (now - cached["fetched_at"]) < _CACHE_TTL:
            results[ticker] = cached["data"]
        else:
            to_fetch.append(ticker)

    if not to_fetch:
        return results

    async with httpx.AsyncClient(timeout=10) as client:
        for ticker in to_fetch:
            try:
                resp = await client.get(
                    f"{config.fmp_proxy_url}/quote/{ticker}",
                    headers={"X-API-Key": config.fmp_api_key},
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list) and data:
                    results[ticker] = data[0]
                    _quote_cache[ticker] = {"data": data[0], "fetched_at": now}
                elif isinstance(data, dict) and data.get("price"):
                    results[ticker] = data
                    _quote_cache[ticker] = {"data": data, "fetched_at": now}
            except Exception as e:
                logger.debug(f"FMP quote failed for {ticker}: {e}")

    return results


def enrich_positions(
    positions: list[dict], quotes: dict[str, dict]
) -> list[dict]:
    """
    Merge live quotes into portfolio positions to compute
    current market value and unrealized P&L.
    """
    enriched = []
    for pos in positions:
        ticker = pos.get("ticker", "")
        quote = quotes.get(ticker, {})
        current_price = quote.get("price")

        entry = {**pos}

        if current_price and pos.get("quantity") and pos.get("avg_price"):
            qty = float(pos["quantity"])
            avg = float(pos["avg_price"])
            entry["current_price"] = current_price
            entry["market_value"] = current_price * qty
            entry["unrealized_pnl"] = (current_price - avg) * qty
            entry["unrealized_pnl_pct"] = ((current_price - avg) / avg * 100) if avg else 0
        enriched.append(entry)
    return enriched
