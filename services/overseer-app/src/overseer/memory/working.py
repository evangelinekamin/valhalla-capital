from __future__ import annotations

import asyncpg
import structlog
from typing import Any

log = structlog.get_logger()


async def get(pool: asyncpg.Pool, key: str) -> Any:
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM working_memory WHERE key = $1",
                key
            )
            if row is None:
                log.warning("working_memory_key_not_found", key=key)
                return None
            return row["value"]
    except Exception as e:
        log.error("working_memory_get_failed", key=key, error=str(e))
        raise


async def set(pool: asyncpg.Pool, key: str, value: Any) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO working_memory (key, value, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (key)
                DO UPDATE SET value = $2, updated_at = NOW()
                """,
                key,
                value
            )
            log.debug("working_memory_set", key=key)
    except Exception as e:
        log.error("working_memory_set_failed", key=key, error=str(e))
        raise


async def get_all(pool: asyncpg.Pool) -> dict[str, Any]:
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT key, value FROM working_memory")
            return {row["key"]: row["value"] for row in rows}
    except Exception as e:
        log.error("working_memory_get_all_failed", error=str(e))
        raise


async def get_all_with_timestamps(pool: asyncpg.Pool) -> dict[str, tuple[Any, Any]]:
    """Return all entries as {key: (value, updated_at)} for staleness annotation."""
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT key, value, updated_at FROM working_memory"
            )
            return {row["key"]: (row["value"], row["updated_at"]) for row in rows}
    except Exception as e:
        log.error("working_memory_get_all_with_timestamps_failed", error=str(e))
        raise


async def delete(pool: asyncpg.Pool, key: str) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM working_memory WHERE key = $1", key)
            log.debug("working_memory_deleted", key=key)
    except Exception as e:
        log.error("working_memory_delete_failed", key=key, error=str(e))
        raise
