from __future__ import annotations

import json
import time
from typing import Any, Callable, Coroutine

import structlog

from overseer.config import OverseerSettings
from overseer.models.tools import (
    CapabilityWishInput,
    CheckSpendingInput,
    CloseThesisInput,
    CompareToThesisInput,
    CreateThesisInput,
    DiscordMessageInput,
    EarningsCalendarInput,
    FMPDataInput,
    GetThesesInput,
    LogObservationInput,
    MemorySearchInput,
    NewsQueryInput,
    OpenInsiderQueryInput,
    ProposeTradeInput,
    ResearchCompanyInput,
    SubstackQueryInput,
    TwitterQueryInput,
    UpdateThesisInput,
    YellowbrickQueryInput,
)
from overseer.utils import database as db

log = structlog.get_logger()

ToolHandler = Callable[..., Coroutine[Any, Any, Any]]


class ToolRegistry:
    def __init__(self, pool, settings: OverseerSettings):
        self._pool = pool
        self._settings = settings
        self._handlers: dict[str, ToolHandler] = {}
        self._definitions: list[dict] = []
        self._register_all()

    def _register_all(self) -> None:
        self._register(
            "get_benchmark_performance",
            "Compare portfolio performance against SPY benchmark since inception. "
            "Returns portfolio return vs SPY return and alpha (outperformance). "
            "Use during daily/weekly/monthly reviews to assess relative performance.",
            {"type": "object", "properties": {}, "required": []},
            self._handle_benchmark,
        )
        self._register(
            "query_twitter_feed",
            "Query recent tweets from the Twitter pipeline. Returns CRITICAL, IMPORTANT, and ROUTINE "
            "tweets (commentary/memes are pre-filtered). Use this to scan for market signals, "
            "actionable ideas, and notable events.",
            TwitterQueryInput.model_json_schema(),
            self._handle_twitter,
        )
        self._register(
            "query_news_feed",
            "Query critical news alerts from the news pipeline.",
            NewsQueryInput.model_json_schema(),
            self._handle_news,
        )
        self._register(
            "query_substack_feed",
            "Query recent investment newsletter recommendations from Substack.",
            SubstackQueryInput.model_json_schema(),
            self._handle_substack,
        )
        self._register(
            "query_yellowbrick_feed",
            "Query recent investment pitches from Yellowbrick (big money and elite feeds).",
            YellowbrickQueryInput.model_json_schema(),
            self._handle_yellowbrick,
        )
        self._register(
            "query_openinsider",
            "Query recent insider trading cluster buys from OpenInsider.",
            OpenInsiderQueryInput.model_json_schema(),
            self._handle_openinsider,
        )
        self._register(
            "get_fmp_data",
            "Get comprehensive financial data for a ticker from FMP (quote, fundamentals, profile).",
            FMPDataInput.model_json_schema(),
            self._handle_fmp,
        )
        self._register(
            "research_company",
            (
                "Pull ONE primary-source document (10-K, 10-Q, 8-K, DEF 14A proxy, "
                "or earnings call transcript) and have an isolated worker LLM "
                "produce a 500-word structured summary plus extracted findings "
                "(thesis_impact, FCF/margin/revenue deltas, guidance change, red "
                "flags). Raw documents NEVER enter your context; only the summary "
                "does. The summary is auto-saved to knowledge_base so future "
                "search_knowledge_base calls find it. Cached: same "
                "(ticker, source_type, period) is free on subsequent calls. "
                "Cost ~$0.001-$0.04 per call. "
                "USE THIS TOOL WHEN: (1) you're proposing to invalidate or reverse "
                "an active thesis — read the latest 10-Q or transcript first, (2) "
                "you're considering an add that would push a position above 10% of "
                "portfolio, (3) compare_to_thesis surfaced a contradiction you need "
                "to sanity-check against the actual filing, (4) an 8-K material "
                "event hits the news feed, (5) earnings just dropped and you want "
                "the call transcript instead of waiting for analyst takes. Don't "
                "use for routine quote/fundamentals — get_fmp_data is cheaper."
            ),
            ResearchCompanyInput.model_json_schema(),
            self._handle_research,
        )
        self._register(
            "search_memory",
            "Search episodic memory for past observations, analyses, and trade outcomes using semantic similarity.",
            MemorySearchInput.model_json_schema(),
            self._handle_search_memory,
        )
        self._register(
            "search_knowledge_base",
            "Search the investment literature knowledge base for relevant theory and principles.",
            MemorySearchInput.model_json_schema(),
            self._handle_search_kb,
        )
        self._register(
            "log_observation",
            "Log a new observation or insight to episodic memory for future reference.",
            LogObservationInput.model_json_schema(),
            self._handle_log_observation,
        )
        self._register(
            "get_active_principles",
            "Retrieve active learned investment principles, optionally filtered by category.",
            {"type": "object", "properties": {"category": {"type": "string"}}, "required": []},
            self._handle_get_principles,
        )
        self._register(
            "propose_trade",
            "Propose a trade with Kelly-criterion position sizing and risk checks. "
            "action must be exactly \"buy\" or \"sell\" (lowercase). "
            "IMPORTANT for SELLs: omitting quantity_override sells the ENTIRE "
            "position. To trim a position partially you MUST set quantity_override "
            "to the exact number of shares you want to sell. "
            "For buys, Kelly sizing caps the override (you can only ever buy fewer "
            "shares than Kelly proposes, never more). "
            "If an active thesis exists on the ticker and your action conflicts "
            "with it (LONG thesis + sell, or SHORT thesis + buy), set thesis_action "
            "to one of {close, invalidate, reverse, trim} and provide thesis_reasoning. "
            "Requires conviction: you must provide falsification criteria for every trade.",
            ProposeTradeInput.model_json_schema(),
            self._handle_propose_trade,
        )
        self._register(
            "get_portfolio_state",
            "Get current portfolio positions, cash, and P&L from IBKR.",
            {"type": "object", "properties": {}, "required": []},
            self._handle_portfolio,
        )
        self._register(
            "check_pending_trades",
            "Check IBKR gateway for status updates on all submitted/pending trades. "
            "Call this at the start of any cycle to catch fills that happened after "
            "initial submission. Returns list of trades whose status was updated.",
            {"type": "object", "properties": {}, "required": []},
            self._handle_check_pending_trades,
        )
        self._register(
            "check_circuit_breakers",
            "Check all trading circuit breakers (daily loss halt, trade limits, market hours).",
            {"type": "object", "properties": {}, "required": []},
            self._handle_circuit_breakers,
        )
        self._register(
            "compare_to_thesis",
            "Compare current data against the original thesis and falsification criteria for a decision. "
            "Price movement alone does NOT invalidate a thesis.",
            CompareToThesisInput.model_json_schema(),
            self._handle_compare_thesis,
        )
        self._register(
            "send_discord_message",
            "Send a message to the Discord channel. Types: info, alert, trade, report.",
            DiscordMessageInput.model_json_schema(),
            self._handle_discord,
        )
        self._register(
            "request_capability",
            "Request a new capability or data source. Will be reviewed during weekly improvement.",
            CapabilityWishInput.model_json_schema(),
            self._handle_capability_wish,
        )
        self._register(
            "write_reflection",
            "Write a structured reflection on a cycle's findings, updating working memory.",
            {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Working memory key to update"},
                    "value": {"description": "The value to store (any JSON type)"},
                },
                "required": ["key", "value"],
            },
            self._handle_write_reflection,
        )
        self._register(
            "check_earnings_calendar",
            "Check upcoming earnings dates for a ticker. Returns days until next earnings "
            "and a HIGH_RISK warning if within 14 calendar days. Always check before proposing trades.",
            EarningsCalendarInput.model_json_schema(),
            self._handle_earnings_calendar,
        )
        self._register(
            "check_spending",
            "Check actual API spending from Anthropic billing. Returns real cost data by model. "
            "Use days=1 for today, days=7 for past week, days=30 for past month.",
            CheckSpendingInput.model_json_schema(),
            self._handle_check_spending,
        )
        self._register(
            "get_active_theses",
            "Get all active position theses with pillars, catalysts, risks, and update history. "
            "Optionally filter by ticker. Use this to review conviction and track thesis evolution.",
            GetThesesInput.model_json_schema(),
            self._handle_get_theses,
        )
        self._register(
            "create_thesis",
            "Create a structured thesis for a new position. Include thesis statement, pillars "
            "(key assumptions), catalysts, risks, and valuation targets. One active thesis per ticker.",
            CreateThesisInput.model_json_schema(),
            self._handle_create_thesis,
        )
        self._register(
            "update_thesis",
            "Update an active thesis with new data. Log what changed, how it impacts the thesis, "
            "and whether conviction should change. Updates pillars and appends to the audit trail.",
            UpdateThesisInput.model_json_schema(),
            self._handle_update_thesis,
        )
        self._register(
            "close_thesis",
            "Close a thesis when exiting a position, when the thesis is invalidated by evidence, "
            "or when the thesis is confirmed and target reached. Also updates the linked decision journal.",
            CloseThesisInput.model_json_schema(),
            self._handle_close_thesis,
        )

    def _register(self, name: str, description: str, schema: dict, handler: ToolHandler) -> None:
        self._handlers[name] = handler
        clean_schema = {k: v for k, v in schema.items() if k != "title"}
        if "type" not in clean_schema:
            clean_schema["type"] = "object"
        self._definitions.append({
            "name": name,
            "description": description,
            "input_schema": clean_schema,
        })

    def get_tool_definitions(self) -> list[dict]:
        return self._definitions

    async def execute(self, tool_name: str, tool_input: dict, cycle_log_id: int | None = None) -> str:
        handler = self._handlers.get(tool_name)
        if not handler:
            return json.dumps({
                "tool_error": True,
                "error_type": "unknown_tool",
                "error": f"Unknown tool: {tool_name}",
                "message": (
                    "This tool is not registered. DO NOT describe any action as "
                    "completed. Either correct the tool name or request a capability."
                ),
            })

        start = time.monotonic()
        error_msg = None
        try:
            result = await handler(tool_input)
            output = json.dumps(result, default=str)
        except Exception as e:
            # IMPORTANT: we wrap unhandled exceptions in a distinctive shape so the
            # LLM can tell a raised exception from a legitimate `{"error": ...}`
            # response. Without this marker, the LLM sometimes narrates actions
            # (e.g. "TRADE EXECUTED") as if they succeeded when the tool actually
            # crashed — see 2026-04-15 FOUR-exit incident.
            log.error(
                "tool_execution_error",
                tool=tool_name,
                error_type=type(e).__name__,
                error=str(e),
                exc_info=True,
            )
            error_msg = str(e)
            output = json.dumps({
                "tool_error": True,
                "error_type": type(e).__name__,
                "error": error_msg,
                "tool": tool_name,
                "message": (
                    "This tool raised an unhandled exception — it did NOT complete. "
                    "DO NOT describe the intended action as done, executed, filled, "
                    "or completed. Investigate the error and retry if appropriate."
                ),
            })

        duration_ms = int((time.monotonic() - start) * 1000)

        try:
            output_for_log = json.loads(output)
            if len(output) > 10000:
                output_for_log = {"truncated": True, "preview": output[:2000]}
            await db.execute(
                self._pool,
                """INSERT INTO tool_call_log (cycle_log_id, tool_name, input, output, duration_ms, error)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                cycle_log_id,
                tool_name,
                tool_input,
                output_for_log,
                duration_ms,
                error_msg,
            )
        except Exception as e:
            log.warning("tool_log_insert_failed", tool=tool_name, error=str(e))

        return output

    async def _handle_twitter(self, input: dict) -> dict:
        from overseer.tools.data_feeds import query_twitter_feed
        return await query_twitter_feed(
            self._settings,
            limit=input.get("limit", 50),
            since=input.get("since"),
        )

    async def _handle_news(self, input: dict) -> dict:
        from overseer.tools.data_feeds import query_news_feed
        return await query_news_feed(self._settings)

    async def _handle_substack(self, input: dict) -> dict:
        from overseer.tools.data_feeds import query_substack_feed
        return await query_substack_feed(self._settings, limit=input.get("limit", 20))

    async def _handle_yellowbrick(self, input: dict) -> dict:
        from overseer.tools.data_feeds import query_yellowbrick_feed
        return await query_yellowbrick_feed(
            self._settings,
            limit=input.get("limit", 20),
            feed_type=input.get("feed_type"),
        )

    async def _handle_openinsider(self, input: dict) -> dict:
        from overseer.tools.data_feeds import query_openinsider
        return await query_openinsider(
            self._settings,
            min_insider_count=input.get("min_insider_count", 3),
            limit=input.get("limit", 20),
        )

    async def _handle_fmp(self, input: dict) -> dict:
        from overseer.tools.fmp_client import get_fmp_data
        return await get_fmp_data(
            self._settings,
            symbol=input["symbol"],
            include_quote=input.get("include_quote", True),
            include_fundamentals=input.get("include_fundamentals", True),
            include_profile=input.get("include_profile", False),
        )

    async def _handle_research(self, input: dict) -> dict:
        from overseer.tools.research_worker import run_research
        return await run_research(
            pool=self._pool,
            settings=self._settings,
            ticker=input["ticker"],
            source_type=input["source_type"],
            focus=input["focus"],
            period=input.get("period"),
            triggered_by="manual",
        )

    async def _handle_search_memory(self, input: dict) -> dict:
        from overseer.memory.episodic import search_semantic
        results = await search_semantic(
            self._pool, input["query"], top_k=input.get("top_k", 5)
        )
        return {"results": [r.model_dump() for r in results]}

    async def _handle_search_kb(self, input: dict) -> dict:
        from overseer.memory.knowledge_base import search
        # Reuse MemorySearchInput.tickers — first entry filters KB rows. The
        # all-MiniLM embedding is weak on ticker-keyed recall on its own, so
        # an explicit filter avoids returning AAPL rows for an MSFT query.
        tickers = input.get("tickers")
        ticker_filter = tickers[0] if tickers else None
        results = await search(
            self._pool,
            input["query"],
            top_k=input.get("top_k", 5),
            ticker=ticker_filter,
        )
        return {"results": [r.model_dump() for r in results]}

    async def _handle_log_observation(self, input: dict) -> dict:
        from pydantic import ValidationError
        from overseer.memory.episodic import create
        from overseer.models.memory import EpisodicMemory
        try:
            validated = LogObservationInput.model_validate(input)
        except ValidationError as e:
            # Tool-use APIs are loose with required fields. Return a clean
            # rejection with the missing/invalid fields named so the LLM can
            # retry; the historic behavior was a KeyError that bubbled up as
            # a generic tool execution error.
            log.warning(
                "log_observation_validation_failed",
                input_keys=list(input.keys()),
                errors=[{"loc": err["loc"], "msg": err["msg"]} for err in e.errors()],
            )
            return {
                "status": "rejected",
                "error": "Input validation failed",
                "details": [
                    {"field": ".".join(str(p) for p in err["loc"]), "msg": err["msg"]}
                    for err in e.errors()
                ],
            }
        memory = EpisodicMemory(
            event_type=validated.event_type,
            summary=validated.summary,
            details=validated.details,
            tickers=validated.tickers,
            tags=validated.tags,
            importance=validated.importance,
        )
        mem_id = await create(self._pool, memory)
        return {"id": mem_id, "status": "logged"}

    async def _handle_get_principles(self, input: dict) -> dict:
        from overseer.memory.principles import get_active
        principles = await get_active(self._pool, category=input.get("category"))
        return {"principles": [p.model_dump() for p in principles]}

    async def _handle_propose_trade(self, input: dict) -> dict:
        from overseer.models.tools import ProposeTradeInput
        from overseer.tools.trading import propose_trade
        trade_input = ProposeTradeInput(**input)
        return await propose_trade(self._pool, self._settings, trade_input)

    async def _handle_portfolio(self, input: dict) -> dict:
        from overseer.tools.portfolio import get_portfolio_state
        state = await get_portfolio_state(self._pool, self._settings)
        return state.model_dump()

    async def _handle_check_pending_trades(self, input: dict) -> dict:
        from overseer.tools.trading import check_pending_trades
        return await check_pending_trades(self._pool, self._settings)

    async def _handle_circuit_breakers(self, input: dict) -> dict:
        from overseer.tools.system_tools import check_circuit_breakers
        return await check_circuit_breakers(self._pool)

    async def _handle_compare_thesis(self, input: dict) -> dict:
        from overseer.tools.system_tools import compare_to_thesis
        return await compare_to_thesis(self._pool, input["decision_id"], input.get("current_data", {}))

    async def _handle_discord(self, input: dict) -> dict:
        from overseer.tools.discord_tools import send_discord_message
        sent = await send_discord_message(
            self._settings, input["content"], message_type=input.get("message_type", "info")
        )
        return {"sent": sent}

    async def _handle_capability_wish(self, input: dict) -> dict:
        from overseer.models.cycle import CapabilityWish
        from overseer.tools.system_tools import request_capability
        wish = CapabilityWish(**input)
        wish_id = await request_capability(self._pool, wish)
        return {"wish_id": wish_id, "status": "recorded"}

    async def _handle_write_reflection(self, input: dict) -> dict:
        from overseer.memory.working import set as wm_set
        key = input.get("key")
        if not key or not isinstance(key, str):
            return {
                "status": "error",
                "error": "write_reflection requires a non-empty 'key' string argument",
            }
        if "value" not in input:
            return {
                "status": "error",
                "error": "write_reflection requires a 'value' argument",
            }
        # Block scheduler-internal keys. The LLM kept clobbering drought
        # counters with narrative strings, breaking the skip-check backoff.
        from overseer.core.context_builder import _SCHEDULER_INTERNAL_KEYS
        if key in _SCHEDULER_INTERNAL_KEYS:
            return {
                "status": "error",
                "error": f"key '{key}' is reserved for the scheduler and cannot be written via write_reflection",
            }
        await wm_set(self._pool, key, input["value"])
        return {"key": key, "status": "updated"}

    async def _handle_earnings_calendar(self, input: dict) -> dict:
        from overseer.tools.fmp_client import get_earnings_calendar
        result = await get_earnings_calendar(self._settings, input["symbol"])
        next_e = result.get("next_earnings")
        if next_e and next_e.get("days_until") is not None:
            days = next_e["days_until"]
            if days <= 14:
                result["earnings_risk"] = "HIGH"
                result["earnings_warning"] = (
                    f"EARNINGS IN {days} DAYS ({next_e['date']}). "
                    f"High risk of gap move. Consider waiting until after earnings."
                )
            else:
                result["earnings_risk"] = "LOW"
                result["earnings_warning"] = None
        else:
            result["earnings_risk"] = "UNKNOWN"
            result["earnings_warning"] = "No earnings date found. Exercise caution."
        return result

    async def _handle_check_spending(self, input: dict) -> dict:
        from overseer.tools.spending import check_spending
        return await check_spending(self._pool, self._settings, days=input.get("days", 1))

    async def _handle_get_theses(self, input: dict) -> dict:
        from overseer.tools.thesis import get_active_theses
        return await get_active_theses(self._pool, ticker=input.get("ticker"))

    async def _handle_create_thesis(self, input: dict) -> dict:
        from overseer.tools.thesis import create_thesis
        return await create_thesis(
            self._pool,
            ticker=input["ticker"],
            thesis_statement=input["thesis_statement"],
            position_type=input.get("position_type", "LONG"),
            conviction=input.get("conviction", "MEDIUM"),
            pillars=input.get("pillars"),
            catalysts=input.get("catalysts"),
            risks=input.get("risks"),
            target_price=input.get("target_price"),
            stop_loss=input.get("stop_loss"),
            valuation_methodology=input.get("valuation_methodology"),
            entry_price=input.get("entry_price"),
        )

    async def _handle_update_thesis(self, input: dict) -> dict:
        from overseer.tools.thesis import update_thesis
        return await update_thesis(
            self._pool,
            thesis_id=input["thesis_id"],
            data_point=input["data_point"],
            thesis_impact=input["thesis_impact"],
            action=input.get("action", "MAINTAIN"),
            conviction_change=input.get("conviction_change"),
            pillar_updates=input.get("pillar_updates"),
            new_catalysts=input.get("new_catalysts"),
            new_risks=input.get("new_risks"),
            target_price=input.get("target_price"),
            stop_loss=input.get("stop_loss"),
        )

    async def _handle_close_thesis(self, input: dict) -> dict:
        from overseer.tools.thesis import close_thesis
        return await close_thesis(
            self._pool,
            thesis_id=input["thesis_id"],
            reason=input["reason"],
            outcome=input.get("outcome", "exited"),
        )

    async def _handle_benchmark(self, input: dict) -> dict:
        from overseer.tools.fmp_client import get_benchmark_return
        from overseer.tools.portfolio import get_portfolio_state
        from overseer.utils.database import fetchrow, fetchval

        row = await fetchrow(
            self._pool,
            "SELECT MIN(created_at) AS first_trade FROM trades WHERE status = 'filled'",
        )
        if not row or not row["first_trade"]:
            return {"error": "No filled trades found — cannot determine inception date"}

        inception_date = row["first_trade"].strftime("%Y-%m-%d")

        # Use actual invested capital (sum of cash deposits/withdrawals) as the
        # return denominator. Previously hardcoded to $1000 which produced wrong
        # return% and alpha whenever the real portfolio value differed — the
        # LLM was consuming phantom performance numbers.
        invested = await fetchval(
            self._pool,
            "SELECT COALESCE(SUM(amount), 0) FROM cash_flows",
        )
        initial_value = float(invested) if invested and float(invested) > 0 else 1000.0

        benchmark = await get_benchmark_return(self._settings, inception_date)
        if "error" in benchmark:
            return benchmark

        state = await get_portfolio_state(self._pool, self._settings)
        portfolio_return_pct = ((state.total_value / initial_value) - 1) * 100
        alpha = round(portfolio_return_pct - benchmark["benchmark_return_pct"], 2)

        return {
            "inception_date": inception_date,
            "days_held": benchmark["days_held"],
            "portfolio": {
                "initial_value": initial_value,
                "current_value": state.total_value,
                "return_pct": round(portfolio_return_pct, 2),
            },
            "benchmark": {
                "symbol": benchmark["benchmark"],
                "inception_price": benchmark["inception_price"],
                "current_price": benchmark["current_price"],
                "return_pct": benchmark["benchmark_return_pct"],
            },
            "alpha_pct": alpha,
            "outperforming": alpha > 0,
        }
