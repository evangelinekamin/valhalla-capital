from __future__ import annotations

import asyncpg
import structlog

from overseer.models.memory import LearnedPrinciple

log = structlog.get_logger()


async def create(pool: asyncpg.Pool, principle: LearnedPrinciple) -> int:
    try:
        async with pool.acquire() as conn:
            principle_id = await conn.fetchval(
                """
                INSERT INTO learned_principles (
                    category, principle, confidence, evidence_count, source,
                    source_episodes, contradictions, active, version, previous_version_text
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
                """,
                principle.category,
                principle.principle,
                principle.confidence,
                principle.evidence_count,
                principle.source,
                principle.source_episodes,
                principle.contradictions,
                principle.active,
                principle.version,
                principle.previous_version_text
            )

            log.info(
                "principle_created",
                id=principle_id,
                category=principle.category,
                confidence=principle.confidence
            )
            return principle_id
    except Exception as e:
        log.error("principle_create_failed", error=str(e), category=principle.category)
        raise


async def get_active(
    pool: asyncpg.Pool,
    category: str | None = None
) -> list[LearnedPrinciple]:
    try:
        async with pool.acquire() as conn:
            if category:
                rows = await conn.fetch(
                    """
                    SELECT *
                    FROM learned_principles
                    WHERE active = TRUE AND category = $1
                    ORDER BY confidence DESC, updated_at DESC
                    """,
                    category
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT *
                    FROM learned_principles
                    WHERE active = TRUE
                    ORDER BY confidence DESC, updated_at DESC
                    """
                )

            results = [_row_to_principle(row) for row in rows]
            log.debug("principles_get_active", category=category, count=len(results))
            return results
    except Exception as e:
        log.error("principles_get_active_failed", error=str(e), category=category, exc_info=True)
        raise


async def update_confidence(
    pool: asyncpg.Pool,
    id: int,
    new_evidence_id: int,
    supporting: bool
) -> LearnedPrinciple:
    try:
        async with pool.acquire() as conn:
            current = await conn.fetchrow(
                "SELECT * FROM learned_principles WHERE id = $1",
                id
            )

            if not current:
                raise ValueError(f"Principle {id} not found")

            old_confidence = float(current["confidence"])
            evidence_count = current["evidence_count"]
            source_episodes = list(current["source_episodes"])
            contradictions = list(current["contradictions"])

            if supporting:
                source_episodes.append(new_evidence_id)

                # Bayesian-style update: weight prior by `prior_strength`, new
                # observation by 1. Using the post-increment `evidence_count`
                # as the numerator (pre-fix) double-counted every step and the
                # confidence ratcheted to the 0.95 cap in ~3 observations,
                # suppressing genuine learning. Apply the update first, THEN
                # bump the evidence counter for the persisted record.
                prior_strength = 2.0
                new_confidence = (
                    (old_confidence * prior_strength + 1.0) /
                    (prior_strength + 1.0)
                )
                new_confidence = min(new_confidence, 0.95)
                evidence_count += 1
            else:
                contradictions.append(new_evidence_id)
                evidence_count += 1

                penalty = 0.1 * (1.0 + len(contradictions) * 0.1)
                new_confidence = max(old_confidence - penalty, 0.05)

            await conn.execute(
                """
                UPDATE learned_principles
                SET
                    confidence = $2,
                    evidence_count = $3,
                    source_episodes = $4,
                    contradictions = $5,
                    updated_at = NOW()
                WHERE id = $1
                """,
                id,
                new_confidence,
                evidence_count,
                source_episodes,
                contradictions
            )

            updated_row = await conn.fetchrow(
                "SELECT * FROM learned_principles WHERE id = $1",
                id
            )

            result = _row_to_principle(updated_row)

            log.info(
                "principle_confidence_updated",
                id=id,
                supporting=supporting,
                old_confidence=old_confidence,
                new_confidence=new_confidence,
                evidence_count=evidence_count
            )

            return result
    except Exception as e:
        log.error("principle_update_confidence_failed", error=str(e), id=id)
        raise


async def deactivate(pool: asyncpg.Pool, id: int) -> None:
    try:
        async with pool.acquire() as conn:
            tag = await conn.execute(
                """
                UPDATE learned_principles
                SET active = FALSE, updated_at = NOW()
                WHERE id = $1
                """,
                id
            )
            rows_affected = int(tag.split()[-1]) if tag.startswith("UPDATE ") else 0
            if rows_affected == 0:
                raise ValueError(f"Principle id={id} not found — nothing deactivated")
            log.info("principle_deactivated", id=id)
    except Exception as e:
        log.error("principle_deactivate_failed", error=str(e), id=id)
        raise


async def get_by_id(pool: asyncpg.Pool, id: int) -> LearnedPrinciple | None:
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM learned_principles WHERE id = $1",
                id
            )

            if not row:
                log.warning("principle_not_found", id=id)
                return None

            return _row_to_principle(row)
    except Exception as e:
        log.error("principle_get_by_id_failed", error=str(e), id=id)
        return None


def _row_to_principle(row: asyncpg.Record) -> LearnedPrinciple:
    return LearnedPrinciple(
        id=row["id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        category=row["category"],
        principle=row["principle"],
        confidence=float(row["confidence"]),
        evidence_count=row["evidence_count"],
        source=row["source"],
        source_episodes=list(row["source_episodes"]) if row["source_episodes"] else [],
        contradictions=list(row["contradictions"]) if row["contradictions"] else [],
        active=row["active"],
        version=row["version"],
        previous_version_text=row["previous_version_text"]
    )
