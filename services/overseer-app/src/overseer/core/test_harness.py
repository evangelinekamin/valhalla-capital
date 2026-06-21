"""Test harness for benchmarking OpenRouter models on the agent loop.

Runs cycles with mock tool responses so we can compare models without
hitting real APIs, writing to the database, or posting to Discord.

Usage:
    python -m overseer.core.test_harness --model deepseek/deepseek-v3.2
    python -m overseer.core.test_harness --model moonshotai/kimi-k2.5 --cycle data_synthesis
    python -m overseer.core.test_harness --compare deepseek/deepseek-v3.2,openai/gpt-oss-120b
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from typing import Any

import structlog

from overseer.core.openrouter_client import OpenRouterClient

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Mock tool data — realistic canned responses
# ---------------------------------------------------------------------------

MOCK_PORTFOLIO = json.dumps({
    "total_value": 1005.49,
    "cash": 104.22,
    "positions": [
        {"ticker": "DMLP", "qty": 5, "avg_price": 23.10, "market_value": 117.50, "unrealized_pnl": 2.00, "pnl_pct": 1.7},
        {"ticker": "FOUR", "qty": 2, "avg_price": 73.50, "market_value": 152.80, "unrealized_pnl": 5.80, "pnl_pct": 3.9},
        {"ticker": "IPI", "qty": 4, "avg_price": 28.75, "market_value": 118.20, "unrealized_pnl": 3.20, "pnl_pct": 2.8},
        {"ticker": "RAL", "qty": 10, "avg_price": 24.60, "market_value": 253.00, "unrealized_pnl": 7.00, "pnl_pct": 2.8},
        {"ticker": "SKWD", "qty": 5, "avg_price": 43.20, "market_value": 222.75, "unrealized_pnl": 6.75, "pnl_pct": 3.1},
        {"ticker": "TBPH", "qty": 2, "avg_price": 17.50, "market_value": 32.04, "unrealized_pnl": -2.96, "pnl_pct": -8.5},
    ],
    "data_age_seconds": 120,
})

MOCK_TWITTER = json.dumps({
    "data_fresh": True,
    "data_staleness_hours": 0.5,
    "tweets": [
        {"username": "firstadopter", "content": "Oil up 10% and stock market futures tanking after Iran escalation. This is unsustainable for the global economy.", "classification": "CRITICAL", "sentiment": "bearish", "tickers": [], "published_at": "2026-04-05T14:30:00Z"},
        {"username": "SSI_invest", "content": "$VRE being acquired by a real estate investment manager at $19.00/share cash. Closing Q2'26.", "classification": "CRITICAL", "sentiment": "bullish", "tickers": ["VRE"], "published_at": "2026-04-05T13:15:00Z"},
        {"username": "InvestSpecial", "content": "$SOFI fintech mask hides massive unsecured lending. NII >60%. Re-rate to bank multiples => 60%+ downside.", "classification": "IMPORTANT", "sentiment": "bearish", "tickers": ["SOFI"], "published_at": "2026-04-05T12:00:00Z"},
        {"username": "rubicon59", "content": "No amount of compression will reduce demand for memory and compute. $NVDA $MU", "classification": "IMPORTANT", "sentiment": "bullish", "tickers": ["NVDA", "MU"], "published_at": "2026-04-05T11:30:00Z"},
        {"username": "taobanker", "content": "Remarkable disconnect: EPS projections soaring while S&P dumping. One twitch in Mag7 capex and the last pillar cracks.", "classification": "IMPORTANT", "sentiment": "bearish", "tickers": [], "published_at": "2026-04-05T10:45:00Z"},
    ],
})

MOCK_NEWS = json.dumps({
    "critical_alerts": [
        {"headline": "Trump issues ultimatum to Iran over Hormuz Strait blockage", "source": "BBC", "classification": "CRITICAL", "published": "2026-04-05T16:30:00Z"},
        {"headline": "US crude inventories fall to 3-year low as Iran conflict disrupts shipping", "source": "Reuters", "classification": "CRITICAL", "published": "2026-04-05T15:00:00Z"},
    ],
    "unacknowledged": 2,
})

MOCK_CIRCUIT_BREAKERS = json.dumps({
    "all_clear": True,
    "market_open": False,
    "daily_loss_pct": 0.0,
    "trades_today": 0,
    "max_trades_per_day": 5,
})

MOCK_THESES = json.dumps([
    {"id": 1, "ticker": "RAL", "thesis_statement": "Undervalued specialty chemicals play with catalyst from restructuring", "conviction": "HIGH", "position_type": "LONG", "target_price": 30.0, "stop_loss": 20.0, "status": "active"},
    {"id": 2, "ticker": "FOUR", "thesis_statement": "Payment processing compounder with durable SMB moat", "conviction": "MEDIUM", "position_type": "LONG", "target_price": 90.0, "stop_loss": 65.0, "status": "active"},
])

MOCK_EARNINGS = json.dumps({"symbol": "RAL", "next_earnings_date": "2026-04-22", "days_until": 17, "risk_level": "NORMAL"})

MOCK_SPENDING = json.dumps({"period": "1 day", "total_cost_cents": 45.2, "by_model": {"claude-haiku-4-5-20251001": 12.1, "claude-sonnet-4-6": 33.1}})

MOCK_BENCHMARK = json.dumps({"portfolio_return_pct": 4.2, "spy_return_pct": 2.8, "alpha_pct": 1.4, "period": "since_inception"})

MOCK_MEMORY_SEARCH = json.dumps({"results": [{"summary": "Iran conflict escalation began mid-March 2026, oil spiked 40% in 2 weeks", "importance": 0.8, "created_at": "2026-03-18"}]})

MOCK_KB_SEARCH = json.dumps({"results": [{"content": "Geopolitical shocks historically cause 3-5 day sell-offs followed by recovery unless fundamentals deteriorate", "source": "investment_literature"}]})

MOCK_SUBSTACK = json.dumps({"newsletters": []})
MOCK_YELLOWBRICK = json.dumps({"pitches": []})
MOCK_OPENINSIDER = json.dumps({"clusters": []})
MOCK_PENDING = json.dumps({"pending_trades": [], "recently_filled": []})

# Map tool names to mock responses
MOCK_RESPONSES: dict[str, str] = {
    "get_portfolio_state": MOCK_PORTFOLIO,
    "query_twitter_feed": MOCK_TWITTER,
    "query_news_feed": MOCK_NEWS,
    "check_circuit_breakers": MOCK_CIRCUIT_BREAKERS,
    "get_active_theses": MOCK_THESES,
    "check_earnings_calendar": MOCK_EARNINGS,
    "check_spending": MOCK_SPENDING,
    "get_benchmark_performance": MOCK_BENCHMARK,
    "search_memory": MOCK_MEMORY_SEARCH,
    "search_knowledge_base": MOCK_KB_SEARCH,
    "query_substack_feed": MOCK_SUBSTACK,
    "query_yellowbrick_feed": MOCK_YELLOWBRICK,
    "query_openinsider": MOCK_OPENINSIDER,
    "check_pending_trades": MOCK_PENDING,
    "get_active_principles": json.dumps({"principles": [{"text": "Never average down without a thesis update", "confidence": 0.85}]}),
    "get_fmp_data": json.dumps({"symbol": "RAL", "quote": {"price": 25.30, "change_pct": 1.2, "volume": 45000}, "profile": {"sector": "Materials"}}),
    # Write operations return confirmation
    "log_observation": json.dumps({"status": "logged", "id": 999}),
    "write_reflection": json.dumps({"status": "saved"}),
    "send_discord_message": json.dumps({"status": "sent (mock)"}),
    "request_capability": json.dumps({"status": "logged", "id": 50}),
    "propose_trade": json.dumps({"status": "blocked", "reason": "TEST MODE - trade not submitted"}),
    "compare_to_thesis": json.dumps({"thesis_id": 1, "status": "intact", "pillars_holding": 3, "pillars_weakened": 0}),
    "create_thesis": json.dumps({"status": "created (mock)", "thesis_id": 99}),
    "update_thesis": json.dumps({"status": "updated (mock)"}),
    "close_thesis": json.dumps({"status": "closed (mock)"}),
}


# ---------------------------------------------------------------------------
# Mock tool registry that returns canned data
# ---------------------------------------------------------------------------

def get_mock_tool_definitions() -> list[dict]:
    """Return real tool definitions but backed by mock execution."""
    # Import real definitions for schema accuracy
    try:
        from overseer.config import get_settings
        from overseer.core.tool_registry import ToolRegistry
        import asyncpg

        # We just need the definitions, not a real pool
        # Create a minimal mock
        class FakePool:
            pass

        settings = get_settings()
        registry = ToolRegistry.__new__(ToolRegistry)
        registry._pool = FakePool()
        registry._settings = settings
        registry._handlers = {}
        registry._definitions = []

        # We can't call _register_all without a real pool, so build from schema
        pass
    except Exception:
        pass

    # Fallback: build definitions manually from known tools
    from overseer.models.tools import (
        TwitterQueryInput, NewsQueryInput, SubstackQueryInput,
        YellowbrickQueryInput, OpenInsiderQueryInput, FMPDataInput,
        MemorySearchInput, LogObservationInput, ProposeTradeInput,
        CapabilityWishInput, DiscordMessageInput, CompareToThesisInput,
        EarningsCalendarInput, CheckSpendingInput, CreateThesisInput,
        UpdateThesisInput, CloseThesisInput, GetThesesInput,
    )

    def _schema(model_cls) -> dict:
        s = model_cls.model_json_schema()
        s.pop("title", None)
        return s

    tools = [
        {"name": "get_portfolio_state", "description": "Get current portfolio positions, cash, and P&L from IBKR.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "query_twitter_feed", "description": "Query classified tweets from financial Twitter accounts.", "input_schema": _schema(TwitterQueryInput)},
        {"name": "query_news_feed", "description": "Get critical news alerts from RSS feed monitor.", "input_schema": _schema(NewsQueryInput)},
        {"name": "query_substack_feed", "description": "Get recent investment newsletter recommendations.", "input_schema": _schema(SubstackQueryInput)},
        {"name": "query_yellowbrick_feed", "description": "Get investment pitches from Yellowbrick.", "input_schema": _schema(YellowbrickQueryInput)},
        {"name": "query_openinsider", "description": "Get insider trading cluster buys from OpenInsider.", "input_schema": _schema(OpenInsiderQueryInput)},
        {"name": "get_fmp_data", "description": "Get FMP financial data (quote, fundamentals, profile) for a ticker.", "input_schema": _schema(FMPDataInput)},
        {"name": "search_memory", "description": "Semantic search over episodic memory observations.", "input_schema": _schema(MemorySearchInput)},
        {"name": "search_knowledge_base", "description": "Semantic search over investment literature knowledge base.", "input_schema": _schema(MemorySearchInput)},
        {"name": "log_observation", "description": "Record a new observation to episodic memory.", "input_schema": _schema(LogObservationInput)},
        {"name": "get_active_principles", "description": "Get learned investment principles.", "input_schema": {"type": "object", "properties": {"category": {"type": "string"}}}},
        {"name": "propose_trade", "description": "Propose a Kelly-criterion sized trade with falsification criteria.", "input_schema": _schema(ProposeTradeInput)},
        {"name": "check_pending_trades", "description": "Check status of pending/submitted trades.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "check_circuit_breakers", "description": "Check daily loss halt, trade limits, market hours.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "compare_to_thesis", "description": "Compare current data against a decision's thesis.", "input_schema": _schema(CompareToThesisInput)},
        {"name": "send_discord_message", "description": "Send a message to the Discord channel.", "input_schema": _schema(DiscordMessageInput)},
        {"name": "request_capability", "description": "Log a wish for a new data source or capability.", "input_schema": _schema(CapabilityWishInput)},
        {"name": "write_reflection", "description": "Set a key/value in working memory.", "input_schema": {"type": "object", "properties": {"key": {"type": "string"}, "value": {}}, "required": ["key", "value"]}},
        {"name": "check_earnings_calendar", "description": "Check upcoming earnings date for a ticker.", "input_schema": _schema(EarningsCalendarInput)},
        {"name": "check_spending", "description": "Check Anthropic API spending by model.", "input_schema": _schema(CheckSpendingInput)},
        {"name": "get_active_theses", "description": "Get all active investment theses.", "input_schema": _schema(GetThesesInput)},
        {"name": "create_thesis", "description": "Create a new structured investment thesis.", "input_schema": _schema(CreateThesisInput)},
        {"name": "update_thesis", "description": "Update an existing thesis with new data.", "input_schema": _schema(UpdateThesisInput)},
        {"name": "close_thesis", "description": "Close a thesis on exit or invalidation.", "input_schema": _schema(CloseThesisInput)},
        {"name": "get_benchmark_performance", "description": "Get portfolio vs SPY alpha since inception.", "input_schema": {"type": "object", "properties": {}}},
    ]
    return tools


async def mock_execute(tool_name: str, tool_input: dict) -> str:
    """Execute a tool call against mock data."""
    response = MOCK_RESPONSES.get(tool_name)
    if response is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    # For tools that take a symbol, customize the mock slightly
    if tool_name == "get_fmp_data" and "symbol" in tool_input:
        sym = tool_input["symbol"]
        return json.dumps({"symbol": sym, "quote": {"price": 25.30, "change_pct": 1.2, "volume": 45000}, "profile": {"sector": "Materials"}})

    if tool_name == "check_earnings_calendar" and "symbol" in tool_input:
        sym = tool_input["symbol"]
        return json.dumps({"symbol": sym, "next_earnings_date": "2026-04-22", "days_until": 17, "risk_level": "NORMAL"})

    return response


# ---------------------------------------------------------------------------
# Test cycle prompts
# ---------------------------------------------------------------------------

QUICK_CHECK_SYSTEM = """You are an autonomous AI investment analyst managing a small-cap value portfolio.

CURRENT PORTFOLIO: $1,005 total value, 6 positions (DMLP, FOUR, IPI, RAL, SKWD, TBPH) + $104 cash.

This is a QUICK CHECK cycle.
Focus: Scan for urgent signals that need immediate attention.
- Check critical tweets and news alerts
- Look for price-moving events on watchlist tickers
- Flag anything requiring deeper analysis in the next data_synthesis cycle
- Do NOT make trade decisions in this cycle - only flag opportunities
Keep token usage minimal. Be brief."""

DATA_SYNTHESIS_SYSTEM = """You are an autonomous AI investment analyst managing a small-cap value portfolio.

CURRENT PORTFOLIO: $1,005 total value, 6 positions (DMLP, FOUR, IPI, RAL, SKWD, TBPH) + $104 cash.

This is a DATA SYNTHESIS cycle.
Focus: Cross-reference data from multiple sources to build conviction.
- Synthesize Twitter, news, Substack, and other feeds
- Update working memory with market observations
- Evaluate if any positions need attention based on new data
- Propose trades ONLY on high conviction with clear thesis
Be thorough but concise."""

DEEP_ANALYSIS_SYSTEM = """You are an autonomous AI investment analyst managing a small-cap value portfolio.

CURRENT PORTFOLIO: $1,005 total value, 6 positions (DMLP, FOUR, IPI, RAL, SKWD, TBPH) + $104 cash.

This is a DEEP ANALYSIS cycle.
Focus: Deep fundamental analysis of positions and candidates.
- Review each position against its thesis and falsification criteria
- Analyze new candidates from Substack/Yellowbrick with FMP data
- Build or update investment theses with Kelly criterion sizing
- Check earnings calendar for upcoming catalysts
Be thorough. Quality over speed."""

WEEKLY_REVIEW_SYSTEM = """You are an autonomous AI investment analyst managing a small-cap value portfolio.

CURRENT PORTFOLIO: $1,005 total value, 6 positions (DMLP, FOUR, IPI, RAL, SKWD, TBPH) + $104 cash.

This is a WEEKLY REVIEW cycle.
Focus: Strategic weekly assessment and reflection.
- Review portfolio performance vs benchmark
- Assess win/loss patterns and update learned principles
- Evaluate thesis health for all positions
- Check spending and operational efficiency
- Prioritize capability wishes
- Send comprehensive Discord report
Be comprehensive and strategic. This is the most important cycle of the week."""

CYCLE_PROMPTS = {
    "quick_check": (QUICK_CHECK_SYSTEM, "Quick check: scan for urgent signals across Twitter and news feeds."),
    "data_synthesis": (DATA_SYNTHESIS_SYSTEM, "Synthesize recent data from all feeds. What patterns emerge? Any positions need attention?"),
    "deep_analysis": (DEEP_ANALYSIS_SYSTEM, "Run deep fundamental analysis on all positions. Check each thesis, review new candidates, and assess Kelly sizing."),
    "weekly_review": (WEEKLY_REVIEW_SYSTEM, "Conduct the weekly strategic review. Assess performance, review theses, update principles, and prepare the Discord report."),
}

# Replay data files (real tool outputs captured from the DB)
REPLAY_FILES = {
    "data_synthesis": "replay_data_synthesis.json",
    "deep_analysis": "replay_deep_analysis.json",
    "weekly_review": "replay_weekly_review.json",
}


# ---------------------------------------------------------------------------
# Agent loop (mock version)
# ---------------------------------------------------------------------------

MAX_ITERATIONS = 25
MAX_TOOL_OUTPUT_CHARS = 4000


def load_replay_data(cycle_type: str) -> dict[str, str] | None:
    """Load real tool outputs from a replay file if available."""
    fname = REPLAY_FILES.get(cycle_type)
    if not fname:
        return None
    import pathlib
    path = pathlib.Path(__file__).parent / fname
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    # Build lookup: tool_name -> list of outputs (in order, for repeated calls)
    lookup: dict[str, list[str]] = {}
    for tc in data.get("tool_calls", []):
        lookup.setdefault(tc["name"], []).append(tc["output"])
    return lookup


class ReplayExecutor:
    """Returns real tool outputs in order, falling back to mock data."""

    def __init__(self, replay_data: dict[str, list[str]] | None):
        self._replay = replay_data or {}
        self._cursors: dict[str, int] = {}

    async def execute(self, tool_name: str, tool_input: dict) -> str:
        outputs = self._replay.get(tool_name, [])
        cursor = self._cursors.get(tool_name, 0)
        if cursor < len(outputs):
            self._cursors[tool_name] = cursor + 1
            return outputs[cursor]
        # Fallback to static mock
        return await mock_execute(tool_name, tool_input)


async def run_mock_cycle(
    model: str,
    api_key: str,
    cycle_type: str = "quick_check",
    max_tokens: int = 8192,
    use_replay: bool = True,
) -> dict:
    """Run a cycle with mock/replayed tools — no DB, no Discord, no real trades."""
    from overseer.core.openrouter_client import OpenRouterClient

    client = OpenRouterClient(api_key=api_key)
    tools = get_mock_tool_definitions()

    replay_data = load_replay_data(cycle_type) if use_replay else None
    executor = ReplayExecutor(replay_data)

    system_prompt, user_message = CYCLE_PROMPTS.get(cycle_type, CYCLE_PROMPTS["quick_check"])

    system_blocks = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
    messages = [{"role": "user", "content": user_message}]

    total_in = 0
    total_out = 0
    all_tool_calls = []
    iteration = 0
    final_text = ""
    start_total = time.monotonic()

    while iteration < MAX_ITERATIONS:
        iteration += 1
        start = time.monotonic()

        try:
            response = await client.messages.create(
                model=model, max_tokens=max_tokens,
                system=system_blocks, tools=tools, messages=messages,
            )
        except Exception as e:
            final_text += f"[Error: {e}]"
            break

        elapsed_ms = int((time.monotonic() - start) * 1000)
        total_in += response.usage.input_tokens
        total_out += response.usage.output_tokens

        if response.stop_reason in {"end_turn", "stop_sequence"}:
            for block in response.content:
                if block.type == "text":
                    final_text += block.text
            break

        if response.stop_reason == "tool_use":
            assistant_content = []
            tool_results = []

            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                    final_text += block.text
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use", "id": block.id,
                        "name": block.name, "input": block.input,
                    })

                    tool_output = await executor.execute(block.name, block.input)
                    all_tool_calls.append({"name": block.name, "input": block.input})

                    if len(tool_output) > MAX_TOOL_OUTPUT_CHARS:
                        tool_output = tool_output[:MAX_TOOL_OUTPUT_CHARS] + "\n[TRUNCATED]"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_output,
                    })

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    total_elapsed = time.monotonic() - start_total

    return {
        "model": model,
        "cycle_type": cycle_type,
        "iterations": iteration,
        "tokens_in": total_in,
        "tokens_out": total_out,
        "tool_calls": [tc["name"] for tc in all_tool_calls],
        "elapsed_sec": round(total_elapsed, 1),
        "final_text": final_text,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Overseer model test harness")
    parser.add_argument("--model", type=str, help="Single model to test")
    parser.add_argument("--compare", type=str, help="Comma-separated models to compare")
    parser.add_argument("--cycle", type=str, default="quick_check",
                        choices=["quick_check", "data_synthesis", "deep_analysis", "weekly_review"])
    parser.add_argument("--api-key", type=str, default=None, help="OpenRouter API key")
    args = parser.parse_args()

    # Resolve API key
    api_key = args.api_key
    if not api_key:
        try:
            from overseer.config import get_settings
            api_key = get_settings().openrouter_api_key
        except Exception:
            import os
            api_key = os.getenv("OPENROUTER_API_KEY", "")

    if not api_key:
        print("ERROR: No OpenRouter API key. Use --api-key or set OPENROUTER_API_KEY.")
        return

    models = []
    if args.compare:
        models = [m.strip() for m in args.compare.split(",")]
    elif args.model:
        models = [args.model]
    else:
        models = ["deepseek/deepseek-v3.2", "openai/gpt-oss-120b"]

    print(f"Testing {len(models)} model(s) on {args.cycle} cycle\n")

    results = []
    for model in models:
        print(f"--- {model} ---")
        result = await run_mock_cycle(model, api_key, args.cycle)
        results.append(result)
        print(f"  Iterations: {result['iterations']}")
        print(f"  Tokens: {result['tokens_in']} in / {result['tokens_out']} out")
        print(f"  Tool calls: {result['tool_calls']}")
        print(f"  Time: {result['elapsed_sec']}s")
        print(f"  Output preview: {result['final_text'][:300]}")
        print()

    if len(results) > 1:
        print("=" * 70)
        print(f"{'Model':<35} {'Iters':>6} {'In':>7} {'Out':>7} {'Tools':>6} {'Time':>6}")
        print("-" * 70)
        for r in results:
            print(f"{r['model']:<35} {r['iterations']:>6} {r['tokens_in']:>7} {r['tokens_out']:>7} {len(r['tool_calls']):>6} {r['elapsed_sec']:>5.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
