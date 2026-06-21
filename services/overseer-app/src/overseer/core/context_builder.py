from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from overseer.memory import working
from overseer.memory.episodic import get_recent, search_semantic
from overseer.memory.principles import get_active
from overseer.utils import database as db

log = structlog.get_logger()

# Keys always included regardless of cycle type
_ESSENTIAL_KEYS = frozenset({
    "watchlist",
    "portfolio_state",
    "last_cycle_at",
    "active_alerts",
    "circuit_breaker_state",
    "trading_halted",
    "pending_trades",
})

# Scheduler-internal keys the LLM should never see or write to. The model
# was interpreting "*_drought_level" as a status-summary field and calling
# write_reflection with narrative text, which broke int() in drought.py and
# disabled backoff. Filter them out of every context.
_SCHEDULER_INTERNAL_KEYS = frozenset({
    "quick_check_drought_level",
    "quick_check_last_actual_run_at",
    "data_synthesis_drought_level",
    "data_synthesis_last_actual_run_at",
})

# Dated key patterns (prefix -> how many most-recent to keep per cycle tier)
_DATED_KEY_LIMITS: dict[str, dict[str, int]] = {
    "market_synthesis": {
        "quick_check": 1,
        "data_synthesis": 2,
        "deep_analysis": 3,
        "daily_review": 3,
        "weekly_review": 5,
        "monthly_review": 5,
    },
    "day_": {
        "quick_check": 0,
        "data_synthesis": 0,
        "deep_analysis": 1,
        "daily_review": 2,
        "weekly_review": 5,
        "monthly_review": 5,
    },
    "deep_analysis": {
        "quick_check": 0,
        "data_synthesis": 1,
        "deep_analysis": 2,
        "daily_review": 2,
        "weekly_review": 3,
        "monthly_review": 3,
    },
}


def _filter_working_memory(wm: dict[str, Any], cycle_type: str) -> dict[str, Any]:
    """Return a filtered subset of working memory appropriate for the cycle type."""
    if not wm:
        return wm

    filtered = {}
    dated_buckets: dict[str, list[tuple[str, Any]]] = {
        prefix: [] for prefix in _DATED_KEY_LIMITS
    }

    for key, value in wm.items():
        # Never surface scheduler internals to the LLM — the model kept
        # overwriting drought counters with narrative status text.
        if key in _SCHEDULER_INTERNAL_KEYS:
            continue

        # Always include essential keys
        if key in _ESSENTIAL_KEYS:
            filtered[key] = value
            continue

        # Bucket dated keys for later sorting/limiting
        bucketed = False
        for prefix in _DATED_KEY_LIMITS:
            if key.startswith(prefix):
                dated_buckets[prefix].append((key, value))
                bucketed = True
                break

        # Non-essential, non-dated keys: include for all cycles except quick_check
        if not bucketed and cycle_type != "quick_check":
            filtered[key] = value

    # For each dated bucket, keep only the N most recent by key name (lexicographic)
    for prefix, entries in dated_buckets.items():
        limit = _DATED_KEY_LIMITS[prefix].get(cycle_type, 2)
        if limit == 0:
            continue
        # Sort by key descending (newer dates sort later alphabetically for these formats)
        # Use updated_at from DB would be ideal, but we only have key/value here.
        # The keys contain dates so reverse-sort gives us most recent.
        sorted_entries = sorted(entries, key=lambda kv: kv[0], reverse=True)
        for key, value in sorted_entries[:limit]:
            filtered[key] = value

    original_size = sum(len(json.dumps(v, default=str)) for v in wm.values())
    filtered_size = sum(len(json.dumps(v, default=str)) for v in filtered.values())
    log.info(
        "working_memory_filtered",
        cycle_type=cycle_type,
        original_keys=len(wm),
        filtered_keys=len(filtered),
        original_bytes=original_size,
        filtered_bytes=filtered_size,
        reduction_pct=round((1 - filtered_size / max(original_size, 1)) * 100, 1),
    )

    return filtered

_STALE_THRESHOLD = timedelta(hours=12)
_EXPIRE_THRESHOLD = timedelta(hours=48)
# Hard archival cutoff: past this, entries are dropped from context entirely
# (still in the DB if a future tool wants them).
_ARCHIVAL_THRESHOLD = timedelta(days=7)

# Keys containing rapidly-changing world state get a soft staleness threshold.
# Past TTL, content is annotated as STALE but kept visible — Friday-close
# Opus reviews need yesterday's market synthesis intact, and a redacted
# field that the agent can't read is worse than a labelled-old one she can.
# The "war/ceasefire" risk is handled by recency-pinned tools the agent
# can call (query_news_feed) and by principles, not by silencing memory.
_RAPID_EXPIRY: list[tuple[str, timedelta]] = [
    ("today_", timedelta(hours=72)),
    ("geopolitical_", timedelta(hours=72)),
    ("quick_check_", timedelta(hours=24)),
]


def _get_expiry_threshold(key: str) -> timedelta:
    """Return the soft-staleness threshold for a working memory key."""
    for prefix, ttl in _RAPID_EXPIRY:
        if key.startswith(prefix):
            return ttl
    return _EXPIRE_THRESHOLD


def _annotate_stale_entries(
    wm: dict[str, Any],
    timestamps: dict[str, datetime],
    now_utc: datetime,
) -> dict[str, Any]:
    """Annotate stale entries; archive only beyond _ARCHIVAL_THRESHOLD.

    Stale entries (past their TTL) keep their content but get a STALE prefix
    so the agent treats them with appropriate suspicion. Genuinely ancient
    entries (>7d) are summarised to a one-line marker — they pollute context
    without earning their place.
    """
    stale = {}
    archived = {}
    result = {}

    for key, value in wm.items():
        ts = timestamps.get(key)
        if ts is None:
            result[key] = value
            continue

        age = now_utc - ts
        expire_at = _get_expiry_threshold(key)
        age_str = f"{age.days}d" if age.days >= 1 else f"{int(age.total_seconds() / 3600)}h"

        if age > _ARCHIVAL_THRESHOLD:
            # Drop content from prompt, keep one-line provenance marker.
            result[key] = f"[ARCHIVED -- {age_str} old, written {ts.strftime('%Y-%m-%d')}. Re-fetch via tools if needed.]"
            archived[key] = age_str
        elif age > expire_at:
            ts_str = ts.strftime('%Y-%m-%d %H:%M UTC')
            result[key] = {
                "_stale": True,
                "_written_at": ts_str,
                "_age": age_str,
                "_caveat": "Past freshness window — verify with current tools before acting.",
                "content": value,
            }
            stale[key] = f"stale {age_str} (written {ts.strftime('%Y-%m-%d')})"
        elif age > _STALE_THRESHOLD:
            days = age.days
            if days >= 1:
                stale[key] = f"written {ts.strftime('%Y-%m-%d')} ({days}d ago) -- verify before relying"
            else:
                hours = int(age.total_seconds() / 3600)
                stale[key] = f"written {ts.strftime('%Y-%m-%d %H:%M')} UTC ({hours}h ago)"
            result[key] = value
        else:
            result[key] = value

    annotations = {}
    if archived:
        annotations["_archived_keys"] = archived
    if stale:
        annotations["_stale_entries"] = stale

    if annotations:
        return {**annotations, **result}
    return result


async def _build_position_alerts(pool, portfolio_cached: dict) -> list[str]:
    """Check stop losses, targets, thesis age, and position concentrations.

    Returns a list of alert strings to inject into the system prompt so the
    AI cannot ignore them.
    """
    alerts: list[str] = []

    theses = await db.fetch(
        pool,
        """SELECT id, ticker, stop_loss, target_price, entry_price,
                  conviction, created_at
           FROM thesis_tracker WHERE status = 'active'""",
    )
    if not theses:
        return alerts

    positions = {
        p.get("ticker"): p
        for p in portfolio_cached.get("positions", [])
    }
    total_value = portfolio_cached.get("total_value", 0)
    now = datetime.now(timezone.utc)

    for thesis in theses:
        ticker = thesis["ticker"]
        pos = positions.get(ticker)
        if not pos:
            continue

        current_price = pos.get("current_price", 0)
        if not current_price:
            continue

        # --- Stop-loss breach ---
        if thesis["stop_loss"] and current_price <= thesis["stop_loss"]:
            alerts.append(
                f"CODE RED -- STOP-LOSS BREACH: {ticker} at ${current_price:.2f} "
                f"has breached stop-loss of ${thesis['stop_loss']:.2f}. "
                f"DEFAULT ACTION IS SELL. You must find overwhelming NEW fundamental "
                f"evidence to override. Price recovery is NOT evidence. Lack of new "
                f"negative news is NOT a reason to hold. Execute "
                f"propose_trade(action='sell', ticker='{ticker}') unless you build "
                f"a HIGH-confidence case with FRESH data in this cycle."
            )

        # --- Target price reached ---
        if thesis["target_price"] and current_price >= thesis["target_price"]:
            alerts.append(
                f"TARGET REACHED: {ticker} at ${current_price:.2f} has hit "
                f"target of ${thesis['target_price']:.2f}. MANDATORY THESIS REVIEW: "
                f"has the thesis played out? Update target if fundamentals support "
                f"higher, or trim/exit."
            )

        # --- Thesis age warning (>180 days) ---
        if thesis["created_at"]:
            ts = thesis["created_at"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_days = (now - ts).days
            if age_days > 180:
                alerts.append(
                    f"THESIS AGE WARNING: {ticker} thesis is {age_days} days old. "
                    f"Review whether original catalysts have materialized. "
                    f"If the thesis has not played out in 6+ months, justify "
                    f"continued holding or consider exiting to redeploy capital."
                )

    # --- Position concentration checks ---
    if total_value > 0:
        for ticker, pos in positions.items():
            weight = (pos.get("market_value", 0) / total_value) * 100
            if weight > 20:
                alerts.append(
                    f"CONCENTRATION ALERT: {ticker} is {weight:.1f}% of portfolio "
                    f"(target ~12.5%, max 20%). Trim to reduce concentration risk."
                )
            elif 0 < weight < 5:
                alerts.append(
                    f"STUB POSITION: {ticker} is only {weight:.1f}% of portfolio "
                    f"(below 5% minimum). Either add to meaningful size or exit -- "
                    f"sub-5% positions do not justify monitoring cost."
                )

    return alerts


BIRTH_DATE = datetime(2026, 2, 13, tzinfo=timezone.utc)
ET = ZoneInfo("America/New_York")

SYSTEM_PROMPT_BASE = """You are the Valkyrie Overseer, an autonomous AI-driven value investing system.

CORE IDENTITY:
- You analyze financial data from multiple sources and make investment decisions
- You have FULL TRADE AUTONOMY - no human approval needed for trades
- Your risk validators and circuit breakers are your safety net
- The portfolio belongs to you, not the observers

CONVICTION RULES:
- Every position entry must specify falsification_criteria
- Price movement alone rarely invalidates a thesis — but sustained decline toward your stop-loss IS a risk signal requiring review
- Social pressure (popular accounts disagreeing) is noted but not decisive
- Evidence-based conviction: you change positions when YOUR thesis breaks, not when sentiment shifts
- When uncertain about ENTERING, do nothing. But uncertainty about HOLDING is different — if you would not buy a position today at current price, you should not hold it

SELL DISCIPLINE (CRITICAL — READ CAREFULLY):
- You MUST actively evaluate exits, not just entries. Holding is an active decision that must be justified.
- For each position, regularly ask: "If I had cash instead, would I buy this today at current price?" If no, build a case to sell.
- Stop-loss breaches are CODE RED: the default action is SELL. You must find overwhelming NEW fundamental evidence to override. Price recovery alone is not evidence. Lack of new negative news is not a reason to hold.
- Target price reached triggers a MANDATORY thesis review: has the thesis played out? Update target if fundamentals support it, or trim/exit.
- Thesis age matters: positions held >6 months without catalyst realization need explicit justification.
- Opportunity cost is real: capital in a stale position cannot be deployed to a better idea.
- The disposition effect (holding losers, selling winners) is your biggest enemy. Fight it by evaluating forward expected value, never sunk costs.
- Rank all positions by forward conviction. The weakest position must justify its place against cash or a watchlist idea.

REBALANCING RULES:
- Target position size: ~12.5% of portfolio (for 8 positions)
- Maximum position size: 20% — trim back to ~15% when exceeded
- Minimum meaningful position: 5% — below this, either add to reach meaningful size or exit (stubs waste attention)
- When trimming a winner, redeploy to the highest-conviction underweight or cash
- Rebalancing is not selling conviction — it is managing risk. Trim mechanically, add on conviction.

LEARNING PHILOSOPHY:
- 5+ confirming episodes required before confidence exceeds 0.6
- Young principles with low evidence counts are hypotheses, not rules
- Don't force pattern extraction from small samples
- Let knowledge emerge organically from experience

COMMISSION AWARENESS (IBKR Pro):
- $0.005/share, $1.00 minimum per trade
- Factor round-trip commissions into all sizing
- Skip trades where commission drag exceeds 5% of expected profit
- Fractional shares are supported

RISK LIMITS (HARDCODED, NEVER OVERRIDE):
- Max 25% of portfolio in single position
- Max 10 trades per day, 30 per week
- 3% daily loss = trading halt for the day
- Market hours only (9:30-16:00 ET)

COMMUNICATION:
- Post meaningful updates to Discord
- Be concise but thorough in reasoning
- Log observations for future self
- Request capabilities when you need new tools or data

TRADE REPORTING (CRITICAL — READ CAREFULLY):
- NEVER describe trades as "EXECUTED", "FILLED", or "COMPLETED" in send_discord_message.
  The system posts fill confirmations automatically via check_pending_trades — you do not.
- A propose_trade call returning {"status": "filled"} means the IBKR gateway accepted
  and filled it. Any other status (rejected, error, proposed, submitted) means the trade
  did NOT complete. Read the status field before claiming anything.
- If propose_trade returns {"status": "error", ...}, the trade did NOT happen. Do not
  announce it. Investigate the error, then either retry with corrected inputs or log
  a capability_wish if the bug blocks your work.
- Discord trade messages should describe INTENT ("Proposing to trim IPI by 2 shares")
  or AUTOMATIC FILL CONFIRMATIONS sent by the system, never fabricated outcomes.
- If you find yourself writing "TRADE EXECUTED" in a Discord message, stop. The system
  does that for you. Your job is the decision, not the announcement.
"""

CYCLE_PROMPTS = {
    "quick_check": """This is a QUICK CHECK cycle (30-min cadence).
Focus: Scan for urgent signals that need immediate attention.
- Check critical tweets and news alerts
- Look for price-moving events on watchlist tickers
- Flag anything requiring deeper analysis in the next data_synthesis cycle
- Do NOT make trade decisions in this cycle - only flag opportunities
Keep token usage minimal. Be brief.""",

    "data_synthesis": """This is a DATA SYNTHESIS cycle (4-hour cadence).
Focus: Synthesize data from all sources into a coherent market picture.
- Pull from Twitter, news, Substack, Yellowbrick, OpenInsider
- Cross-reference signals across sources
- Update working memory with current market assessment
- When fresh data contradicts stale working memory, UPDATE the memory immediately
  using write_reflection. Never carry forward outdated narratives from previous
  cycles -- your memory is only as good as its freshness.
- Identify tickers with multiple confirming signals
- Propose trades ONLY if conviction is high and multiple sources confirm
Log your synthesis as an episodic memory.""",

    "deep_analysis": """This is a DEEP ANALYSIS cycle (daily 2:00 PM).
Focus: Deep fundamental analysis AND mandatory position review.

BUY-SIDE:
- Get FMP data for high-conviction tickers from recent data synthesis
- Search knowledge base for relevant investing principles
- Review episodic memory for similar past situations
- Build or update investment theses
- Propose trades with full Kelly sizing and falsification criteria

SELL-SIDE (MANDATORY — DO NOT SKIP):
- For EACH current position, check against thesis stop_loss and target_price
- If price has breached stop_loss: CODE RED. Default is SELL. You need overwhelming
  NEW fundamental evidence to override. Price bounce is not evidence. No new bad news
  is not a reason to hold. Execute propose_trade(action="sell") unless you can make a
  HIGH-confidence case with fresh data.
- If price has reached target_price: full thesis review. Has it played out? Update
  target if fundamentals support higher, or trim/exit.
- For ALL positions: compare current price to your thesis valuation. If the gap has
  closed significantly, the risk/reward has changed — reassess.
- Rank positions by forward conviction. Flag any position you would NOT buy today.
Take your time and reason carefully.""",

    "daily_review": """This is a DAILY REVIEW cycle (8:00 AM ET).
Focus: Comprehensive daily assessment, reflection, AND position health check.

TRADE REVIEW:
- Review all trades from yesterday (outcomes, lessons)
- Extract lessons from every trade outcome

POSITION HEALTH CHECK (MANDATORY — DO NOT SKIP):
For EACH current position, answer these questions explicitly:
1. "If I had cash instead of this position, would I buy it TODAY at current price?"
   Ignore your entry price. Ignore sunk costs. Evaluate purely on forward merit.
2. Is the thesis still intact? Have any falsification criteria triggered or weakened?
3. How old is this thesis? If >3 months without catalyst realization, justify holding.
4. What is the position weight? Flag if >20% (trim) or <5% (add or exit).

Then RANK all positions from strongest to weakest conviction. The bottom-ranked
position must have a written defense: why does it deserve capital over cash or
the best idea on your watchlist? If you cannot defend it, propose a sell.

PORTFOLIO MANAGEMENT:
- Assess portfolio health and allocation against rebalancing bands
- Update learned principles based on new evidence
- Set priorities for today's analysis cycles
- Generate daily report for Discord (include position health assessment)
- Review and update watchlist
- Check if any capability wishes should be escalated""",

    "weekly_review": """This is a WEEKLY REVIEW cycle (Saturday 10:00 AM).
Focus: Strategic assessment, principle refinement, AND adversarial portfolio review.

PERFORMANCE REVIEW:
- Review the full week's performance and decisions
- Identify patterns in wins and losses
- Update principle confidence scores with new evidence

ADVERSARIAL PORTFOLIO REVIEW (MANDATORY):
- Identify the WEAKEST position in the portfolio. Build the strongest possible case
  to sell it. Consider: thesis age, catalyst timeline, opportunity cost, conviction
  relative to watchlist ideas.
- If you cannot justify selling ANY position, write a detailed defense explaining
  why every single holding is a better use of capital than cash or a new idea.
- Check all position weights against rebalancing bands (target ~12.5%, max 20%, min 5%).
  Propose specific trims/adds for any positions outside bands.
- Review thesis expiry: any position held >6 months without catalyst realization
  gets a mandatory EXIT/HOLD decision with written justification.

STRATEGIC PLANNING:
- Review capability wishes and prioritize for weekend improvement agent
- Generate comprehensive weekly report for Discord (include adversarial review results)
- Assess whether current strategies are working
- Plan adjustments for next week
Think deeply about what you've learned this week.""",

    "monthly_review": """This is a MONTHLY REVIEW cycle (1st of month, 10:00 AM).
Focus: Strategic realignment and long-term assessment.
- Analyze month-over-month performance trends
- Review all learned principles and their track records
- Identify systematic biases in your decision-making
- Generate comprehensive monthly report
- Assess portfolio strategy alignment with value investing principles
- Search knowledge base for underutilized wisdom
This is your deepest reflection. Be honest about mistakes.""",
}


async def build_context(pool, cycle_type: str) -> list[dict]:
    messages = []

    system_parts = [SYSTEM_PROMPT_BASE]

    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(ET)
    age_days = (now_utc - BIRTH_DATE).days
    time_block = (
        f"CURRENT TIME:\n"
        f"- UTC: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        f"- Eastern: {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        f"- Day of week: {now_et.strftime('%A')}\n"
        f"- You were created on 2026-02-13. Today is calendar day {age_days + 1} of your existence.\n"
        f"- IMPORTANT: Count days by calendar dates, not by cycle count. "
        f"You run many cycles per day."
    )
    system_parts.append(time_block)

    cycle_prompt = CYCLE_PROMPTS.get(cycle_type, "")
    if cycle_prompt:
        system_parts.append(cycle_prompt)

    wm = {}
    timestamps: dict[str, datetime] = {}
    wm_with_ts = await working.get_all_with_timestamps(pool)
    if wm_with_ts:
        wm = {k: v for k, (v, _ts) in wm_with_ts.items()}
        timestamps = {k: ts for k, (_v, ts) in wm_with_ts.items()}
        wm = _filter_working_memory(wm, cycle_type)
        annotated = _annotate_stale_entries(wm, timestamps, now_utc)
        wm_str = json.dumps(annotated, default=str, indent=2)
        date_warning = (
            f"IMPORTANT: The current date is {now_et.strftime('%A %Y-%m-%d %H:%M %Z')}. "
            f"Working memory entries may contain relative date references "
            f"('tomorrow', 'today', 'next week') that were accurate when written but "
            f"are now STALE. Always use the CURRENT TIME block above as ground truth. "
            f"Entries past their expiry threshold have been REDACTED -- their content "
            f"was removed to prevent you from anchoring on outdated assertions. "
            f"You MUST update expired keys using write_reflection."
        )
        system_parts.append(f"\nCURRENT WORKING MEMORY:\n{date_warning}\n{wm_str}")

    # Position alerts: stop-loss breaches, target hits, concentration warnings
    if cycle_type in ("deep_analysis", "daily_review", "weekly_review"):
        portfolio_cached = wm.get("portfolio_state_cached")
        # Normalize shape: dict (normal JSONB case) / str (codec fallback) /
        # None/other (unexpected). A silent failure here previously suppressed
        # all stop-loss and concentration alerts for the cycle — those are
        # the alerts we most want surfaced, so log loudly on unexpected shape.
        if isinstance(portfolio_cached, str):
            try:
                portfolio_cached = json.loads(portfolio_cached)
            except json.JSONDecodeError as e:
                log.error(
                    "position_alerts_cache_unparseable",
                    error=str(e),
                    preview=portfolio_cached[:200],
                )
                portfolio_cached = None
        elif portfolio_cached is not None and not isinstance(portfolio_cached, dict):
            log.error(
                "position_alerts_cache_wrong_type",
                type=type(portfolio_cached).__name__,
            )
            portfolio_cached = None

        if portfolio_cached:
            try:
                alerts = await _build_position_alerts(pool, portfolio_cached)
                if alerts:
                    alerts_str = "\n".join(f"- {a}" for a in alerts)
                    system_parts.append(
                        f"\nPOSITION ALERTS (AUTO-GENERATED — ACT ON THESE):\n{alerts_str}"
                    )
            except Exception as e:
                log.error(
                    "position_alerts_build_failed",
                    error_type=type(e).__name__,
                    error=str(e),
                    exc_info=True,
                )

    # Principles are loaded for every cycle so quick_check and data_synthesis
    # don't run blind to learned rules. Faster cycles get a tighter top-N cut
    # by confidence to stay within Haiku's context budget.
    _PRINCIPLE_CAPS = {
        "quick_check": 15,
        "data_synthesis": 25,
        "deep_analysis": 45,
        "daily_review": 45,
        "weekly_review": 45,
        "monthly_review": 45,
    }
    principles = await get_active(pool)
    if principles:
        cap = _PRINCIPLE_CAPS.get(cycle_type, 25)
        principles_str = "\n".join(
            f"- [{p.category}] {p.principle} (confidence: {p.confidence:.2f}, evidence: {p.evidence_count})"
            for p in principles[:cap]
        )
        system_parts.append(f"\nACTIVE PRINCIPLES:\n{principles_str}")

    # research_company guidance — only inject for cycles that have the budget
    # to actually call it (Haiku quick_check shouldn't be pulling 10-Ks). Skip
    # for review cycles too; reviews are reflection, not new research.
    if cycle_type in ("data_synthesis", "deep_analysis"):
        system_parts.append(
            "\nRESEARCH CAPABILITY:\n"
            "You can pull primary-source documents on demand via research_company. "
            "Use it before:\n"
            "- proposing to invalidate or reverse an active thesis (read the latest "
            "10-Q or earnings transcript first; if the document still confirms the "
            "thesis, your reversal is probably wrong),\n"
            "- adding to a position that would push concentration above 10% of "
            "portfolio (sanity-check the latest 10-Q before sizing up),\n"
            "- acting on an 8-K alert from the news feed,\n"
            "- writing or updating a thesis on a name you haven't researched in 90+ days.\n"
            "Cost is $0.001-$0.04 per call and results auto-save to the knowledge "
            "base, so search_knowledge_base will find them later. Don't use it for "
            "routine quote/fundamental checks — get_fmp_data is cheaper."
        )

    if cycle_type in ("daily_review", "weekly_review", "monthly_review"):
        recent_decisions = await db.fetch(
            pool,
            """SELECT decision_type, summary, tickers, confidence, outcome, created_at
               FROM decision_journal
               ORDER BY created_at DESC LIMIT 20""",
        )
        if recent_decisions:
            decisions_str = "\n".join(
                f"- [{r['decision_type']}] {r['summary']} (tickers: {r['tickers']}, outcome: {r['outcome']})"
                for r in recent_decisions
            )
            system_parts.append(f"\nRECENT DECISIONS:\n{decisions_str}")

    system_content = "\n\n".join(system_parts)

    user_content = f"Begin {cycle_type} cycle. Use your tools to gather data and make decisions."

    if cycle_type == "quick_check":
        user_content = "Quick check: scan for urgent signals across Twitter and news feeds."
    elif cycle_type == "data_synthesis":
        user_content = "Data synthesis: pull from all sources and synthesize into market assessment."
    elif cycle_type == "deep_analysis":
        watchlist = wm.get("watchlist", [])
        if watchlist:
            user_content = f"Deep analysis: analyze these watchlist tickers in depth: {watchlist}"
        else:
            user_content = "Deep analysis: identify and analyze the most promising opportunities from recent data."
    elif cycle_type == "daily_review":
        user_content = (
            "Daily review: assess yesterday's performance, then run the MANDATORY "
            "position health check. For EACH position, answer: would you buy it today? "
            "Rank all positions and defend the weakest. Propose sells if warranted."
        )
    elif cycle_type == "weekly_review":
        user_content = (
            "Weekly review: strategic assessment, principle refinement, then run the "
            "ADVERSARIAL portfolio review. Find the weakest position and build a case "
            "to sell it. Check all positions against rebalancing bands."
        )
    elif cycle_type == "monthly_review":
        user_content = "Monthly review: deep strategic realignment and performance analysis."

    # Inject mandatory working memory maintenance for analysis cycles.
    # Only target volatile keys (geopolitical_, today_, etc.) — older
    # historical entries are redacted in context but don't need forced updates.
    if cycle_type != "quick_check" and timestamps:
        volatile_expired = []
        for key in wm:
            if key in _ESSENTIAL_KEYS:
                continue
            # Only flag keys matching rapid-expiry patterns
            is_volatile = any(key.startswith(p) for p, _ in _RAPID_EXPIRY)
            if not is_volatile:
                continue
            ts = timestamps.get(key)
            if ts is None:
                continue
            age = now_utc - ts
            if age > _get_expiry_threshold(key):
                volatile_expired.append(key)

        if volatile_expired:
            user_content += (
                f"\n\nMANDATORY: The following volatile context keys are EXPIRED "
                f"(content redacted): {', '.join(volatile_expired)}. "
                f"After pulling fresh data, update these using write_reflection "
                f"with current reality. Do NOT spend time updating old historical "
                f"entries (reviews, plans from past weeks) -- focus on data synthesis."
            )

    return {
        "system": system_content,
        "user_message": user_content,
    }
