from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from uuid import UUID

import asyncpg
import structlog

from overseer.config import OverseerSettings

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None
_pool_lock: asyncio.Lock = asyncio.Lock()


def _jsonb_encoder(obj):
    """JSON encoder that handles datetime, UUID, and other common types."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json_dumps(value):
    return json.dumps(value, default=_jsonb_encoder)


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Initialize each connection with JSONB codec and pgvector support."""
    await conn.set_type_codec(
        "jsonb",
        encoder=_json_dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    from pgvector.asyncpg import register_vector
    await register_vector(conn)


async def get_pool(settings: OverseerSettings) -> asyncpg.Pool:
    global _pool
    # Double-checked locking: fast path without the lock when pool is ready,
    # serialized creation path so two concurrent startup coroutines don't
    # both create a pool (the loser would leak forever with no close path).
    if _pool is not None and not _pool._closed:
        return _pool
    async with _pool_lock:
        if _pool is not None and not _pool._closed:
            return _pool
        _pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password or None,
            min_size=2,
            max_size=10,
            command_timeout=30,
            init=_init_connection,
        )
        log.info("database_pool_created", host=settings.db_host, db=settings.db_name)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None and not _pool._closed:
        await _pool.close()
        log.info("database_pool_closed")
        _pool = None


async def execute(pool: asyncpg.Pool, query: str, *args) -> str:
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def fetch(pool: asyncpg.Pool, query: str, *args) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(pool: asyncpg.Pool, query: str, *args) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def fetchval(pool: asyncpg.Pool, query: str, *args):
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args)


async def bootstrap_schema(pool: asyncpg.Pool) -> None:
    """Idempotent schema setup for tables managed by overseer at startup.

    - `trade_counters`: held outside working_memory so the daily/weekly trade
      caps can't be silently disabled by a NULL→0 fallback in the KV reader.
    - `document_cache`: raw filing/transcript text for research_company tool.
      Keyed on (ticker, source_type, period_key); avoids re-fetching FMP/EDGAR.
    - knowledge_base column extensions: lets ingest tag rows with ticker, doc
      type, confidence, importance, stale_after, findings — so future searches
      can filter out low-quality or outdated auto-summaries.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_counters (
                name          TEXT PRIMARY KEY,
                count         INTEGER NOT NULL DEFAULT 0,
                period_start  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            INSERT INTO trade_counters (name)
            VALUES ('daily'), ('weekly')
            ON CONFLICT (name) DO NOTHING
            """
        )
        await conn.execute(
            """
            DELETE FROM working_memory
            WHERE key IN ('daily_trade_count', 'weekly_trade_count')
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_cache (
                id              BIGSERIAL PRIMARY KEY,
                ticker          TEXT NOT NULL,
                source_type     TEXT NOT NULL,
                period_key      TEXT NOT NULL,
                accession_no    TEXT,
                filed_at        DATE,
                fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                raw_text        TEXT NOT NULL,
                raw_token_count INTEGER,
                source_url      TEXT,
                fmp_meta        JSONB DEFAULT '{}'::jsonb,
                UNIQUE (ticker, source_type, period_key)
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_document_cache_ticker ON document_cache(ticker, fetched_at DESC)"
        )

        await conn.execute(
            """
            ALTER TABLE knowledge_base
                ADD COLUMN IF NOT EXISTS source_doc_ref BIGINT REFERENCES document_cache(id),
                ADD COLUMN IF NOT EXISTS doc_type       TEXT,
                ADD COLUMN IF NOT EXISTS ticker         TEXT,
                ADD COLUMN IF NOT EXISTS confidence     REAL,
                ADD COLUMN IF NOT EXISTS importance     REAL DEFAULT 0.5,
                ADD COLUMN IF NOT EXISTS stale_after    DATE,
                ADD COLUMN IF NOT EXISTS findings       JSONB
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_kb_ticker_doctype ON knowledge_base(ticker, doc_type) WHERE ticker IS NOT NULL"
        )
    log.info("schema_bootstrapped", tables=["trade_counters", "document_cache", "knowledge_base+cols"])
