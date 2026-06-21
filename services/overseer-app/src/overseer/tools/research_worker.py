"""On-demand company research via isolated worker LLM.

Pulls a single SEC filing or earnings transcript, hands it to a cheap
single-shot worker model selected per source type, and returns a 500-word
structured summary plus extracted findings. Raw documents NEVER enter the
main agent's context — that's the whole point of the isolation pattern.

Trigger conditions are wired by the caller (currently only manual via the
research_company tool; auto-triggers from propose_trade are a future phase).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any

import httpx
import structlog

from overseer.config import OverseerSettings
from overseer.core.openrouter_client import OpenRouterClient
from overseer.utils import database as db

log = structlog.get_logger()

FMP_BASE = "https://financialmodelingprep.com/stable"
EDGAR_USER_AGENT = "Valhalla Capital research@valhalla.local"
HTTP_TIMEOUT = 60.0
MAX_INPUT_TOKENS = 150_000  # truncate raw_text before sending to non-grok models

# Model routing per source type. Pricing verified on OpenRouter 2026-05-06.
# 10-K is the only one routed to grok-4.1-fast (2M ctx) because full 10-Ks
# regularly exceed 200k tokens. Smaller doc types route to cheaper models.
_SOURCE_TYPE_MODEL: dict[str, str] = {
    "10-K": "x-ai/grok-4.1-fast",
    "10-Q": "qwen/qwen-plus-2025-07-28",
    "8-K": "google/gemini-2.5-flash-lite",
    "DEF 14A": "qwen/qwen-plus-2025-07-28",
    "earnings_transcript": "deepseek/deepseek-v3.2",
}

# Stale-after defaults (days). Filed at search time, not deletion — so a
# manual override can still surface the row.
_STALE_AFTER_DAYS: dict[str, int] = {
    "10-K": 730,
    "10-Q": 365,
    "8-K": 90,
    "DEF 14A": 365,
    "earnings_transcript": 180,
}

WORKER_SYSTEM_PROMPT = """\
You are a forensic financial-document reader for a value-investing agent.
You receive ONE document (a SEC filing or earnings transcript) and a `focus`
directive. You produce ONE 500-word structured markdown summary and a
machine-readable findings JSON. You are NOT the trading agent. You do NOT
recommend trades. You report what the document says, with quantitative deltas
vs the comparable prior period when the document supplies them.

Hard rules:
1. Never invent numbers — if a metric isn't in the document, write null.
2. Use prior-period numbers from the document itself; do not recall outside knowledge.
3. Flag forward-looking guidance separately from results.
4. If the document contradicts a common thesis pattern (moat erosion, customer
   concentration, accounting change, going-concern language), say so explicitly
   in red_flags.
5. confidence is your self-rated extraction quality 0-1. Sub-0.6 means
   downstream should NOT trust the findings.

Output format — exactly these sections, in this order:

## Headline (≤30 words)
## Thesis Impact (confirms / weakens / neutral, with one-sentence why)
## Financial Deltas (FCF, gross margin, op margin, revenue mix, leverage — YoY/QoQ)
## Guidance Changes (raised / lowered / withdrawn / unchanged, with magnitude)
## Capital Allocation (buybacks, dividends, M&A, capex)
## Red Flags (≥0 bullets — going-concern, auditor change, related-party,
   restated numbers, customer/supplier concentration)
## Verbatim Quotes (≤3 short quotes that load-bear the above)

Then a fenced ```json``` block with the findings object:
{
  "thesis_impact": "confirms" | "weakens" | "neutral",
  "fcf_delta_pct": number | null,
  "gross_margin_delta_bps": number | null,
  "op_margin_delta_bps": number | null,
  "revenue_growth_pct": number | null,
  "guidance_change": string | null,
  "red_flags": [string, ...],
  "confidence": number  // 0..1
}
"""


# ---------------------------------------------------------------------------
# Source fetchers
# ---------------------------------------------------------------------------

async def _fetch_fmp_filings_index(
    settings: OverseerSettings, ticker: str, filing_type: str, limit: int = 8
) -> list[dict]:
    """FMP returns the filings INDEX (URLs, accession numbers, dates) — not
    the actual 10-K body. We then fetch the body from EDGAR separately.

    The endpoint requires `from`/`to` date params and ignores `type` server-side,
    so we pull a broad window and filter client-side by `formType`."""
    url = f"{FMP_BASE}/sec-filings-search/symbol"
    today = date.today()
    params = {
        "symbol": ticker.upper(),
        "from": (today - timedelta(days=730)).isoformat(),
        "to": today.isoformat(),
        "apikey": settings.fmp_api_key,
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return []
        target = filing_type.upper()
        matches = [f for f in data if (f.get("formType") or "").upper() == target]
        # FMP returns most-recent first already; preserve that ordering.
        return matches[:limit]


async def _fetch_edgar_body(filing_url: str) -> str:
    """Pull the filing HTML from EDGAR and strip to plain text.

    EDGAR returns 403 without a real User-Agent and rate-limits at 10 req/s.
    We're well below that on a single-developer cadence."""
    from bs4 import BeautifulSoup  # local import: heavy + only needed here

    async with httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": EDGAR_USER_AGENT, "Accept-Encoding": "gzip"},
        follow_redirects=True,
    ) as client:
        resp = await client.get(filing_url)
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "lxml")
    # XBRL tags and inline-stylesheet noise pollute .get_text() — strip first.
    for tag in soup(["script", "style", "ix:header", "ix:hidden"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Collapse runs of blank lines that BeautifulSoup leaves behind
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


async def _fetch_fmp_transcript(
    settings: OverseerSettings,
    ticker: str,
    year: int | None,
    quarter: int | None,
) -> dict | None:
    """FMP returns the full transcript text directly — no EDGAR step needed."""
    url = f"{FMP_BASE}/earning-call-transcript"
    params: dict[str, Any] = {"symbol": ticker.upper(), "apikey": settings.fmp_api_key}
    if year is not None:
        params["year"] = year
    if quarter is not None:
        params["quarter"] = quarter
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0]
        return None


async def _fetch_source(
    settings: OverseerSettings,
    ticker: str,
    source_type: str,
    period: str | None,
) -> dict | None:
    """Resolve (source_type, period) → {raw_text, period_key, accession_no,
    filed_at, source_url, fmp_meta}. Returns None on miss."""
    if source_type == "earnings_transcript":
        year = quarter = None
        if period:
            m = re.match(r"^(\d{4})(?:-?Q([1-4]))?$", period)
            if m:
                year = int(m.group(1))
                if m.group(2):
                    quarter = int(m.group(2))
        t = await _fetch_fmp_transcript(settings, ticker, year, quarter)
        if not t:
            return None
        raw_text = t.get("content") or ""
        if len(raw_text) < 500:
            return None
        period_key = f"{t.get('year')}-Q{t.get('quarter')}"
        return {
            "raw_text": raw_text,
            "period_key": period_key,
            "accession_no": None,
            "filed_at": t.get("date"),
            "source_url": None,
            "fmp_meta": {k: v for k, v in t.items() if k != "content"},
        }

    # SEC filings — pull the index, find the right one, then EDGAR-fetch the body
    filings = await _fetch_fmp_filings_index(settings, ticker, source_type, limit=8)
    if not filings:
        return None

    chosen: dict | None = None
    if period:
        for f in filings:
            # Match either YYYY-MM-DD prefix or year/quarter
            filed = (f.get("filingDate") or "")[:10]
            if filed.startswith(period[:10]) or period in filed:
                chosen = f
                break
    if chosen is None:
        chosen = filings[0]  # most recent

    # Prefer `link` (the index page with all exhibits) over `finalLink`
    # (a single embedded XML/document) so BeautifulSoup gets readable HTML.
    filing_url = chosen.get("link") or chosen.get("finalLink") or chosen.get("url")
    if not filing_url:
        return None

    try:
        raw_text = await _fetch_edgar_body(filing_url)
    except Exception as e:
        log.error("edgar_fetch_failed", url=filing_url, error=str(e))
        return None

    if len(raw_text) < 1000:
        # Plan F8: don't cache a near-empty fetch — likely a transient EDGAR error.
        log.warning("filing_body_too_short", url=filing_url, length=len(raw_text))
        return None

    filed_at = (chosen.get("filingDate") or "")[:10] or None
    period_key = filed_at or "unknown"
    return {
        "raw_text": raw_text,
        "period_key": period_key,
        "accession_no": chosen.get("accessionNumber") or chosen.get("accession_no"),
        "filed_at": filed_at,
        "source_url": filing_url,
        "fmp_meta": chosen,
    }


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

async def _cache_lookup(
    pool, ticker: str, source_type: str, period_key: str
) -> dict | None:
    row = await db.fetchrow(
        pool,
        """SELECT id, ticker, source_type, period_key, accession_no, filed_at,
                  fetched_at, raw_text, raw_token_count, source_url, fmp_meta
           FROM document_cache
           WHERE ticker = $1 AND source_type = $2 AND period_key = $3""",
        ticker.upper(),
        source_type,
        period_key,
    )
    return dict(row) if row else None


async def _cache_insert(
    pool,
    ticker: str,
    source_type: str,
    period_key: str,
    raw_text: str,
    accession_no: str | None,
    filed_at: str | None,
    source_url: str | None,
    fmp_meta: dict,
) -> int:
    # Rough token count: ~4 chars/token. Avoids importing tiktoken.
    raw_token_count = max(1, len(raw_text) // 4)
    filed_at_date: date | None = None
    if filed_at:
        try:
            filed_at_date = datetime.strptime(filed_at[:10], "%Y-%m-%d").date()
        except ValueError:
            filed_at_date = None
    return await db.fetchval(
        pool,
        """INSERT INTO document_cache (
              ticker, source_type, period_key, accession_no, filed_at,
              raw_text, raw_token_count, source_url, fmp_meta
           ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
           ON CONFLICT (ticker, source_type, period_key) DO UPDATE
              SET raw_text = EXCLUDED.raw_text,
                  raw_token_count = EXCLUDED.raw_token_count,
                  fetched_at = NOW(),
                  fmp_meta = EXCLUDED.fmp_meta
           RETURNING id""",
        ticker.upper(),
        source_type,
        period_key,
        accession_no,
        filed_at_date,
        raw_text,
        raw_token_count,
        source_url,
        fmp_meta,
    )


# ---------------------------------------------------------------------------
# Worker call
# ---------------------------------------------------------------------------

def _truncate_for_model(raw_text: str, model: str) -> tuple[str, list[str]]:
    """Cap text to MAX_INPUT_TOKENS for non-grok models.

    Truncate from the END (financial statements live in the front half of
    SEC filings), not the front. Returns (text, warnings)."""
    warnings: list[str] = []
    if model.startswith("x-ai/grok"):
        return raw_text, warnings  # 2M ctx, no truncation needed
    max_chars = MAX_INPUT_TOKENS * 4
    if len(raw_text) > max_chars:
        warnings.append(f"truncated_to_{MAX_INPUT_TOKENS}_tokens")
        return raw_text[:max_chars], warnings
    return raw_text, warnings


def _parse_worker_output(text: str) -> tuple[str, dict | None]:
    """Split the worker response into (markdown_summary, findings_dict).

    Findings is the trailing fenced ```json``` block. If parsing fails, return
    (full_text, None) and let the caller decide (rule F1: confidence<0.6 OR
    findings=None → cache only, no KB write)."""
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        return text.strip(), None
    summary = text[: m.start()].strip()
    try:
        findings = json.loads(m.group(1))
    except json.JSONDecodeError:
        return text.strip(), None
    return summary, findings


async def _run_worker(
    settings: OverseerSettings,
    model: str,
    raw_text: str,
    ticker: str,
    source_type: str,
    period_key: str,
    focus: str,
) -> tuple[str, dict | None, dict]:
    """Single-shot OpenRouter call. No tools, no agent loop."""
    text_in, warnings = _truncate_for_model(raw_text, model)
    user_msg = (
        f"Ticker: {ticker}\n"
        f"Source: {source_type} ({period_key})\n"
        f"Focus: {focus}\n\n"
        f"--- DOCUMENT ---\n{text_in}\n--- END DOCUMENT ---"
    )

    client = OpenRouterClient(api_key=settings.openrouter_api_key)
    try:
        resp = await client.messages.create(
            model=model,
            max_tokens=2000,
            system=WORKER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
    finally:
        await client.messages.close()

    text_out = ""
    for block in resp.content:
        if hasattr(block, "text") and block.text:
            text_out += block.text

    summary, findings = _parse_worker_output(text_out)
    usage_meta = {
        "model_used": model,
        "tokens_in": resp.usage.input_tokens,
        "tokens_out": resp.usage.output_tokens,
        "cost_usd": resp.usage.openrouter_cost_usd,
        "warnings": warnings,
    }
    return summary, findings, usage_meta


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def run_research(
    pool,
    settings: OverseerSettings,
    ticker: str,
    source_type: str,
    focus: str,
    period: str | None = None,
    triggered_by: str = "manual",
) -> dict:
    """End-to-end: fetch source → cache → worker → optional KB write.

    Returns a dict shaped per the Phase 3 plan section A. Never raises on
    expected misses (FMP empty, EDGAR 4xx, parse failures); raises only on
    truly-unexpected DB errors."""
    if source_type not in _SOURCE_TYPE_MODEL:
        return {"status": "fetch_failed", "reason": f"Unsupported source_type: {source_type}"}

    ticker_u = ticker.upper()
    fetched = await _fetch_source(settings, ticker_u, source_type, period)
    if fetched is None:
        return {
            "status": "fetch_failed",
            "ticker": ticker_u,
            "source_type": source_type,
            "reason": "FMP/EDGAR returned no document for the requested period.",
        }

    period_key = fetched["period_key"]

    # Cache lookup — same period_key means we already have the raw text and
    # likely also a KB row from a prior run.
    cache_hit_row = await _cache_lookup(pool, ticker_u, source_type, period_key)
    if cache_hit_row:
        # If a KB row also exists, return that summary; otherwise re-run worker
        # on the cached raw_text (rare, but possible if a prior worker failed).
        kb_row = await db.fetchrow(
            pool,
            """SELECT id, content, findings, confidence
               FROM knowledge_base
               WHERE source_doc_ref = $1 AND doc_type = 'company_research'
               ORDER BY created_at DESC LIMIT 1""",
            cache_hit_row["id"],
        )
        if kb_row and kb_row["confidence"] is not None and kb_row["confidence"] >= 0.6:
            return {
                "status": "cache_hit",
                "ticker": ticker_u,
                "source_type": source_type,
                "period": period_key,
                "filed_at": cache_hit_row["filed_at"],
                "document_cache_id": cache_hit_row["id"],
                "knowledge_base_id": kb_row["id"],
                "summary_markdown": kb_row["content"],
                "findings": kb_row["findings"],
                "model_used": "cache",
                "cost_usd": 0.0,
                "warnings": [],
            }
        document_cache_id = cache_hit_row["id"]
        raw_text = cache_hit_row["raw_text"]
    else:
        document_cache_id = await _cache_insert(
            pool,
            ticker_u,
            source_type,
            period_key,
            fetched["raw_text"],
            fetched.get("accession_no"),
            fetched.get("filed_at"),
            fetched.get("source_url"),
            fetched.get("fmp_meta") or {},
        )
        raw_text = fetched["raw_text"]

    model = _SOURCE_TYPE_MODEL[source_type]
    try:
        summary, findings, usage_meta = await _run_worker(
            settings, model, raw_text, ticker_u, source_type, period_key, focus
        )
    except Exception as e:
        log.error("research_worker_failed", ticker=ticker_u, error=str(e))
        return {
            "status": "fetch_failed",
            "ticker": ticker_u,
            "source_type": source_type,
            "period": period_key,
            "document_cache_id": document_cache_id,
            "reason": f"Worker call failed: {e}",
        }

    confidence = (findings or {}).get("confidence", 0.0)
    if findings is None or confidence < 0.6:
        # Rule F1: cache stays, but KB does NOT — surface the summary once,
        # don't pollute future search_knowledge_base retrievals.
        return {
            "status": "below_quality",
            "ticker": ticker_u,
            "source_type": source_type,
            "period": period_key,
            "filed_at": fetched.get("filed_at"),
            "document_cache_id": document_cache_id,
            "knowledge_base_id": None,
            "summary_markdown": summary,
            "findings": findings,
            "model_used": usage_meta["model_used"],
            "cost_usd": usage_meta["cost_usd"],
            "tokens_in": usage_meta["tokens_in"],
            "tokens_out": usage_meta["tokens_out"],
            "warnings": usage_meta["warnings"]
            + (["low_confidence_findings"] if findings else ["findings_parse_failed"]),
        }

    # Compute derived importance per plan section F4.
    has_red_flags = bool((findings or {}).get("red_flags"))
    thesis_impact = (findings or {}).get("thesis_impact") or "neutral"
    has_guidance = bool((findings or {}).get("guidance_change"))
    importance = min(
        1.0,
        0.4
        + (0.3 if has_red_flags else 0.0)
        + (0.2 if thesis_impact != "neutral" else 0.0)
        + (0.1 if has_guidance else 0.0),
    )

    stale_days = _STALE_AFTER_DAYS.get(source_type, 365)
    stale_after = (datetime.utcnow() + timedelta(days=stale_days)).date()

    from overseer.memory.knowledge_base import ingest as kb_ingest

    kb_id = await kb_ingest(
        pool=pool,
        ticker=ticker_u,
        doc_type="company_research",
        content=summary,
        findings=findings,
        source_doc_ref=document_cache_id,
        source_file=f"{ticker_u}/{source_type}/{period_key}",
        confidence=float(confidence),
        importance=float(importance),
        stale_after=stale_after,
    )

    log.info(
        "research_complete",
        ticker=ticker_u,
        source_type=source_type,
        period=period_key,
        confidence=confidence,
        importance=importance,
        kb_id=kb_id,
        triggered_by=triggered_by,
        cost_usd=usage_meta["cost_usd"],
    )

    return {
        "status": "ok",
        "ticker": ticker_u,
        "source_type": source_type,
        "period": period_key,
        "filed_at": fetched.get("filed_at"),
        "document_cache_id": document_cache_id,
        "knowledge_base_id": kb_id,
        "summary_markdown": summary,
        "findings": findings,
        "model_used": usage_meta["model_used"],
        "cost_usd": usage_meta["cost_usd"],
        "tokens_in": usage_meta["tokens_in"],
        "tokens_out": usage_meta["tokens_out"],
        "warnings": usage_meta["warnings"],
    }
