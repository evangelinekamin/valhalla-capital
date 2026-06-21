from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import structlog

from overseer.config import OverseerSettings
from overseer.memory import working
from overseer.models.tools import ProposeTradeInput
from overseer.models.trading import KellySizing, RiskCheck, TradeAnalysis, TradeRequest
from overseer.tools.discord_tools import send_discord_message
from overseer.tools.portfolio import get_portfolio_state
from overseer.utils.database import execute, fetchval
from overseer.utils.market_hours import is_market_hours

log = structlog.get_logger()


MIN_POSITION_VALUE = 25.0  # Minimum position value in USD

# Cap structure (user picked 20/25 from the Phase 2 review):
#   FRESH_BUY_CAP — fresh adds may not push post-trade weight above this.
#                   Kelly's target weight is also capped here, so it never
#                   proposes a target the caller will immediately want to trim.
#   DRIFT_CAP    — existing weight above this from price movement blocks
#                   any fresh add. Trim is the only path back below.
FRESH_BUY_CAP = 0.20
DRIFT_CAP = 0.25


def calculate_kelly_size(
    win_prob: float,
    gain_pct: float,
    loss_pct: float,
    portfolio_value: float,
    price: float,
    existing_value: float = 0.0,
    fresh_buy_cap: float = FRESH_BUY_CAP,
    drift_cap: float = DRIFT_CAP,
) -> KellySizing:
    # Kelly is a buy-side sizing formula and requires a positive expected gain.
    # Sells are routed around Kelly entirely in propose_trade, but guard here
    # so any direct caller gets a clean rejection rather than a ZeroDivisionError.
    if gain_pct <= 0:
        return KellySizing(
            shares=0,
            position_value=0.0,
            kelly_fraction=0.0,
            half_kelly_fraction=0.0,
            commission_round_trip=0.0,
            commission_drag_pct=0.0,
            rejection_reason="expected_gain_pct must be > 0 for Kelly sizing",
        )

    full_kelly = (win_prob * gain_pct - (1 - win_prob) * abs(loss_pct)) / gain_pct
    half_kelly = full_kelly / 2

    existing_weight = (existing_value / portfolio_value) if portfolio_value > 0 else 0.0

    # Negative Kelly means the bet has negative expected value. The prior
    # code silently coerced this to 1 share via max(1, floor(negative)),
    # letting losing propositions through with a positive position_value.
    if half_kelly <= 0:
        return KellySizing(
            shares=0,
            position_value=0.0,
            existing_weight=existing_weight,
            existing_value=existing_value,
            kelly_fraction=full_kelly,
            half_kelly_fraction=half_kelly,
            commission_round_trip=0.0,
            commission_drag_pct=0.0,
            rejection_reason=(
                f"Negative expected value (half-Kelly={half_kelly:.3f}). "
                f"With win_prob={win_prob:.2f}, gain={gain_pct:.1f}%, "
                f"loss={loss_pct:.1f}%, this trade loses money on average."
            ),
        )

    # Target weight = the portfolio fraction Kelly wants this position to occupy.
    # Cap at fresh_buy_cap so we never aim past the trim line; drift past
    # fresh_buy_cap can still happen from price moves and is allowed up to drift_cap.
    target_weight = min(half_kelly, fresh_buy_cap)
    target_value = target_weight * portfolio_value

    # Drift cap: existing concentration too high — any fresh add is rejected,
    # trim is the only path back. Caller must explicitly trim, not "add to trim."
    if existing_weight >= drift_cap:
        return KellySizing(
            shares=0,
            position_value=0.0,
            target_weight=target_weight,
            target_value=target_value,
            existing_weight=existing_weight,
            existing_value=existing_value,
            kelly_fraction=full_kelly,
            half_kelly_fraction=half_kelly,
            commission_round_trip=0.0,
            commission_drag_pct=0.0,
            rejection_reason=(
                f"Position weight {existing_weight:.1%} ≥ drift cap {drift_cap:.0%}. "
                f"No fresh adds — trim instead."
            ),
        )

    # Already at or above Kelly's target weight: nothing to add. Don't pretend
    # there's still a 1-share buy here — the prior implementation's "max(1, …)"
    # floor manufactured a forced 1-share trade in this exact situation.
    if existing_weight >= target_weight:
        return KellySizing(
            shares=0,
            position_value=0.0,
            target_weight=target_weight,
            target_value=target_value,
            existing_weight=existing_weight,
            existing_value=existing_value,
            kelly_fraction=full_kelly,
            half_kelly_fraction=half_kelly,
            commission_round_trip=0.0,
            commission_drag_pct=0.0,
            rejection_reason=(
                f"Existing weight {existing_weight:.1%} already ≥ target {target_weight:.1%}. "
                f"Position at/above Kelly size — no add."
            ),
        )

    delta_value_target = target_value - existing_value
    shares = max(1, math.floor(delta_value_target / price))  # Whole shares
    delta_value = shares * price  # Actual whole-share delta

    commission_per_share = 0.005
    min_commission = 1.0
    commission_round_trip = max(shares * commission_per_share, min_commission) * 2

    # gain_pct is percent-units (e.g. 12.0 for 12%). Convert to a decimal
    # fraction before multiplying by notional — the prior formula omitted
    # this, inflating expected_profit 100x and silently disabling the
    # commission-drag guard below.
    expected_profit = shares * price * (gain_pct / 100.0) * win_prob
    commission_drag = 0.0
    rejection_reason = None

    if expected_profit > 0:
        commission_drag = commission_round_trip / expected_profit
        if commission_drag > 0.05:
            rejection_reason = f"Commission drag {commission_drag:.1%} exceeds 5% threshold"

    if delta_value < MIN_POSITION_VALUE:
        rejection_reason = f"Position value ${delta_value:.2f} below ${MIN_POSITION_VALUE:.0f} minimum"

    return KellySizing(
        shares=shares,
        position_value=delta_value,
        target_weight=target_weight,
        target_value=target_value,
        existing_weight=existing_weight,
        existing_value=existing_value,
        delta_value=delta_value,
        kelly_fraction=full_kelly,
        half_kelly_fraction=half_kelly,
        commission_round_trip=commission_round_trip,
        commission_drag_pct=commission_drag,
        rejection_reason=rejection_reason,
    )


async def check_risk_limits(
    pool: asyncpg.Pool,
    settings: OverseerSettings,
    ticker: str,
    action: str,
    position_value: float,
    portfolio_value: float,
    existing_position_value: float = 0.0,
) -> RiskCheck:
    checks: dict[str, bool] = {}
    rejection_reasons: list[str] = []

    # trade_counters table is seeded by bootstrap_schema, so None here means a
    # genuine bug (truncated table). The historic `or 0` masked that and
    # silently let through unlimited trades on a fresh deploy.
    try:
        daily_trade_count = await fetchval(
            pool, "SELECT count FROM trade_counters WHERE name = 'daily'"
        )
        if daily_trade_count is None:
            raise RuntimeError("trade_counters['daily'] missing — schema bootstrap did not run")
        checks["daily_trade_limit"] = daily_trade_count < 10
        if not checks["daily_trade_limit"]:
            rejection_reasons.append(f"Daily trade limit reached ({daily_trade_count}/10)")
    except Exception as e:
        log.error("failed_to_check_daily_trade_count", error=str(e))
        checks["daily_trade_limit"] = False
        rejection_reasons.append("Failed to check daily trade count")

    try:
        weekly_trade_count = await fetchval(
            pool, "SELECT count FROM trade_counters WHERE name = 'weekly'"
        )
        if weekly_trade_count is None:
            raise RuntimeError("trade_counters['weekly'] missing — schema bootstrap did not run")
        checks["weekly_trade_limit"] = weekly_trade_count < 30
        if not checks["weekly_trade_limit"]:
            rejection_reasons.append(f"Weekly trade limit reached ({weekly_trade_count}/30)")
    except Exception as e:
        log.error("failed_to_check_weekly_trade_count", error=str(e))
        checks["weekly_trade_limit"] = False
        rejection_reasons.append("Failed to check weekly trade count")

    # Concentration: fresh buys can't push post-trade weight above FRESH_BUY_CAP
    # (20%). Drift above 20% from price moves is allowed up to DRIFT_CAP (25%);
    # past that, no new adds. Sells reduce concentration, so they skip this check.
    if action == "buy":
        total_after = existing_position_value + position_value
        existing_pct = (existing_position_value / portfolio_value) if portfolio_value > 0 else 0.0
        post_pct = (total_after / portfolio_value) if portfolio_value > 0 else 0.0
        if existing_pct >= DRIFT_CAP:
            checks["position_size_limit"] = False
            rejection_reasons.append(
                f"Existing weight {existing_pct:.1%} ≥ drift cap {DRIFT_CAP:.0%}. "
                f"Trim required before new adds."
            )
        elif post_pct > FRESH_BUY_CAP:
            checks["position_size_limit"] = False
            rejection_reasons.append(
                f"Post-trade weight {post_pct:.1%} exceeds fresh-buy cap {FRESH_BUY_CAP:.0%} "
                f"(existing {existing_pct:.1%} + new {(position_value / portfolio_value):.1%})"
            )
        else:
            checks["position_size_limit"] = True
    else:
        checks["position_size_limit"] = True

    try:
        daily_pnl = await working.get(pool, "daily_pnl") or 0.0
        daily_pnl_pct = (daily_pnl / portfolio_value) if portfolio_value > 0 else 0.0
        checks["circuit_breaker"] = daily_pnl_pct > -0.03
        if not checks["circuit_breaker"]:
            rejection_reasons.append(f"Circuit breaker active: daily PnL {daily_pnl_pct:.1%}")
    except Exception as e:
        log.error("failed_to_check_daily_pnl", error=str(e))
        checks["circuit_breaker"] = False
        rejection_reasons.append("Failed to check daily PnL")

    if action in ["buy", "sell"]:
        checks["market_hours"] = is_market_hours()
        if not checks["market_hours"]:
            rejection_reasons.append("Market is closed")
    else:
        checks["market_hours"] = True

    checks["trading_mode"] = settings.trading_mode in ["paper", "live"]
    if not checks["trading_mode"]:
        rejection_reasons.append(f"Invalid trading mode: {settings.trading_mode}")

    passed = all(checks.values())

    return RiskCheck(
        passed=passed,
        checks=checks,
        rejection_reasons=rejection_reasons,
    )


def _thesis_conflicts_with_action(position_type: str, action: str) -> bool:
    """Return True when the proposed action goes against the thesis direction.

    LONG thesis + sell  → conflict (closing/trimming a buy thesis).
    SHORT thesis + buy → conflict (covering a short).
    Same-direction trades (LONG+buy, SHORT+sell) align and don't trip the gate.
    """
    pt = (position_type or "LONG").upper()
    a = action.lower()
    if pt == "LONG" and a == "sell":
        return True
    if pt == "SHORT" and a == "buy":
        return True
    return False


async def _apply_thesis_action(
    pool: asyncpg.Pool,
    thesis_id: int,
    thesis_action: str,
    thesis_reasoning: str,
    ticker: str,
) -> None:
    """Record thesis transition. 'close', 'invalidate', 'reverse' end the thesis;
    'trim' appends to update_log but keeps it active."""
    now = datetime.now(timezone.utc)
    log_entry = {
        "at": now.isoformat(),
        "action": thesis_action,
        "reasoning": thesis_reasoning,
    }
    if thesis_action in ("close", "invalidate", "reverse"):
        status_map = {"close": "closed", "invalidate": "invalidated", "reverse": "reversed"}
        await execute(
            pool,
            """UPDATE thesis_tracker
               SET status = $2,
                   closed_at = $3,
                   close_reason = $4,
                   update_log = COALESCE(update_log, '[]'::jsonb) || $5::jsonb,
                   updated_at = $3
               WHERE id = $1""",
            thesis_id,
            status_map[thesis_action],
            now,
            f"{thesis_action}: {thesis_reasoning}",
            log_entry,
        )
    else:  # trim
        await execute(
            pool,
            """UPDATE thesis_tracker
               SET update_log = COALESCE(update_log, '[]'::jsonb) || $2::jsonb,
                   updated_at = $3
               WHERE id = $1""",
            thesis_id,
            log_entry,
            now,
        )
    log.info(
        "thesis_action_applied",
        thesis_id=thesis_id,
        ticker=ticker,
        action=thesis_action,
    )


async def propose_trade(
    pool: asyncpg.Pool,
    settings: OverseerSettings,
    input: ProposeTradeInput,
) -> dict:
    try:
        state = await get_portfolio_state(pool, settings)
        portfolio_value = state.total_value
        if portfolio_value <= 0:
            log.error("invalid_portfolio_value", value=portfolio_value)
            return {
                "status": "rejected",
                "error": "Portfolio value not available or invalid",
            }

        # Thesis-action gate: if there's an active thesis on this ticker and
        # the proposed action conflicts with its direction, force the agent to
        # explicitly label the thesis transition. We validate the inputs HERE
        # but defer the actual thesis_tracker write until after IBKR confirms
        # the fill — otherwise a rejected/stale trade still flips the thesis
        # state, leaving us with phantom closed theses on positions still held.
        _RESOLUTION_ACTIONS = {"close", "invalidate", "reverse", "trim"}
        thesis_row = await fetchval(
            pool,
            """SELECT to_jsonb(t.*) FROM thesis_tracker t
               WHERE upper(ticker) = upper($1) AND status = 'active'
               ORDER BY created_at DESC LIMIT 1""",
            input.ticker,
        )
        thesis_conflict = bool(
            thesis_row
            and _thesis_conflicts_with_action(
                thesis_row.get("position_type"), input.action
            )
        )
        if thesis_conflict:
            if input.thesis_action not in _RESOLUTION_ACTIONS:
                log.info(
                    "trade_rejected_thesis_action_required",
                    ticker=input.ticker,
                    action=input.action,
                    thesis_action=input.thesis_action,
                    thesis_id=thesis_row.get("id"),
                )
                got = (
                    f"got '{input.thesis_action}' which is not a conflict resolution"
                    if input.thesis_action
                    else "thesis_action is null"
                )
                return {
                    "status": "rejected",
                    "reason": (
                        f"Active {thesis_row.get('position_type')} thesis on "
                        f"{input.ticker} (id={thesis_row.get('id')}, target="
                        f"${thesis_row.get('target_price')}). Proposing "
                        f"{input.action.upper()} requires thesis_action ∈ "
                        f"{{close, invalidate, reverse, trim}} plus thesis_reasoning. "
                        f"{got}."
                    ),
                    "active_thesis": {
                        "id": thesis_row.get("id"),
                        "position_type": thesis_row.get("position_type"),
                        "thesis_statement": thesis_row.get("thesis_statement"),
                        "target_price": thesis_row.get("target_price"),
                        "stop_loss": thesis_row.get("stop_loss"),
                        "conviction": thesis_row.get("conviction"),
                    },
                }
            if not input.thesis_reasoning or len(input.thesis_reasoning) < 30:
                return {
                    "status": "rejected",
                    "reason": (
                        f"thesis_action='{input.thesis_action}' was provided but "
                        f"thesis_reasoning is missing or under 30 chars. Explain "
                        f"why the {thesis_row.get('position_type')} thesis on "
                        f"{input.ticker} is being {input.thesis_action}d."
                    ),
                }
            # Defer _apply_thesis_action — it runs after fill confirms below.

        from overseer.tools import fmp_client
        quote_data = await fmp_client.get_quote(settings, input.ticker)
        if "error" in quote_data or not quote_data:
            log.error("failed_to_get_quote", ticker=input.ticker, error=quote_data.get("error"))
            return {
                "status": "rejected",
                "error": f"Failed to get quote for {input.ticker}",
            }

        price = quote_data[0].get("price") if isinstance(quote_data, list) else quote_data.get("price")
        if not price:
            log.error("no_price_in_quote", ticker=input.ticker, data=quote_data)
            return {
                "status": "rejected",
                "error": f"No price available for {input.ticker}",
            }

        ticker_upper = input.ticker.upper()
        existing = next(
            (p for p in state.positions if p.ticker.upper() == ticker_upper),
            None,
        )
        existing_quantity = existing.quantity if existing else 0.0
        existing_value = (
            (existing.market_value or (existing.quantity * price))
            if existing
            else 0.0
        )

        # Earnings proximity check (non-fatal)
        earnings_warning = None
        earnings_days_until = None
        try:
            earnings_data = await fmp_client.get_earnings_calendar(settings, input.ticker)
            next_e = earnings_data.get("next_earnings")
            if next_e and next_e.get("days_until") is not None:
                earnings_days_until = next_e["days_until"]
                if earnings_days_until <= 14:
                    earnings_warning = (
                        f"EARNINGS IN {earnings_days_until} DAYS ({next_e['date']}). "
                        f"High risk of gap move."
                    )
                    log.warning(
                        "trade_near_earnings",
                        ticker=input.ticker,
                        days_until=earnings_days_until,
                        date=next_e["date"],
                    )
        except Exception as e:
            log.warning("earnings_check_failed", ticker=input.ticker, error=str(e))

        # Sells are sized from current holdings, not Kelly. Kelly assumes a new
        # long position with positive expected gain — neither applies to exits.
        if input.action == "sell":
            if existing is None or existing_quantity <= 0:
                return {
                    "status": "rejected",
                    "reason": f"Cannot sell {input.ticker} — no position held",
                    "earnings_warning": earnings_warning,
                    "earnings_days_until": earnings_days_until,
                }

            if input.quantity_override is not None and input.quantity_override > 0:
                final_shares = int(input.quantity_override)
            else:
                final_shares = int(existing_quantity)

            if final_shares > existing_quantity:
                return {
                    "status": "rejected",
                    "reason": (
                        f"Cannot sell {final_shares} shares — only "
                        f"{existing_quantity:g} held"
                    ),
                    "earnings_warning": earnings_warning,
                    "earnings_days_until": earnings_days_until,
                }

            final_position_value = final_shares * price
            if final_position_value < MIN_POSITION_VALUE and final_shares < existing_quantity:
                # Allow full exits below the minimum (stub cleanup). Reject
                # partial trims that would leave a dust-sized order.
                return {
                    "status": "rejected",
                    "reason": (
                        f"Partial sell value ${final_position_value:.2f} below "
                        f"${MIN_POSITION_VALUE:.0f} minimum — either exit fully or trim more"
                    ),
                    "earnings_warning": earnings_warning,
                    "earnings_days_until": earnings_days_until,
                }

            sizing = None
        else:
            sizing = calculate_kelly_size(
                win_prob=input.win_probability,
                gain_pct=input.expected_gain_pct,
                loss_pct=input.expected_loss_pct,
                portfolio_value=portfolio_value,
                price=price,
                existing_value=existing_value,
            )

            if input.quantity_override is not None and input.quantity_override > 0:
                # Kelly shares==0 with a rejection_reason is a HARD rejection
                # (negative EV, invalid inputs). The override cannot bypass
                # these — it only lets the caller pick a smaller size than Kelly
                # proposes when the trade is fundamentally valid.
                if sizing.shares == 0 and sizing.rejection_reason:
                    log.info(
                        "trade_rejected_by_sizing",
                        ticker=input.ticker,
                        reason=sizing.rejection_reason,
                    )
                    return {
                        "status": "rejected",
                        "sizing": sizing,
                        "reason": sizing.rejection_reason,
                        "earnings_warning": earnings_warning,
                        "earnings_days_until": earnings_days_until,
                    }

                final_shares = min(input.quantity_override, sizing.shares)
                override_position_value = final_shares * price
                if override_position_value < MIN_POSITION_VALUE:
                    return {
                        "status": "rejected",
                        "reason": f"Position value ${override_position_value:.2f} below ${MIN_POSITION_VALUE:.0f} minimum",
                        "earnings_warning": earnings_warning,
                        "earnings_days_until": earnings_days_until,
                    }
                log.info(
                    "quantity_override_applied",
                    ticker=input.ticker,
                    kelly_shares=sizing.shares,
                    override_shares=input.quantity_override,
                    final_shares=final_shares,
                )
            else:
                if sizing.rejection_reason:
                    log.info(
                        "trade_rejected_by_sizing",
                        ticker=input.ticker,
                        reason=sizing.rejection_reason,
                    )
                    return {
                        "status": "rejected",
                        "sizing": sizing,
                        "reason": sizing.rejection_reason,
                        "earnings_warning": earnings_warning,
                        "earnings_days_until": earnings_days_until,
                    }
                final_shares = sizing.shares

            final_position_value = final_shares * price

        if input.action == "buy" and state.cash < final_position_value:
            log.info(
                "trade_rejected_insufficient_cash",
                ticker=input.ticker,
                need=final_position_value,
                have=state.cash,
            )
            return {
                "status": "rejected",
                "sizing": sizing,
                "reason": (
                    f"Insufficient cash: need ${final_position_value:.2f}, "
                    f"have ${state.cash:.2f} available "
                    f"(total portfolio ${portfolio_value:.2f} includes equity)"
                ),
                "earnings_warning": earnings_warning,
                "earnings_days_until": earnings_days_until,
            }

        risk_check = await check_risk_limits(
            pool=pool,
            settings=settings,
            ticker=input.ticker,
            action=input.action,
            position_value=final_position_value,
            portfolio_value=portfolio_value,
            existing_position_value=existing_value,
        )

        if not risk_check.passed:
            log.info(
                "trade_rejected_by_risk_check",
                ticker=input.ticker,
                reasons=risk_check.rejection_reasons,
            )
            return {
                "status": "rejected",
                "sizing": sizing,
                "risk_check": risk_check,
                "reasons": risk_check.rejection_reasons,
                "earnings_warning": earnings_warning,
                "earnings_days_until": earnings_days_until,
            }

        request_id = uuid4()
        decision_id_value = await fetchval(
            pool,
            """
            INSERT INTO decision_journal (
                created_at,
                decision_type,
                summary,
                reasoning,
                tickers,
                confidence,
                falsification_criteria
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            datetime.now(timezone.utc),
            "trade_proposal",
            f"{input.action.upper()} {final_shares} shares of {input.ticker} at ~${price:.2f}",
            input.reasoning,
            [input.ticker],
            input.confidence,
            input.falsification_criteria,
        )

        kelly_fraction_value = sizing.half_kelly_fraction if sizing else None

        trade_id = await fetchval(
            pool,
            """
            INSERT INTO trades (
                request_id,
                decision_id,
                created_at,
                ticker,
                action,
                quantity,
                price,
                status,
                kelly_fraction,
                reasoning
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id
            """,
            request_id,
            decision_id_value,
            datetime.now(timezone.utc),
            input.ticker,
            input.action.upper(),
            final_shares,
            price,
            "pending",
            kelly_fraction_value,
            input.reasoning,
        )

        log.info(
            "trade_proposed",
            trade_id=trade_id,
            ticker=input.ticker,
            action=input.action,
            shares=final_shares,
            position_value=final_position_value,
        )

        # Submit to IBKR gateway for execution
        from overseer.tools import ibkr_client

        trade_request = TradeRequest(
            request_id=request_id,
            ticker=input.ticker,
            action=input.action,
            analysis=TradeAnalysis(
                win_probability=input.win_probability,
                expected_gain_pct=input.expected_gain_pct,
                expected_loss_pct=input.expected_loss_pct,
                confidence=input.confidence,
            ),
            reasoning=input.reasoning,
            quantity=final_shares,
            kelly_fraction=kelly_fraction_value,
        )

        submission = await ibkr_client.submit_trade(settings, trade_request)

        if submission.get("submitted"):
            await execute(
                pool,
                "UPDATE trades SET status = 'submitted' WHERE id = $1",
                trade_id,
            )
            log.info("trade_submitted_to_ibkr", trade_id=trade_id, request_id=str(request_id))

            # Increment trade counters for risk limit tracking
            from overseer.tools.system_tools import increment_trade_count
            await increment_trade_count(pool)

            # Poll for trade result from IBKR gateway
            fill_info = await _poll_trade_result(
                pool, settings, str(request_id), trade_id
            )
        else:
            fill_info = None
            log.error(
                "trade_submission_failed",
                trade_id=trade_id,
                error=submission.get("error"),
            )

        # Be explicit about what actually happened. The LLM was narrating
        # "submitted" as "done" and posting Discord messages claiming trims
        # that silently failed gateway validation (2026-04-17 IPI/FOUR
        # incident). Split the outcome into distinct statuses and include a
        # plain-English outcome line the LLM can't mis-read.
        if not submission.get("submitted"):
            final_status = "submission_failed"
            llm_outcome = (
                "NOT EXECUTED. SSH write to the IBKR gateway failed — the "
                "trade never reached the gateway. Do NOT announce or record "
                "this as a completed action."
            )
        elif fill_info and fill_info.get("filled"):
            final_status = "filled"
            fp = fill_info.get("fill_price")
            qty = fill_info.get("quantity")
            llm_outcome = (
                f"FILLED. {input.action.upper()} {qty} shares of "
                f"{input.ticker} at ${fp} confirmed by the IBKR gateway."
            )

            # Apply deferred thesis action — only now that the trade actually
            # filled. Skips the historic bug where a rejected trade still
            # flipped thesis_tracker state.
            if thesis_conflict and input.thesis_action in _RESOLUTION_ACTIONS:
                try:
                    await _apply_thesis_action(
                        pool,
                        thesis_row["id"],
                        input.thesis_action,
                        input.thesis_reasoning or "",
                        input.ticker,
                    )
                except Exception as e:
                    log.error(
                        "thesis_apply_post_fill_failed",
                        ticker=input.ticker,
                        thesis_id=thesis_row.get("id"),
                        error=str(e),
                    )

            # Auto-close: if a SELL drove the position to zero, force-close
            # any thesis still active on the ticker — even if the agent
            # labelled the trade 'trim'. Catches mislabelled full exits
            # without creating phantom-active theses on names she no longer
            # holds.
            try:
                filled_qty = float(qty or 0)
                remaining = float(existing_quantity) - filled_qty
                if (
                    input.action == "sell"
                    and remaining <= 1e-9
                    and existing_quantity > 0
                ):
                    closed_id = await fetchval(
                        pool,
                        """UPDATE thesis_tracker
                           SET status = 'closed',
                               closed_at = NOW(),
                               close_reason = COALESCE(
                                   close_reason,
                                   'auto-closed: position fully exited via trade ' || $2::text
                               ),
                               update_log = COALESCE(update_log, '[]'::jsonb)
                                            || jsonb_build_object(
                                                   'at', NOW(),
                                                   'action', 'auto_close_full_exit',
                                                   'trade_id', $2::int,
                                                   'reasoning',
                                                   'Position fully sold; thesis auto-closed regardless of thesis_action label.'
                                               ),
                               updated_at = NOW()
                           WHERE upper(ticker) = upper($1) AND status = 'active'
                           RETURNING id""",
                        input.ticker,
                        trade_id,
                    )
                    if closed_id:
                        log.info(
                            "thesis_auto_closed_full_exit",
                            ticker=input.ticker,
                            thesis_id=closed_id,
                            trade_id=trade_id,
                        )
            except Exception as e:
                log.error(
                    "thesis_auto_close_failed",
                    ticker=input.ticker,
                    error=str(e),
                )
        elif fill_info and fill_info.get("status") in ("rejected", "cancelled", "failed", "error"):
            final_status = fill_info.get("status", "rejected")
            llm_outcome = (
                f"{final_status.upper()}. The IBKR gateway responded with "
                f"status={final_status}. Do NOT announce this as completed."
            )
        else:
            # Submitted to gateway but poll window elapsed without a result
            # file. Could be a validation failure that archived silently, a
            # slow IBKR response, or a lost result. Treat as unconfirmed.
            final_status = "submitted_unconfirmed"
            llm_outcome = (
                "UNCONFIRMED. The request was written to the gateway but no "
                "fill or rejection was observed within the 60s poll window. "
                "Do NOT narrate this trade as done. Call check_pending_trades "
                "in a later cycle to resolve the outcome; position state is "
                "unchanged until a fill is confirmed."
            )

        return {
            "status": final_status,
            "llm_outcome": llm_outcome,
            "trade_id": trade_id,
            "request_id": str(request_id),
            "sizing": sizing,
            "risk_check": risk_check,
            "ibkr_submitted": submission.get("submitted", False),
            "fill_info": fill_info,
            "earnings_warning": earnings_warning,
            "earnings_days_until": earnings_days_until,
        }

    except Exception as e:
        log.error("propose_trade_failed", ticker=input.ticker, error=str(e), exc_info=True)
        return {
            "status": "error",
            "error": str(e),
        }


POLL_INTERVAL_SECONDS = 5
POLL_MAX_ATTEMPTS = 12  # 60 seconds total


async def _poll_trade_result(
    pool: asyncpg.Pool,
    settings: OverseerSettings,
    request_id: str,
    trade_id: int,
) -> dict:
    """Poll IBKR gateway for trade result and update DB when filled."""
    from overseer.tools import ibkr_client

    for attempt in range(POLL_MAX_ATTEMPTS):
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

        result = await ibkr_client.get_trade_result(settings, request_id)
        if result is None:
            log.debug("trade_result_pending", request_id=request_id, attempt=attempt + 1)
            continue

        if result.status == "filled":
            await execute(
                pool,
                """UPDATE trades
                   SET status = 'filled',
                       fill_price = $1,
                       filled_at = $2,
                       commission = $3,
                       quantity = $4,
                       ibkr_order_id = $5
                   WHERE id = $6""",
                result.fill_price,
                result.filled_at or datetime.now(timezone.utc),
                result.commission,
                result.filled_quantity or result.quantity,
                result.order_id,
                trade_id,
            )
            log.info(
                "trade_filled",
                trade_id=trade_id,
                fill_price=result.fill_price,
                quantity=result.filled_quantity or result.quantity,
                commission=result.commission,
            )
            return {
                "filled": True,
                "fill_price": result.fill_price,
                "quantity": result.filled_quantity or result.quantity,
                "commission": result.commission,
            }

        if result.status in ("rejected", "cancelled", "error"):
            await execute(
                pool,
                "UPDATE trades SET status = $1 WHERE id = $2",
                result.status,
                trade_id,
            )
            log.warning(
                "trade_not_filled",
                trade_id=trade_id,
                status=result.status,
                error=getattr(result, "error", None),
            )
            return {"filled": False, "status": result.status}

    log.warning("trade_poll_timeout", trade_id=trade_id, request_id=request_id)
    return {"filled": False, "status": "poll_timeout"}


async def check_pending_trades(
    pool: asyncpg.Pool,
    settings: OverseerSettings,
) -> dict:
    """Check IBKR gateway for updates on all submitted/pending trades.

    Called by Valkyrie in any cycle to catch fills that happened after the
    initial 60-second polling window.
    """
    from overseer.tools import ibkr_client
    from overseer.utils.database import fetch

    pending_trades = await fetch(
        pool,
        """SELECT id, request_id, ticker, action, quantity, price, status, created_at
           FROM trades
           WHERE status IN ('submitted', 'pending')
           ORDER BY created_at ASC""",
    )

    if not pending_trades:
        return {"checked": 0, "updated": [], "message": "No pending trades"}

    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    updated = []
    for trade in pending_trades:
        request_id = str(trade["request_id"])
        trade_id = trade["id"]
        ticker = trade["ticker"]

        result = await ibkr_client.get_trade_result(settings, request_id)
        if result is None:
            # Mark as stale if submitted >2 hours ago with no result file
            if trade["created_at"] < stale_cutoff:
                await execute(
                    pool,
                    "UPDATE trades SET status = 'stale' WHERE id = $1",
                    trade_id,
                )
                log.warning(
                    "trade_marked_stale",
                    trade_id=trade_id,
                    ticker=ticker,
                    created_at=str(trade["created_at"]),
                )
                updated.append({
                    "trade_id": trade_id,
                    "ticker": ticker,
                    "new_status": "stale",
                    "reason": "No IBKR result after 2+ hours",
                })
                await send_discord_message(
                    settings,
                    f"Trade {trade_id} for {ticker} marked stale — no IBKR result after 2+ hours",
                    message_type="alert",
                )
            else:
                log.debug("pending_trade_no_result", trade_id=trade_id, ticker=ticker)
            continue

        if result.status == "filled":
            await execute(
                pool,
                """UPDATE trades
                   SET status = 'filled',
                       fill_price = $1,
                       filled_at = $2,
                       commission = $3,
                       quantity = COALESCE($4, quantity),
                       ibkr_order_id = $5
                   WHERE id = $6""",
                result.fill_price,
                result.filled_at or datetime.now(timezone.utc),
                result.commission,
                result.filled_quantity or result.quantity,
                result.order_id,
                trade_id,
            )
            log.info(
                "pending_trade_filled",
                trade_id=trade_id,
                ticker=ticker,
                fill_price=result.fill_price,
            )
            filled_quantity = result.filled_quantity or result.quantity
            updated.append({
                "trade_id": trade_id,
                "ticker": ticker,
                "new_status": "filled",
                "fill_price": result.fill_price,
                "quantity": filled_quantity,
                "commission": result.commission,
            })
            await send_discord_message(
                settings,
                f"Trade filled: {trade['action']} {filled_quantity} {ticker} @ ${result.fill_price:.2f}",
                message_type="trade",
            )

        elif result.status in ("rejected", "cancelled", "failed"):
            await execute(
                pool,
                "UPDATE trades SET status = $1 WHERE id = $2",
                result.status,
                trade_id,
            )
            log.info(
                "pending_trade_resolved",
                trade_id=trade_id,
                ticker=ticker,
                status=result.status,
                reason=result.rejection_reason,
            )
            updated.append({
                "trade_id": trade_id,
                "ticker": ticker,
                "new_status": result.status,
                "reason": result.rejection_reason,
            })
            await send_discord_message(
                settings,
                (
                    f"Trade {result.status}: {trade['action']} {trade['quantity']} {ticker} "
                    f"@ ${trade['price']:.2f} — {result.rejection_reason or result.status}"
                ),
                message_type="alert",
            )

    return {
        "checked": len(pending_trades),
        "updated": updated,
        "still_pending": len(pending_trades) - len(updated),
    }
