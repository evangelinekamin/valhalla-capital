"""Anthropic Admin API client for usage and cost reporting."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import structlog

log = structlog.get_logger()

ADMIN_API_BASE = "https://api.anthropic.com/v1/organizations"


async def _request(
    admin_key: str,
    endpoint: str,
    params: list[tuple[str, str]] | None = None,
) -> dict:
    headers = {
        "x-api-key": admin_key,
        "anthropic-version": "2023-06-01",
    }
    url = f"{ADMIN_API_BASE}/{endpoint}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers, params=params or [])
        resp.raise_for_status()
        return resp.json()


async def get_cost_report(
    admin_key: str,
    *,
    starting_at: str,
    ending_at: str,
    bucket_width: str = "1d",
) -> dict:
    """
    Get cost report from Anthropic Admin API.

    Note: ending_at must be strictly after starting_at by at least one bucket,
    and cannot be in the future. Only bucket_width=1d is supported.
    Cost report does not support model-level grouping.
    """
    params = [
        ("starting_at", starting_at),
        ("ending_at", ending_at),
        ("bucket_width", bucket_width),
    ]
    return await _request(admin_key, "cost_report", params)


async def get_usage_report(
    admin_key: str,
    *,
    starting_at: str,
    ending_at: str,
    group_by: list[str] | None = None,
    bucket_width: str = "1d",
) -> dict:
    """
    Get token usage report from Anthropic Admin API.

    Supports group_by: model, api_key, workspace_id, etc.
    ending_at can be up to tomorrow for same-day queries.
    """
    params = [
        ("starting_at", starting_at),
        ("ending_at", ending_at),
        ("bucket_width", bucket_width),
    ]
    for g in (group_by or ["model"]):
        params.append(("group_by[]", g))

    return await _request(admin_key, "usage_report/messages", params)


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT00:00:00Z")


async def get_spending_summary(admin_key: str, days: int = 1) -> dict:
    """
    Get a spending summary combining cost report (historical) and usage report (per-model).

    The cost_report endpoint only provides historical data (can't include today).
    For today's spend, we use usage_report tokens + our pricing table to estimate.

    Args:
        admin_key: Anthropic Admin API key
        days: Number of days to look back (1 = today only, 7 = past week)
    """
    from overseer.core.cycle_runner import MODEL_COST_PER_1K

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period_start = (today_start - timedelta(days=max(days - 1, 0)))
    tomorrow_start = today_start + timedelta(days=1)

    # Cost report: historical days only (ending_at = today, so we get up through yesterday)
    # Only available if we're looking back more than just today
    historical_cost_usd = 0.0
    if days > 1:
        try:
            cost_data = await get_cost_report(
                admin_key,
                starting_at=_date_str(period_start),
                ending_at=_date_str(today_start),
                bucket_width="1d",
            )
            for bucket in cost_data.get("data", []):
                for result in bucket.get("results", []):
                    # API returns amount in cents despite currency=USD
                    historical_cost_usd += float(result.get("amount", 0)) / 100
        except httpx.HTTPStatusError as e:
            log.error("admin_api_cost_error", status=e.response.status_code, body=e.response.text[:200])
        except Exception as e:
            log.error("admin_api_cost_error", error=str(e))

    # Usage report: full period including today (ending_at = tomorrow works for usage)
    by_model: dict[str, float] = {}
    total_tokens: dict[str, dict] = {}
    try:
        usage_data = await get_usage_report(
            admin_key,
            starting_at=_date_str(period_start),
            ending_at=_date_str(tomorrow_start),
            group_by=["model"],
            bucket_width="1d",
        )
        for bucket in usage_data.get("data", []):
            for result in bucket.get("results", []):
                model = result.get("model", "unknown")
                if model not in total_tokens:
                    total_tokens[model] = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_read_tokens": 0,
                        "cache_creation_tokens": 0,
                    }
                total_tokens[model]["input_tokens"] += result.get("uncached_input_tokens", 0)
                total_tokens[model]["output_tokens"] += result.get("output_tokens", 0)
                total_tokens[model]["cache_read_tokens"] += result.get("cache_read_input_tokens", 0)
                cache_creation = result.get("cache_creation", {})
                total_tokens[model]["cache_creation_tokens"] += (
                    cache_creation.get("ephemeral_1h_input_tokens", 0)
                    + cache_creation.get("ephemeral_5m_input_tokens", 0)
                )

        for model, tokens in total_tokens.items():
            costs = MODEL_COST_PER_1K.get(
                model,
                {"input": 0.003, "output": 0.015, "cache_read": 0.0003, "cache_create": 0.00375},
            )
            by_model[model] = round(
                (tokens["input_tokens"] / 1000) * costs["input"]
                + (tokens["output_tokens"] / 1000) * costs["output"]
                + (tokens["cache_read_tokens"] / 1000) * costs["cache_read"]
                + (tokens["cache_creation_tokens"] / 1000) * costs["cache_create"],
                4,
            )
    except httpx.HTTPStatusError as e:
        log.error("admin_api_usage_error", status=e.response.status_code, body=e.response.text[:200])
        return {"error": f"Usage API returned {e.response.status_code}"}
    except Exception as e:
        log.error("admin_api_usage_error", error=str(e))
        return {"error": str(e)}

    estimated_total_usd = sum(by_model.values())

    return {
        "period_days": days,
        "historical_cost_usd": round(historical_cost_usd, 4),
        "estimated_total_usd": round(estimated_total_usd, 4),
        "note": (
            "historical_cost_usd is from Anthropic billing (excludes today). "
            "estimated_total_usd is calculated from token usage * published pricing (includes today)."
        ),
        "by_model": {
            model: {"estimated_cost_usd": cost_usd}
            for model, cost_usd in sorted(by_model.items(), key=lambda x: -x[1])
        },
        "token_usage": total_tokens,
    }
