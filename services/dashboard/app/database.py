"""
Valhalla Capital Dashboard - Database Layer

Stores health check snapshots and dashboard state in SQLite.
Lightweight, no external dependencies beyond aiosqlite.
"""

import aiosqlite
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS health_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    status TEXT NOT NULL,
    response_ms INTEGER,
    details TEXT,  -- JSON blob of health response
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_snapshots_service
    ON health_snapshots(service_name, checked_at DESC);

CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    service_name TEXT NOT NULL,
    checks_total INTEGER DEFAULT 0,
    checks_healthy INTEGER DEFAULT 0,
    avg_response_ms REAL,
    UNIQUE(date, service_name)
);

CREATE TABLE IF NOT EXISTS cost_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    amount_usd REAL NOT NULL,
    description TEXT,
    UNIQUE(date, category)
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    total_value REAL NOT NULL,
    total_cost REAL NOT NULL,
    positions_json TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_time
    ON portfolio_snapshots(captured_at DESC);
"""


class Database:
    """Async SQLite wrapper for dashboard storage."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self):
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA cache_size=-8000")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.execute("PRAGMA temp_store=MEMORY")
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        logger.info(f"Database connected: {self.db_path}")

    async def close(self):
        if self._db:
            await self._db.close()

    async def save_snapshot(
        self,
        service_name: str,
        status: str,
        response_ms: int | None = None,
        details: dict | None = None,
        error: str | None = None,
    ):
        """Store a health check result."""
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """INSERT INTO health_snapshots
               (service_name, checked_at, status, response_ms, details, error)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (service_name, now, status, response_ms,
             json.dumps(details) if details else None, error),
        )
        await self._db.commit()

    async def save_snapshots(self, snapshots: list[dict]):
        """Store a batch of health check results in one transaction."""
        if not snapshots:
            return

        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                entry["service_name"],
                now,
                entry["status"],
                entry.get("response_ms"),
                json.dumps(entry["details"]) if entry.get("details") else None,
                entry.get("error"),
            )
            for entry in snapshots
        ]
        await self._db.executemany(
            """INSERT INTO health_snapshots
               (service_name, checked_at, status, response_ms, details, error)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await self._db.commit()

    async def get_latest_snapshots(self) -> dict[str, dict]:
        """Get the most recent snapshot for each service."""
        cursor = await self._db.execute("""
            SELECT s.*
            FROM health_snapshots s
            INNER JOIN (
                SELECT service_name, MAX(checked_at) as max_checked
                FROM health_snapshots
                GROUP BY service_name
            ) latest ON s.service_name = latest.service_name
                    AND s.checked_at = latest.max_checked
            ORDER BY s.service_name
        """)
        rows = await cursor.fetchall()
        result = {}
        for row in rows:
            result[row["service_name"]] = {
                "status": row["status"],
                "checked_at": row["checked_at"],
                "response_ms": row["response_ms"],
                "details": json.loads(row["details"]) if row["details"] else None,
                "error": row["error"],
            }
        return result

    async def get_service_rollup(
        self,
        service_names: list[str],
        hours: int = 24,
    ) -> tuple[dict[str, dict], dict[str, float], dict[str, list[dict]]]:
        """Fetch latest snapshots, uptime, and response history in a small query set."""
        latest = await self.get_latest_snapshots()

        if not service_names:
            return latest, {}, {}

        placeholders = ",".join("?" for _ in service_names)

        uptime_cursor = await self._db.execute(
            f"""
            SELECT
                service_name,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'Served' THEN 1 ELSE 0 END) as healthy
            FROM health_snapshots
            WHERE service_name IN ({placeholders})
              AND checked_at >= datetime('now', ?)
              AND status != 'On Order'
            GROUP BY service_name
            """,
            [*service_names, f"-{hours} hours"],
        )
        uptime_rows = await uptime_cursor.fetchall()
        uptimes = {
            row["service_name"]: round(row["healthy"] / row["total"] * 100, 1)
            for row in uptime_rows
            if row["total"]
        }

        history_cursor = await self._db.execute(
            f"""
            SELECT service_name, checked_at, response_ms
            FROM health_snapshots
            WHERE service_name IN ({placeholders})
              AND checked_at >= datetime('now', ?)
              AND response_ms IS NOT NULL
            ORDER BY service_name ASC, checked_at ASC
            """,
            [*service_names, f"-{hours} hours"],
        )
        history_rows = await history_cursor.fetchall()
        histories: dict[str, list[dict]] = {name: [] for name in service_names}
        for row in history_rows:
            histories[row["service_name"]].append(
                {"t": row["checked_at"], "ms": row["response_ms"]}
            )

        return latest, uptimes, histories

    async def get_response_times(self, service_name: str, hours: int = 24) -> list[dict]:
        """Get response time history for sparklines."""
        cursor = await self._db.execute("""
            SELECT checked_at, response_ms
            FROM health_snapshots
            WHERE service_name = ?
              AND checked_at >= datetime('now', ?)
              AND response_ms IS NOT NULL
            ORDER BY checked_at ASC
        """, (service_name, f"-{hours} hours"))
        rows = await cursor.fetchall()
        return [{"t": row["checked_at"], "ms": row["response_ms"]} for row in rows]

    async def get_uptime_percent(self, service_name: str, hours: int = 24) -> float:
        """Calculate uptime percentage over the given window.

        Excludes 'On Order' snapshots (pre-check state) from the calculation
        so they don't drag down the percentage.
        """
        cursor = await self._db.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'Served' THEN 1 ELSE 0 END) as healthy
            FROM health_snapshots
            WHERE service_name = ?
              AND checked_at >= datetime('now', ?)
              AND status != 'On Order'
        """, (service_name, f"-{hours} hours"))
        row = await cursor.fetchone()
        if not row or row["total"] == 0:
            return -1  # No data
        return round(row["healthy"] / row["total"] * 100, 1)

    async def delete_service_snapshots(self, service_names: list[str]):
        """Remove all snapshots for services no longer monitored."""
        if not service_names:
            return
        placeholders = ",".join("?" for _ in service_names)
        deleted = await self._db.execute(
            f"DELETE FROM health_snapshots WHERE service_name IN ({placeholders})",
            service_names,
        )
        await self._db.commit()
        logger.info(f"Deleted snapshots for removed services: {service_names}")

    async def get_system_pulse(self, snapshots: dict[str, dict] | None = None) -> dict:
        """Calculate how long all services have been fully healthy.

        Returns a dict with:
          - all_healthy: bool
          - since: ISO timestamp of the last non-healthy snapshot (or None)
          - down_services: list of service names currently not 'Served'
        """
        # Find services currently not healthy
        snapshots = snapshots or await self.get_latest_snapshots()
        down = [
            name for name, snap in snapshots.items()
            if snap.get("status") not in ("Served", "On Order")
        ]

        if down:
            return {"all_healthy": False, "since": None, "down_services": down}

        # All healthy — find when the last incident ended
        cursor = await self._db.execute("""
            SELECT MAX(checked_at) as last_incident
            FROM health_snapshots
            WHERE status NOT IN ('Served', 'On Order')
        """)
        row = await cursor.fetchone()
        last_incident = row["last_incident"] if row else None

        return {"all_healthy": True, "since": last_incident, "down_services": []}

    async def get_recent_status_changes(self, limit: int = 10) -> list[dict]:
        """Detect recent status transitions for the event ticker.

        Finds cases where a service's status changed between consecutive checks.
        """
        cursor = await self._db.execute("""
            SELECT s1.service_name, s1.status as new_status,
                   s1.checked_at, s2.status as old_status
            FROM health_snapshots s1
            INNER JOIN health_snapshots s2
                ON s1.service_name = s2.service_name
                AND s2.checked_at = (
                    SELECT MAX(checked_at)
                    FROM health_snapshots
                    WHERE service_name = s1.service_name
                      AND checked_at < s1.checked_at
                )
            WHERE s1.status != s2.status
              AND s1.checked_at >= datetime('now', '-24 hours')
              AND s1.status != 'On Order'
              AND s2.status != 'On Order'
            ORDER BY s1.checked_at DESC
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        return [
            {
                "service": row["service_name"],
                "old_status": row["old_status"],
                "new_status": row["new_status"],
                "time": row["checked_at"],
            }
            for row in rows
        ]

    async def prune_old_snapshots(self, keep_days: int = 30):
        """Remove snapshots older than keep_days."""
        await self._db.execute("""
            DELETE FROM health_snapshots
            WHERE checked_at < datetime('now', ?)
        """, (f"-{keep_days} days",))
        await self._db.commit()

    # -- Portfolio snapshots ---------------------------------------------------

    async def save_portfolio_snapshot(
        self,
        total_value: float,
        total_cost: float,
        positions_json: str | None = None,
        error: str | None = None,
    ):
        """Store a periodic portfolio value snapshot."""
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """INSERT INTO portfolio_snapshots
               (captured_at, total_value, total_cost, positions_json, error)
               VALUES (?, ?, ?, ?, ?)""",
            (now, total_value, total_cost, positions_json, error),
        )
        await self._db.commit()

    async def get_portfolio_snapshots(self, days: int = 90) -> list[dict]:
        """Get portfolio snapshots for chart rendering (excludes error rows)."""
        cursor = await self._db.execute("""
            SELECT captured_at, total_value
            FROM portfolio_snapshots
            WHERE error IS NULL
              AND captured_at >= datetime('now', ?)
            ORDER BY captured_at ASC
            LIMIT 2000
        """, (f"-{days} days",))
        rows = await cursor.fetchall()
        return [{"time": row["captured_at"], "value": row["total_value"]} for row in rows]

    async def prune_portfolio_snapshots(self, keep_days: int = 90):
        """Remove portfolio snapshots older than keep_days."""
        await self._db.execute("""
            DELETE FROM portfolio_snapshots
            WHERE captured_at < datetime('now', ?)
        """, (f"-{keep_days} days",))
        await self._db.commit()
