from __future__ import annotations

import asyncpg
import structlog
from typing import Any

from overseer.models.memory import EpisodicMemory, MemorySearchResult
from overseer.memory.embeddings import get_embedding

log = structlog.get_logger()


async def create(pool: asyncpg.Pool, memory: EpisodicMemory) -> int:
    try:
        embedding = get_embedding(memory.summary)

        async with pool.acquire() as conn:
            memory_id = await conn.fetchval(
                """
                INSERT INTO episodic_memory (
                    event_type, summary, details, tickers, tags, importance,
                    embedding, trade_id, outcome, outcome_details, lesson_extracted,
                    linked_principle_id
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7::vector, $8, $9, $10, $11, $12)
                RETURNING id
                """,
                memory.event_type,
                memory.summary,
                memory.details,
                memory.tickers,
                memory.tags,
                memory.importance,
                embedding,
                memory.trade_id,
                memory.outcome,
                memory.outcome_details,
                memory.lesson_extracted,
                memory.linked_principle_id
            )

            log.info(
                "episodic_memory_created",
                id=memory_id,
                event_type=memory.event_type,
                tickers=memory.tickers
            )
            return memory_id
    except Exception as e:
        log.error("episodic_memory_create_failed", error=str(e), event_type=memory.event_type)
        raise


async def search_semantic(
    pool: asyncpg.Pool,
    query: str,
    top_k: int = 5
) -> list[MemorySearchResult]:
    try:
        query_embedding = get_embedding(query)

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    summary AS content,
                    event_type,
                    tickers,
                    tags,
                    importance,
                    details,
                    created_at,
                    (1 - (embedding <=> $1::vector)) AS similarity_score
                FROM episodic_memory
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                query_embedding,
                top_k
            )

            results = [
                MemorySearchResult(
                    content=row["content"],
                    source=f"episodic:{row['event_type']}",
                    similarity_score=float(row["similarity_score"]),
                    metadata={
                        "event_type": row["event_type"],
                        "tickers": row["tickers"],
                        "tags": row["tags"],
                        "importance": float(row["importance"]),
                        "created_at": row["created_at"].isoformat(),
                        "details": row["details"]
                    }
                )
                for row in rows
            ]

            log.debug("episodic_semantic_search", query=query, results=len(results))
            return results
    except Exception as e:
        log.error("episodic_semantic_search_failed", error=str(e), query=query, exc_info=True)
        raise


async def search_by_tickers(
    pool: asyncpg.Pool,
    tickers: list[str],
    limit: int = 20
) -> list[EpisodicMemory]:
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM episodic_memory
                WHERE tickers && $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                tickers,
                limit
            )

            results = [_row_to_memory(row) for row in rows]
            log.debug("episodic_ticker_search", tickers=tickers, results=len(results))
            return results
    except Exception as e:
        log.error("episodic_ticker_search_failed", error=str(e), tickers=tickers, exc_info=True)
        raise


async def search_by_tags(
    pool: asyncpg.Pool,
    tags: list[str],
    limit: int = 20
) -> list[EpisodicMemory]:
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM episodic_memory
                WHERE tags && $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                tags,
                limit
            )

            results = [_row_to_memory(row) for row in rows]
            log.debug("episodic_tag_search", tags=tags, results=len(results))
            return results
    except Exception as e:
        log.error("episodic_tag_search_failed", error=str(e), tags=tags, exc_info=True)
        raise


async def get_recent(
    pool: asyncpg.Pool,
    limit: int = 20,
    event_type: str | None = None
) -> list[EpisodicMemory]:
    try:
        async with pool.acquire() as conn:
            if event_type:
                rows = await conn.fetch(
                    """
                    SELECT *
                    FROM episodic_memory
                    WHERE event_type = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    event_type,
                    limit
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT *
                    FROM episodic_memory
                    ORDER BY created_at DESC
                    LIMIT $1
                    """,
                    limit
                )

            results = [_row_to_memory(row) for row in rows]
            log.debug("episodic_recent_search", event_type=event_type, results=len(results))
            return results
    except Exception as e:
        log.error("episodic_recent_search_failed", error=str(e), event_type=event_type, exc_info=True)
        raise


async def update_outcome(
    pool: asyncpg.Pool,
    id: int,
    outcome: str,
    outcome_details: dict[str, Any] | None = None
) -> None:
    try:
        async with pool.acquire() as conn:
            # asyncpg returns "UPDATE <n>" as the command tag; check row count
            # so a nonexistent id raises instead of silently recording "updated".
            tag = await conn.execute(
                """
                UPDATE episodic_memory
                SET outcome = $2, outcome_details = $3
                WHERE id = $1
                """,
                id,
                outcome,
                outcome_details
            )
            rows_affected = int(tag.split()[-1]) if tag.startswith("UPDATE ") else 0
            if rows_affected == 0:
                raise ValueError(f"Episodic memory id={id} not found — no row updated")
            log.info("episodic_outcome_updated", id=id, outcome=outcome)
    except Exception as e:
        log.error("episodic_update_outcome_failed", error=str(e), id=id)
        raise


def _row_to_memory(row: asyncpg.Record) -> EpisodicMemory:
    return EpisodicMemory(
        id=row["id"],
        created_at=row["created_at"],
        event_type=row["event_type"],
        summary=row["summary"],
        details=row["details"] or {},
        tickers=row["tickers"] or [],
        tags=row["tags"] or [],
        importance=float(row["importance"]),
        embedding=None,
        trade_id=row["trade_id"],
        outcome=row["outcome"],
        outcome_details=row["outcome_details"],
        lesson_extracted=row["lesson_extracted"],
        linked_principle_id=row["linked_principle_id"]
    )
