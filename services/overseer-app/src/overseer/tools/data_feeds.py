from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog

from overseer.config import OverseerSettings
from overseer.utils.ssh import ssh_read_file, ssh_sqlite_query

log = structlog.get_logger()


async def query_twitter_feed(
    settings: OverseerSettings,
    limit: int = 50,
    since: str | None = None,
) -> dict[str, Any]:
    source = "twitter"
    try:
        params: dict[str, Any] = {
            "limit": min(limit, 100),
        }
        if since is not None:
            params["since"] = since

        url = f"http://{settings.twitter_host}:{settings.twitter_port}/tweets"

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        tweets = data if isinstance(data, list) else (data.get("tweets") or data.get("data", []))

        # Filter out SKIP (memes, commentary, off-topic) — keep everything else
        tweets = [t for t in tweets if t.get("classification") != "SKIP"]

        # Staleness tracking
        data_fresh = False
        data_staleness_hours = None
        if tweets:
            newest_ts = None
            for tweet in tweets:
                published = tweet.get("published_at") or tweet.get("created_at")
                if not published:
                    continue
                try:
                    ts = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if newest_ts is None or ts > newest_ts:
                        newest_ts = ts
                except (ValueError, TypeError):
                    continue

            if newest_ts is not None:
                now = datetime.now(timezone.utc)
                delta_hours = (now - newest_ts).total_seconds() / 3600
                data_staleness_hours = round(delta_hours, 1)
                data_fresh = delta_hours < 4.0

        return {
            "data": tweets,
            "source": source,
            "fetched_at": datetime.utcnow().isoformat(),
            "count": len(tweets),
            "data_fresh": data_fresh,
            "data_staleness_hours": data_staleness_hours,
        }

    except httpx.TimeoutException as e:
        log.error("twitter_feed_timeout", error=str(e))
        return {
            "data": [],
            "source": source,
            "error": f"Connection timeout: {e}",
            "count": 0,
            "data_fresh": False,
            "data_staleness_hours": None,
        }
    except httpx.HTTPError as e:
        log.error("twitter_feed_http_error", error=str(e))
        return {
            "data": [],
            "source": source,
            "error": f"HTTP error: {e}",
            "count": 0,
            "data_fresh": False,
            "data_staleness_hours": None,
        }
    except Exception as e:
        log.error("twitter_feed_error", error=str(e))
        return {
            "data": [],
            "source": source,
            "error": str(e),
            "count": 0,
            "data_fresh": False,
            "data_staleness_hours": None,
        }


async def query_news_feed(settings: OverseerSettings) -> dict[str, Any]:
    source = "news"
    try:
        file_path = "/opt/trading/news-fetch-process/alerts/critical_alerts.json"
        raw_output = await ssh_read_file(
            settings.data_collection_host,
            file_path,
            key_path=settings.ssh_key_path,
        )

        alerts = json.loads(raw_output)
        if not isinstance(alerts, list):
            alerts = [alerts] if alerts else []

        # Filter to last 48 hours to prevent stale backlog accumulation
        cutoff = (datetime.utcnow() - timedelta(hours=48)).isoformat()
        recent_alerts = [
            a for a in alerts
            if a.get("timestamp", a.get("date", "")) >= cutoff
        ]

        return {
            "data": recent_alerts,
            "source": source,
            "fetched_at": datetime.utcnow().isoformat(),
            "count": len(recent_alerts),
            "total_unfiltered": len(alerts),
        }

    except json.JSONDecodeError as e:
        log.error("news_feed_json_error", error=str(e))
        return {
            "data": [],
            "source": source,
            "error": f"JSON parse error: {e}",
            "count": 0,
        }
    except Exception as e:
        log.error("news_feed_error", error=str(e))
        return {
            "data": [],
            "source": source,
            "error": str(e),
            "count": 0,
        }


async def query_substack_feed(
    settings: OverseerSettings,
    limit: int = 20,
) -> dict[str, Any]:
    source = "substack"
    try:
        db_path = "/opt/trading/substack-fetch-process/newsletters.db"
        query = f"""
            SELECT ticker, action, sentiment, target_price, stop_loss, thesis, confidence, extracted_at
            FROM ticker_updates
            ORDER BY extracted_at DESC
            LIMIT {int(limit)}
        """

        raw_output = await ssh_sqlite_query(
            settings.data_collection_host,
            db_path,
            query,
            mode="json",
            key_path=settings.ssh_key_path,
        )

        updates = json.loads(raw_output) if raw_output.strip() else []
        if not isinstance(updates, list):
            updates = []

        return {
            "data": updates,
            "source": source,
            "fetched_at": datetime.utcnow().isoformat(),
            "count": len(updates),
        }

    except json.JSONDecodeError as e:
        log.error("substack_feed_json_error", error=str(e))
        return {
            "data": [],
            "source": source,
            "error": f"JSON parse error: {e}",
            "count": 0,
        }
    except Exception as e:
        log.error("substack_feed_error", error=str(e))
        return {
            "data": [],
            "source": source,
            "error": str(e),
            "count": 0,
        }


async def query_yellowbrick_feed(
    settings: OverseerSettings,
    limit: int = 20,
    feed_type: str | None = None,
) -> dict[str, Any]:
    source = "yellowbrick"
    try:
        db_path = "/opt/trading/yellowbrick-fetch-process/data/yellowbrick.db"

        where_clause = ""
        if feed_type:
            sanitized_type = "".join(c for c in feed_type if c.isalnum() or c in ("_", "-"))
            where_clause = f"WHERE feed_type = '{sanitized_type}'"
        query = f"SELECT * FROM v_recent_pitches {where_clause} LIMIT {int(limit)}"

        raw_output = await ssh_sqlite_query(
            settings.data_collection_host,
            db_path,
            query,
            mode="json",
            key_path=settings.ssh_key_path,
        )

        pitches = json.loads(raw_output) if raw_output.strip() else []
        if not isinstance(pitches, list):
            pitches = []

        return {
            "data": pitches,
            "source": source,
            "fetched_at": datetime.utcnow().isoformat(),
            "count": len(pitches),
        }

    except json.JSONDecodeError as e:
        log.error("yellowbrick_feed_json_error", error=str(e), raw_output=raw_output if 'raw_output' in locals() else None)
        return {
            "data": [],
            "source": source,
            "error": f"JSON parse error (possibly empty database): {e}",
            "count": 0,
        }
    except RuntimeError as e:
        if "0-byte" in str(e).lower() or "empty" in str(e).lower():
            log.warning("yellowbrick_feed_empty_db", error=str(e))
            return {
                "data": [],
                "source": source,
                "error": "Database is empty or 0-byte",
                "count": 0,
            }
        log.error("yellowbrick_feed_runtime_error", error=str(e))
        return {
            "data": [],
            "source": source,
            "error": str(e),
            "count": 0,
        }
    except Exception as e:
        log.error("yellowbrick_feed_error", error=str(e))
        return {
            "data": [],
            "source": source,
            "error": str(e),
            "count": 0,
        }


async def query_openinsider(
    settings: OverseerSettings,
    min_insider_count: int = 3,
    limit: int = 20,
) -> dict[str, Any]:
    source = "openinsider"
    try:
        db_path = "/opt/trading/openinsider-fetch-process/data/openinsider.db"
        query = f"""
            SELECT * FROM recent_clusters
            WHERE insider_count >= {int(min_insider_count)}
            LIMIT {int(limit)}
        """

        raw_output = await ssh_sqlite_query(
            settings.data_collection_host,
            db_path,
            query,
            mode="json",
            key_path=settings.ssh_key_path,
        )

        clusters = json.loads(raw_output) if raw_output.strip() else []
        if not isinstance(clusters, list):
            clusters = []

        return {
            "data": clusters,
            "source": source,
            "fetched_at": datetime.utcnow().isoformat(),
            "count": len(clusters),
        }

    except json.JSONDecodeError as e:
        log.error("openinsider_feed_json_error", error=str(e))
        return {
            "data": [],
            "source": source,
            "error": f"JSON parse error: {e}",
            "count": 0,
        }
    except Exception as e:
        log.error("openinsider_feed_error", error=str(e))
        return {
            "data": [],
            "source": source,
            "error": str(e),
            "count": 0,
        }


async def query_all_feeds(settings: OverseerSettings) -> dict[str, dict[str, Any]]:
    results = await asyncio.gather(
        query_twitter_feed(settings),
        query_news_feed(settings),
        query_substack_feed(settings),
        query_yellowbrick_feed(settings),
        query_openinsider(settings),
        return_exceptions=True,
    )

    feed_names = ["twitter", "news", "substack", "yellowbrick", "openinsider"]
    output = {}
    for name, result in zip(feed_names, results):
        if isinstance(result, BaseException):
            log.error("feed_query_failed", feed=name, error=str(result))
            output[name] = {"data": [], "source": name, "error": str(result), "count": 0}
        else:
            output[name] = result
    return output
