from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import asyncpg
import structlog

from overseer.config import OverseerSettings
from overseer.memory import working
from overseer.models.trading import Position, PortfolioState
from overseer.tools import fmp_client, ibkr_client
from overseer.utils.database import fetch

log = structlog.get_logger()


async def _enrich_with_fmp_quotes(
    settings: OverseerSettings,
    state: PortfolioState,
) -> PortfolioState:
    """Overlay fresh FMP quotes on IBKR positions to ensure current prices."""
    if not state.positions:
        return state

    tasks = [
        fmp_client.get_quote(settings, pos.ticker)
        for pos in state.positions
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    enriched_positions = []
    for pos, result in zip(state.positions, results):
        if isinstance(result, Exception) or (isinstance(result, dict) and "error" in result):
            enriched_positions.append(pos.model_copy(update={"price_source": "ibkr"}))
            continue

        quote = result[0] if isinstance(result, list) and result else result
        if not isinstance(quote, dict):
            enriched_positions.append(pos.model_copy(update={"price_source": "ibkr"}))
            continue

        fmp_price = quote.get("price")
        if fmp_price is not None and fmp_price > 0:
            market_value = fmp_price * pos.quantity
            unrealized_pnl = (fmp_price - pos.avg_cost) * pos.quantity
            unrealized_pnl_pct = (
                ((fmp_price / pos.avg_cost) - 1) * 100
                if pos.avg_cost > 0
                else 0.0
            )
            enriched_positions.append(pos.model_copy(update={
                "current_price": fmp_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "price_source": "fmp",
            }))
            if pos.current_price and abs(fmp_price - pos.current_price) / pos.current_price > 0.02:
                log.warning(
                    "price_source_divergence",
                    ticker=pos.ticker,
                    ibkr_price=pos.current_price,
                    fmp_price=fmp_price,
                    divergence_pct=round(
                        abs(fmp_price - pos.current_price) / pos.current_price * 100, 2
                    ),
                )
        else:
            enriched_positions.append(pos.model_copy(update={"price_source": "ibkr"}))

    return state.model_copy(update={
        "positions": enriched_positions,
    })


async def get_portfolio_state(
    pool: asyncpg.Pool,
    settings: OverseerSettings,
) -> PortfolioState:
    try:
        state = await ibkr_client.get_portfolio_state(settings)

        now = datetime.now(timezone.utc)
        ts = state.timestamp if state.timestamp.tzinfo else state.timestamp.replace(tzinfo=timezone.utc)
        data_age = (now - ts).total_seconds()
        state = state.model_copy(update={"data_age_seconds": data_age})

        state = await _enrich_with_fmp_quotes(settings, state)

        await working.set(pool, "portfolio_value", state.total_value)
        await working.set(pool, "portfolio_state_cached", state.model_dump())
        log.debug(
            "portfolio_state_enriched",
            total_value=state.total_value,
            data_age_seconds=round(data_age, 1),
            price_sources=[p.price_source for p in state.positions],
        )
        return state
    except Exception as e:
        log.warning("portfolio_state_ibkr_failed", error=str(e), using_cache=True)
        try:
            cached = await working.get(pool, "portfolio_state_cached")
            if cached:
                return PortfolioState(**cached)
        except Exception as cache_err:
            log.error("portfolio_state_cache_failed", error=str(cache_err))

        return PortfolioState()


async def get_sector_exposure(
    settings: OverseerSettings,
    positions: list[Position],
) -> dict:
    sectors: dict[str, dict[str, float]] = {}
    total_value = sum(p.market_value or 0.0 for p in positions)

    if total_value <= 0:
        return {"sectors": {}}

    for position in positions:
        if not position.market_value or position.market_value <= 0:
            continue

        try:
            profile_data = await fmp_client.get_profile(settings, position.ticker)
            if "error" in profile_data or not profile_data:
                log.warning("sector_profile_failed", ticker=position.ticker)
                sector = "Unknown"
            else:
                profile = profile_data[0] if isinstance(profile_data, list) else profile_data
                sector = profile.get("sector", "Unknown")

            if sector not in sectors:
                sectors[sector] = {"value": 0.0, "pct": 0.0}

            sectors[sector]["value"] += position.market_value

        except Exception as e:
            log.error("sector_lookup_failed", ticker=position.ticker, error=str(e))
            sector = "Unknown"
            if sector not in sectors:
                sectors[sector] = {"value": 0.0, "pct": 0.0}
            sectors[sector]["value"] += position.market_value

    for sector_data in sectors.values():
        sector_data["pct"] = (sector_data["value"] / total_value) * 100

    return {"sectors": sectors}


async def get_portfolio_analytics(
    pool: asyncpg.Pool,
    settings: OverseerSettings,
) -> dict:
    try:
        state = await get_portfolio_state(pool, settings)

        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        trades = await fetch(
            pool,
            """
            SELECT
                ticker,
                action,
                quantity,
                price,
                fill_price,
                status,
                outcome,
                outcome_pnl,
                created_at,
                filled_at
            FROM trades
            WHERE created_at >= $1
            ORDER BY created_at DESC
            """,
            thirty_days_ago,
        )

        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t["outcome_pnl"] and t["outcome_pnl"] > 0)
        losing_trades = sum(1 for t in trades if t["outcome_pnl"] and t["outcome_pnl"] < 0)
        pending_trades = sum(1 for t in trades if t["status"] == "pending")

        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0

        winning_pnls = [t["outcome_pnl"] for t in trades if t["outcome_pnl"] and t["outcome_pnl"] > 0]
        losing_pnls = [abs(t["outcome_pnl"]) for t in trades if t["outcome_pnl"] and t["outcome_pnl"] < 0]

        avg_gain = (sum(winning_pnls) / len(winning_pnls)) if winning_pnls else 0.0
        avg_loss = (sum(losing_pnls) / len(losing_pnls)) if losing_pnls else 0.0

        total_gains = sum(winning_pnls)
        total_losses = sum(losing_pnls)
        # profit_factor = gains/losses. Undefined when losses == 0:
        # 0.0 means worst-possible (all losers), so returning 0.0 for a
        # perfect all-winner run would tell the LLM the opposite of the
        # truth. Return None to signal "no losses yet, ratio undefined".
        if total_losses > 0:
            profit_factor = total_gains / total_losses
        elif total_gains > 0:
            profit_factor = None  # all winners — ratio undefined
        else:
            profit_factor = 0.0  # no closed trades with PnL either way

        sector_data = {}
        if state.positions:
            sector_data = await get_sector_exposure(settings, state.positions)

        return {
            "portfolio_value": state.total_value,
            "cash": state.cash,
            "positions_count": len(state.positions),
            "daily_pnl": state.daily_pnl,
            "daily_pnl_pct": state.daily_pnl_pct,
            "last_30_days": {
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "pending_trades": pending_trades,
                "win_rate": win_rate,
                "avg_gain": avg_gain,
                "avg_loss": avg_loss,
                "profit_factor": profit_factor,
                "total_pnl": total_gains - total_losses,
            },
            "sector_exposure": sector_data,
        }

    except Exception as e:
        log.error("portfolio_analytics_failed", error=str(e), exc_info=True)
        return {
            "error": str(e),
            "portfolio_value": 0.0,
            "cash": 0.0,
            "positions_count": 0,
        }
