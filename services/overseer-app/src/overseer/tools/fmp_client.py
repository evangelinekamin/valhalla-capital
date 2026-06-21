from __future__ import annotations

from datetime import date, datetime

import httpx
import structlog

from overseer.config import OverseerSettings

log = structlog.get_logger()

TIMEOUT = 30


async def get_quote(settings: OverseerSettings, symbol: str) -> dict:
    url = f"{settings.fmp_base_url}/quote/{symbol}"
    headers = {"X-API-Key": settings.fmp_local_api_key}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        log.error("get_quote_failed", symbol=symbol, error=str(e))
        return {"error": str(e)}


async def get_profile(settings: OverseerSettings, symbol: str) -> dict:
    url = f"{settings.fmp_base_url}/profile/{symbol}"
    headers = {"X-API-Key": settings.fmp_local_api_key}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        log.error("get_profile_failed", symbol=symbol, error=str(e))
        return {"error": str(e)}


async def get_fmp_data(
    settings: OverseerSettings,
    symbol: str,
    include_quote: bool = True,
    include_fundamentals: bool = True,
    include_profile: bool = False,
) -> dict:
    url = f"{settings.fmp_base_url}/ticker"
    headers = {"X-API-Key": settings.fmp_local_api_key}
    payload = {
        "symbol": symbol,
        "include_quote": include_quote,
        "include_fundamentals": include_fundamentals,
        "include_profile": include_profile,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        log.error("get_fmp_data_failed", symbol=symbol, error=str(e))
        return {"error": str(e)}


async def get_earnings_calendar(settings: OverseerSettings, symbol: str) -> dict:
    """Fetch upcoming earnings dates from FMP stable API directly.

    Uses a 90-day window to keep result set small enough to find the target symbol.
    """
    from datetime import timedelta

    today = date.today()
    date_from = today.isoformat()
    date_to = (today + timedelta(days=90)).isoformat()

    url = "https://financialmodelingprep.com/stable/earnings-calendar"
    params = {
        "from": date_from,
        "to": date_to,
        "apikey": settings.fmp_api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            all_earnings = response.json()

        if not isinstance(all_earnings, list):
            return {
                "symbol": symbol,
                "next_earnings": None,
                "upcoming_earnings": [],
            }

        symbol_upper = symbol.upper()
        matches = [e for e in all_earnings if (e.get("symbol") or "").upper() == symbol_upper]

        future_earnings = []
        for entry in matches:
            earnings_date_str = entry.get("date")
            if not earnings_date_str:
                continue
            try:
                earnings_date = datetime.strptime(earnings_date_str[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            if earnings_date >= today:
                future_earnings.append({
                    "date": earnings_date.isoformat(),
                    "days_until": (earnings_date - today).days,
                    "eps_estimated": entry.get("epsEstimated"),
                    "revenue_estimated": entry.get("revenueEstimated"),
                    "time": entry.get("time"),
                })

        future_earnings.sort(key=lambda e: e["days_until"])
        next_earnings = future_earnings[0] if future_earnings else None

        return {
            "symbol": symbol,
            "next_earnings": next_earnings,
            "upcoming_earnings": future_earnings[:3],
        }

    except Exception as e:
        log.error("get_earnings_calendar_failed", symbol=symbol, error=str(e))
        return {
            "symbol": symbol,
            "next_earnings": None,
            "upcoming_earnings": [],
            "error": str(e),
        }


async def get_benchmark_return(
    settings: OverseerSettings,
    inception_date: str,
    benchmark_symbol: str = "SPY",
) -> dict:
    """Fetch benchmark (SPY) return from inception date to today.

    Uses the FMP stable historical-price-eod endpoint for inception price
    and the local FMP proxy for the current quote.
    """
    today = date.today()

    eod_url = "https://financialmodelingprep.com/stable/historical-price-eod/full"
    eod_params = {
        "symbol": benchmark_symbol,
        "from": inception_date,
        "to": inception_date,
        "apikey": settings.fmp_api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            eod_resp = await client.get(eod_url, params=eod_params)
            eod_resp.raise_for_status()
            eod_data = eod_resp.json()

        if not eod_data or not isinstance(eod_data, list):
            return {"error": f"No historical data for {benchmark_symbol} on {inception_date}"}

        inception_price = eod_data[0].get("close")
        if not inception_price or inception_price <= 0:
            return {"error": f"Invalid inception price for {benchmark_symbol}"}

        current_quote = await get_quote(settings, benchmark_symbol)
        # get_quote returns a list (FMP /quote endpoint shape) on success or
        # {"error": ...} on failure. The prior code called .get/in on the
        # list, which always raised AttributeError, which the outer
        # try/except swallowed — the benchmark was silently broken.
        if isinstance(current_quote, dict) and "error" in current_quote:
            return {"error": f"Could not fetch current {benchmark_symbol} quote: {current_quote['error']}"}

        quote_entry = current_quote[0] if isinstance(current_quote, list) and current_quote else current_quote
        if not isinstance(quote_entry, dict):
            return {"error": f"Unexpected quote shape for {benchmark_symbol}: {type(quote_entry).__name__}"}

        current_price = quote_entry.get("price", 0)
        if not current_price or current_price <= 0:
            return {"error": f"Invalid current price for {benchmark_symbol}"}

        benchmark_return_pct = ((current_price / inception_price) - 1) * 100
        days_held = (today - date.fromisoformat(inception_date)).days

        return {
            "benchmark": benchmark_symbol,
            "inception_date": inception_date,
            "inception_price": inception_price,
            "current_date": today.isoformat(),
            "current_price": current_price,
            "benchmark_return_pct": round(benchmark_return_pct, 2),
            "days_held": days_held,
        }

    except Exception as e:
        log.error("get_benchmark_return_failed", error=str(e))
        return {"error": str(e)}


async def check_health(settings: OverseerSettings) -> dict:
    url = f"{settings.fmp_base_url}/health"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        log.error("check_health_failed", error=str(e))
        return {"error": str(e)}
