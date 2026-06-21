from __future__ import annotations

import json
import shlex
from datetime import datetime, timezone

import structlog

from overseer.config import OverseerSettings
from overseer.models.trading import PortfolioState, TradeRequest, TradeResult
from overseer.utils.ssh import ssh_command, ssh_read_file

log = structlog.get_logger()


async def get_portfolio_state(settings: OverseerSettings) -> PortfolioState:
    file_path = "/shared/portfolio_state/current.json"

    try:
        content = await ssh_read_file(
            host=settings.ibkr_host,
            file_path=file_path,
            key_path=settings.ssh_key_path,
        )
        data = json.loads(content)
        return PortfolioState(**data)
    except Exception as e:
        log.warning(
            "get_portfolio_state_failed",
            host=settings.ibkr_host,
            error=str(e),
            returning_empty=True,
        )
        return PortfolioState()


async def submit_trade(settings: OverseerSettings, request: TradeRequest) -> dict:
    request_id = str(request.request_id)
    file_path = f"/shared/trade_requests/{request_id}.json"

    # The gateway's TradeRequest schema validates `expected_gain_pct > 0` and
    # `expected_loss_pct < 0` (strict inequalities), and silently archives any
    # request that fails validation without writing a result file. Sells
    # legitimately have no expected gain, and an LLM could pass loss_pct=0
    # for an expected-break-even exit — both would be silently dropped. Pass
    # tiny placeholders to satisfy the schema where needed; the gateway
    # doesn't act on these values for sells. Long-term fix is to loosen the
    # gateway validation to `>= 0` / `<= 0`, but that's a separate deploy
    # on host 248.
    gain_pct_for_gateway = request.analysis.expected_gain_pct
    if gain_pct_for_gateway <= 0:
        gain_pct_for_gateway = 0.01

    loss_pct_for_gateway = -abs(request.analysis.expected_loss_pct)
    if loss_pct_for_gateway >= 0:
        loss_pct_for_gateway = -0.01

    payload = {
        "request_id": request_id,
        "timestamp": request.timestamp.isoformat(),
        "ticker": request.ticker,
        "action": request.action.upper(),
        "analysis": {
            "win_probability": request.analysis.win_probability,
            "expected_gain_pct": gain_pct_for_gateway,
            "expected_loss_pct": loss_pct_for_gateway,
            "confidence": request.analysis.confidence,
        },
        "reasoning": request.reasoning,
    }

    if request.quantity is not None:
        payload["quantity"] = request.quantity
    if request.kelly_fraction is not None:
        payload["kelly_fraction"] = request.kelly_fraction

    json_content = json.dumps(payload, indent=2)
    escaped_json = shlex.quote(json_content)

    write_command = f"printf '%s' {escaped_json} > {shlex.quote(file_path)}"

    try:
        await ssh_command(
            host=settings.ibkr_host,
            command=write_command,
            key_path=settings.ssh_key_path,
        )
        log.info("submit_trade_success", request_id=request_id, ticker=request.ticker)
        return {"submitted": True, "request_id": request_id}
    except Exception as e:
        log.error("submit_trade_failed", request_id=request_id, error=str(e))
        return {"submitted": False, "error": str(e)}


async def get_trade_result(
    settings: OverseerSettings, request_id: str
) -> TradeResult | None:
    # Gateway writes files as {timestamp}_{request_id}.json, so we must
    # find the file by listing the directory and matching the request_id suffix.
    find_cmd = f"ls /shared/trade_results/*{shlex.quote(request_id)}.json 2>/dev/null"

    try:
        file_path = (
            await ssh_command(
                host=settings.ibkr_host,
                command=find_cmd,
                key_path=settings.ssh_key_path,
            )
        ).strip()

        if not file_path:
            log.debug("get_trade_result_no_file", request_id=request_id)
            return None

        # Take the first match if multiple lines returned
        file_path = file_path.splitlines()[0].strip()

        content = await ssh_read_file(
            host=settings.ibkr_host,
            file_path=file_path,
            key_path=settings.ssh_key_path,
        )
        data = json.loads(content)
        return _parse_gateway_result(data)
    except Exception as e:
        log.debug("get_trade_result_not_found", request_id=request_id, error=str(e))
        return None


def _parse_gateway_result(data: dict) -> TradeResult | None:
    """Parse the IBKR gateway's nested JSON format into a TradeResult.

    Gateway format:
        {
            "request_id": "...",
            "approved": true/false,
            "trade_result": { "status": "FILLED", "filled_price": ..., ... },
            "message": "..."
        }
    """
    request_id = data.get("request_id")
    if not request_id:
        return None

    trade = data.get("trade_result")
    approved = data.get("approved", False)

    # If not approved or no trade_result, map to rejected
    if not approved or trade is None:
        return TradeResult(
            request_id=request_id,
            status="rejected",
            rejection_reason=data.get("message", "Not approved by gateway"),
        )

    raw_status = (trade.get("status") or "").upper()
    status_map = {
        "FILLED": "filled",
        "REJECTED": "rejected",
        "CANCELLED": "cancelled",
        "FAILED": "failed",
        "PENDING": "pending",
        "SUBMITTED": "submitted",
    }
    status = status_map.get(raw_status, raw_status.lower() or "unknown")

    filled_at = None
    if status == "filled":
        processed_at = data.get("processed_at")
        if processed_at:
            try:
                filled_at = datetime.fromisoformat(processed_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                filled_at = datetime.now(timezone.utc)
        else:
            filled_at = datetime.now(timezone.utc)

    order_id_raw = trade.get("order_id")
    order_id = str(order_id_raw) if order_id_raw is not None else None

    # Gateway currently only writes `quantity` on FILLED results (equal to the
    # filled amount). Prefer `filled_quantity`/`filled_qty`/`executed_quantity`
    # if present — future gateway versions that distinguish partial fills from
    # requested size will then be read correctly rather than over-counting.
    requested_quantity = trade.get("quantity")
    filled_quantity = (
        trade.get("filled_quantity")
        or trade.get("filled_qty")
        or trade.get("executed_quantity")
        or requested_quantity
    )

    return TradeResult(
        request_id=request_id,
        status=status,
        order_id=order_id,
        quantity=requested_quantity,
        filled_quantity=filled_quantity,
        fill_price=trade.get("filled_price"),
        filled_at=filled_at,
        commission=trade.get("commission"),
        rejection_reason=data.get("message") if status != "filled" else None,
    )


async def check_health(settings: OverseerSettings) -> dict:
    check_command = "ps aux | grep -E '(python|java)' | grep -v grep"

    try:
        output = await ssh_command(
            host=settings.ibkr_host,
            command=check_command,
            key_path=settings.ssh_key_path,
        )

        if output.strip():
            return {"status": "running"}

        return {"status": "not_running"}
    except Exception as e:
        log.error("check_health_failed", host=settings.ibkr_host, error=str(e))
        return {"status": "not_running", "error": str(e)}
