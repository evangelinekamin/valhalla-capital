"""
Valhalla Capital Dashboard - External Database Layer

Read-only connection to the Overseer PostgreSQL instance on 249.
All Valkyrie data (cycle_logs, decision_journal, trades, episodic_memory)
lives in the overseer DB.
"""

import logging
from typing import Any

import asyncpg

from .config import DashboardConfig

logger = logging.getLogger(__name__)


class ExternalDB:
    """
    Manages read-only connection pools to external PostgreSQL instances.
    Fails gracefully — if a DB is unreachable, pages degrade to
    'no data available' rather than crashing the dashboard.
    """

    def __init__(self, config: DashboardConfig):
        self.config = config
        self._overseer_pool: asyncpg.Pool | None = None

    async def connect(self):
        """Initialize connection pool. Non-fatal if DB is unreachable."""
        try:
            self._overseer_pool = await asyncpg.create_pool(
                host=self.config.overseer_db_host,
                port=self.config.overseer_db_port,
                database=self.config.overseer_db_name,
                user=self.config.overseer_db_user,
                password=self.config.overseer_db_password,
                min_size=1,
                max_size=3,
                command_timeout=10,
                server_settings={"statement_timeout": "5000"},
            )
            logger.info(f"Connected to Overseer DB at {self.config.overseer_db_host}")
        except Exception as e:
            logger.warning(f"Could not connect to Overseer DB: {e}")
            self._overseer_pool = None

    async def close(self):
        if self._overseer_pool:
            await self._overseer_pool.close()

    # ------------------------------------------------------------------
    # Overseer queries (Valkyrie on 249)
    # ------------------------------------------------------------------

    @property
    def overseer_available(self) -> bool:
        return self._overseer_pool is not None

    async def get_cycle_logs(
        self,
        limit: int = 50,
        offset: int = 0,
        cycle_type: str | None = None,
    ) -> list[dict]:
        """
        Fetch cycle log entries from the overseer.

        These are Valkyrie's full processing outputs — the untruncated
        versions of what gets posted to Discord.

        Actual schema:
            cycle_logs(id, cycle_type, model, started_at, completed_at,
                      tokens_used, tools_called, cost_cents, error, summary)
        """
        if not self._overseer_pool:
            return []

        try:
            where = ""
            params: list[Any] = []
            param_idx = 1

            if cycle_type:
                where = f"WHERE cycle_type = ${param_idx}"
                params.append(cycle_type)
                param_idx += 1

            params.extend([limit, offset])
            query = f"""
                SELECT *
                FROM cycle_logs
                {where}
                ORDER BY started_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            rows = await self._overseer_pool.fetch(query, *params)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to fetch cycle_logs: {e}")
            return []

    async def get_cycle_log_count(self, cycle_type: str | None = None) -> int:
        """Total count for pagination."""
        if not self._overseer_pool:
            return 0
        try:
            if cycle_type:
                row = await self._overseer_pool.fetchrow(
                    "SELECT COUNT(*) as cnt FROM cycle_logs WHERE cycle_type = $1",
                    cycle_type
                )
            else:
                row = await self._overseer_pool.fetchrow(
                    "SELECT COUNT(*) as cnt FROM cycle_logs"
                )
            return row["cnt"] if row else 0
        except Exception as e:
            logger.error(f"Failed to count cycle_logs: {e}")
            return 0

    async def get_decision_journal(
        self,
        limit: int = 50,
        offset: int = 0,
        ticker: str | None = None,
    ) -> list[dict]:
        """
        Fetch decision journal entries — Valkyrie's investment reasoning.

        Actual schema:
            decision_journal(id, cycle_log_id, created_at, decision_type,
                           summary, reasoning, tickers[], confidence,
                           falsification_criteria, outcome, outcome_details, reviewed_at)
        """
        if not self._overseer_pool:
            return []

        try:
            where = ""
            params: list[Any] = []
            param_idx = 1

            if ticker:
                where = f"WHERE ${param_idx} = ANY(tickers)"
                params.append(ticker.upper())
                param_idx += 1

            params.extend([limit, offset])
            query = f"""
                SELECT *
                FROM decision_journal
                {where}
                ORDER BY created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            rows = await self._overseer_pool.fetch(query, *params)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to fetch decision_journal: {e}")
            return []

    async def get_episodic_memory(self, limit: int = 20) -> list[dict]:
        """
        Fetch Valkyrie's episodic memory — what she currently 'knows'.
        """
        if not self._overseer_pool:
            return []

        try:
            rows = await self._overseer_pool.fetch(
                "SELECT * FROM episodic_memory ORDER BY created_at DESC LIMIT $1",
                limit,
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to fetch episodic_memory: {e}")
            return []

    async def get_recent_events(self, limit: int = 15) -> list[dict]:
        """Fetch recent events across trades, decisions, and cycles for the ticker."""
        if not self._overseer_pool:
            return []

        events: list[dict] = []
        queries = [
            ("TRADE", """
                SELECT created_at as event_time,
                       ticker || ' ' || action || ' x' || quantity ||
                           CASE WHEN fill_price IS NOT NULL
                                THEN ' @ $' || ROUND(fill_price::numeric, 2)::text
                                ELSE '' END as event_text
                FROM trades
                WHERE created_at >= NOW() - INTERVAL '48 hours'
                ORDER BY created_at DESC LIMIT 5
            """),
            ("DECISION", """
                SELECT created_at as event_time,
                       COALESCE(tickers[1], '???') || ' ' ||
                           COALESCE(decision_type, 'REVIEW') ||
                           CASE WHEN confidence IS NOT NULL
                                THEN ' [' || confidence::text || '/10]'
                                ELSE '' END as event_text
                FROM decision_journal
                WHERE created_at >= NOW() - INTERVAL '48 hours'
                ORDER BY created_at DESC LIMIT 5
            """),
            ("CYCLE", """
                SELECT started_at as event_time,
                       cycle_type ||
                           CASE WHEN cost_cents IS NOT NULL
                                THEN ' · $' || ROUND(cost_cents::numeric / 100, 2)::text
                                ELSE '' END as event_text
                FROM cycle_logs
                WHERE started_at >= NOW() - INTERVAL '48 hours'
                ORDER BY started_at DESC LIMIT 5
            """),
        ]

        for event_type, query in queries:
            try:
                rows = await self._overseer_pool.fetch(query)
                for r in rows:
                    events.append({
                        "event_type": event_type,
                        "event_time": r["event_time"],
                        "event_text": r["event_text"],
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch {event_type} events: {e}")

        events.sort(key=lambda x: x["event_time"], reverse=True)
        return events[:limit]

    async def get_portfolio_history(self) -> list[dict]:
        """Compute portfolio value over time from filled trades.

        Returns two series:
          - pnl: realized P&L (cash + positions at cost)
          - value: active position value (cost basis of holdings)
        """
        empty = {"pnl": [], "value": []}
        if not self._overseer_pool:
            return empty

        try:
            rows = await self._overseer_pool.fetch("""
                SELECT filled_at, ticker, action, quantity, fill_price
                FROM trades
                WHERE status = 'filled'
                  AND fill_price IS NOT NULL
                  AND filled_at IS NOT NULL
                ORDER BY filled_at ASC
            """)
            if not rows:
                return empty

            # Walk through trades chronologically tracking cash + positions.
            # BUY: cash goes out, position goes in at same value -> net zero.
            # SELL: cash comes in at sell price, position removed at cost basis.
            # Difference = realized P&L, which moves the total.
            positions: dict[str, float] = {}   # ticker -> net quantity
            cost_basis: dict[str, float] = {}  # ticker -> total cost
            cash: float = 0.0
            pnl_points: list[dict] = []
            value_points: list[dict] = []

            for r in rows:
                ticker = r["ticker"]
                qty = float(r["quantity"])
                price = float(r["fill_price"])

                if ticker not in positions:
                    positions[ticker] = 0.0
                    cost_basis[ticker] = 0.0

                if r["action"] == "BUY":
                    cash -= qty * price
                    positions[ticker] += qty
                    cost_basis[ticker] += qty * price
                elif r["action"] == "SELL":
                    cash += qty * price
                    if positions[ticker] > 0:
                        avg = cost_basis[ticker] / positions[ticker]
                        positions[ticker] -= qty
                        cost_basis[ticker] = max(0, positions[ticker] * avg)

                ts = r["filled_at"].isoformat() if hasattr(r["filled_at"], "isoformat") else str(r["filled_at"])
                deployed = sum(cost_basis.values())

                pnl_points.append({
                    "time": ts,
                    "value": round(cash + deployed, 2),
                })
                value_points.append({
                    "time": ts,
                    "value": round(deployed, 2),
                })

            return {"pnl": pnl_points, "value": value_points}
        except Exception as e:
            logger.error(f"Failed to compute portfolio history: {e}")
            return empty

    async def get_portfolio_cash(self) -> dict:
        """Fetch cached portfolio cash balance from working_memory.

        The overseer writes the full IBKR portfolio state to working_memory
        on every cycle. This is the real cash balance, not a trade-replay
        approximation.

        Returns dict with keys: cash, total_value, updated_at
        """
        empty = {"cash": 0.0, "total_value": 0.0, "updated_at": None}
        if not self._overseer_pool:
            return empty
        try:
            row = await self._overseer_pool.fetchrow("""
                SELECT
                    (value->>'cash')::numeric AS cash,
                    (value->>'total_value')::numeric AS total_value,
                    updated_at
                FROM working_memory
                WHERE key = 'portfolio_state_cached'
            """)
            if not row:
                return empty
            return {
                "cash": float(row["cash"]) if row["cash"] is not None else 0.0,
                "total_value": float(row["total_value"]) if row["total_value"] is not None else 0.0,
                "updated_at": row["updated_at"],
            }
        except Exception as e:
            logger.error(f"Failed to fetch portfolio cash: {e}")
            return empty

    async def get_cycle_types(self) -> list[str]:
        """Get distinct cycle types for filtering."""
        if not self._overseer_pool:
            return []
        try:
            rows = await self._overseer_pool.fetch(
                "SELECT DISTINCT cycle_type FROM cycle_logs ORDER BY cycle_type"
            )
            return [r["cycle_type"] for r in rows if r["cycle_type"]]
        except Exception as e:
            logger.error(f"Failed to fetch cycle types: {e}")
            return []

    # ------------------------------------------------------------------
    # Trade queries (trades table lives in overseer DB on 249)
    # ------------------------------------------------------------------

    @property
    def trading_available(self) -> bool:
        return self._overseer_pool is not None

    async def get_trades(
        self,
        limit: int = 50,
        offset: int = 0,
        ticker: str | None = None,
    ) -> list[dict]:
        """
        Fetch trade history from the overseer DB.

        Actual schema:
            trades(id, request_id, decision_id, created_at, ticker, action,
                  quantity, price, commission, status, kelly_fraction,
                  reasoning, ibkr_order_id, filled_at, fill_price,
                  outcome, outcome_pnl)
        """
        if not self._overseer_pool:
            return []

        try:
            where = ""
            params: list[Any] = []
            param_idx = 1

            if ticker:
                where = f"WHERE ticker = ${param_idx}"
                params.append(ticker.upper())
                param_idx += 1

            params.extend([limit, offset])
            query = f"""
                SELECT *
                FROM trades
                {where}
                ORDER BY created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            rows = await self._overseer_pool.fetch(query, *params)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to fetch trades: {e}")
            return []

    async def get_portfolio_state(self) -> dict | None:
        """
        Aggregate current portfolio from trades table.

        Groups filled BUY/SELL trades by ticker to compute net positions,
        weighted average fill price, and estimated market value.
        """
        if not self._overseer_pool:
            return None

        try:
            rows = await self._overseer_pool.fetch("""
                SELECT ticker,
                       SUM(CASE WHEN action = 'BUY' THEN quantity
                                WHEN action = 'SELL' THEN -quantity
                                ELSE 0 END) as quantity,
                       CASE WHEN SUM(CASE WHEN action = 'BUY' THEN quantity ELSE 0 END) > 0
                            THEN SUM(CASE WHEN action = 'BUY' THEN quantity * fill_price ELSE 0 END)
                                 / SUM(CASE WHEN action = 'BUY' THEN quantity ELSE 0 END)
                            ELSE 0 END as avg_price,
                       SUM(CASE WHEN action = 'BUY' THEN quantity * fill_price
                                WHEN action = 'SELL' THEN -quantity * fill_price
                                ELSE 0 END) as market_value,
                       MAX(filled_at) as last_trade
                FROM trades
                WHERE status = 'filled' AND fill_price IS NOT NULL
                GROUP BY ticker
                HAVING SUM(CASE WHEN action = 'BUY' THEN quantity
                                WHEN action = 'SELL' THEN -quantity
                                ELSE 0 END) > 0
                ORDER BY ticker
            """)
            return {
                "positions": [dict(r) for r in rows],
                "source": "trades_aggregation",
            }
        except Exception as e:
            logger.error(f"Failed to fetch portfolio state: {e}")
            return None
