from __future__ import annotations

from datetime import date
from typing import Any

import asyncpg
import structlog

from overseer.models.memory import MemorySearchResult
from overseer.memory.embeddings import get_embedding

log = structlog.get_logger()


async def search(
    pool: asyncpg.Pool,
    query: str,
    top_k: int = 5,
    ticker: str | None = None,
) -> list[MemorySearchResult]:
    """Semantic search over knowledge_base.

    Filters out rows that have aged past `stale_after` or whose `confidence`
    fell below the 0.6 quality bar — both set at ingest time by the research
    worker for company-research summaries. Pre-loaded principle rows have
    NULL on both columns and pass through unchanged.

    `ticker` arg short-circuits the all-MiniLM embedding model's weak
    ticker-keyed recall by adding a hard SQL filter. Use it when the query is
    unambiguously about one company."""
    try:
        query_embedding = get_embedding(query)
        params: list[Any] = [query_embedding, top_k]
        ticker_predicate = ""
        if ticker:
            params.append(ticker.upper())
            ticker_predicate = f"AND (ticker IS NULL OR ticker = ${len(params)})"

        sql = f"""
            SELECT
                id,
                content,
                source_file,
                chunk_index,
                metadata,
                ticker,
                doc_type,
                confidence,
                importance,
                (1 - (embedding <=> $1::vector)) AS similarity_score
            FROM knowledge_base
            WHERE
                (stale_after IS NULL OR stale_after > CURRENT_DATE)
                AND (confidence IS NULL OR confidence >= 0.6)
                {ticker_predicate}
            ORDER BY embedding <=> $1::vector
            LIMIT $2
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

            results: list[MemorySearchResult] = []
            for row in rows:
                meta = dict(row["metadata"] or {})
                if row["ticker"]:
                    meta.setdefault("ticker", row["ticker"])
                if row["doc_type"]:
                    meta.setdefault("doc_type", row["doc_type"])
                if row["confidence"] is not None:
                    meta.setdefault("confidence", float(row["confidence"]))
                if row["importance"] is not None:
                    meta.setdefault("importance", float(row["importance"]))
                results.append(
                    MemorySearchResult(
                        content=row["content"],
                        source=f"kb:{row['source_file']}#{row['chunk_index']}",
                        similarity_score=float(row["similarity_score"]),
                        metadata=meta,
                    )
                )

            log.debug("knowledge_base_search", query=query, ticker=ticker, results=len(results))
            return results
    except Exception as e:
        log.error("knowledge_base_search_failed", error=str(e), query=query, exc_info=True)
        raise


async def ingest(
    pool: asyncpg.Pool,
    ticker: str,
    doc_type: str,
    content: str,
    findings: dict | None,
    source_doc_ref: int | None,
    source_file: str,
    confidence: float,
    importance: float,
    stale_after: date | None,
) -> int:
    """Persist a research summary as a searchable KB row.

    Embeds the markdown summary and stores findings as JSONB. Re-ingesting
    the same `source_file` updates the row in place — keeps re-runs idempotent
    without duplicating embeddings."""
    embedding = get_embedding(content)
    metadata = {"findings": findings or {}}

    async with pool.acquire() as conn:
        kb_id = await conn.fetchval(
            """
            INSERT INTO knowledge_base (
                source_file, chunk_index, content, embedding, metadata,
                ticker, doc_type, confidence, importance, stale_after,
                findings, source_doc_ref
            ) VALUES ($1, 0, $2, $3::vector, $4,
                      $5, $6, $7, $8, $9,
                      $10, $11)
            ON CONFLICT (source_file, chunk_index) DO UPDATE SET
                content       = EXCLUDED.content,
                embedding     = EXCLUDED.embedding,
                metadata      = EXCLUDED.metadata,
                ticker        = EXCLUDED.ticker,
                doc_type      = EXCLUDED.doc_type,
                confidence    = EXCLUDED.confidence,
                importance    = EXCLUDED.importance,
                stale_after   = EXCLUDED.stale_after,
                findings      = EXCLUDED.findings,
                source_doc_ref= EXCLUDED.source_doc_ref
            RETURNING id
            """,
            source_file,
            content,
            embedding,
            metadata,
            ticker.upper(),
            doc_type,
            confidence,
            importance,
            stale_after,
            findings,
            source_doc_ref,
        )

    log.info(
        "knowledge_base_ingested",
        ticker=ticker,
        doc_type=doc_type,
        confidence=confidence,
        importance=importance,
        kb_id=kb_id,
    )
    return kb_id
