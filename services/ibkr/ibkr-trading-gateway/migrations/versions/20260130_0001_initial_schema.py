"""Initial schema with TimescaleDB hypertables.

Revision ID: 001_initial
Revises:
Create Date: 2026-01-30 10:00:00.000000

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial schema with TimescaleDB hypertables."""

    # Enable TimescaleDB extension
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

    # Create trades table
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
        ),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("action", sa.String(length=4), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("order_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("filled_price", sa.Float(), nullable=True),
        sa.Column("commission", sa.Float(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("kelly_fraction", sa.Float(), nullable=True),
        sa.Column("half_kelly_fraction", sa.Float(), nullable=True),
        sa.Column("portfolio_value_at_trade", sa.Float(), nullable=True),
        sa.Column("analysis_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id", "timestamp", name=op.f("pk_trades")),
    )
    op.create_index(op.f("ix_ticker"), "trades", ["ticker"], unique=False)
    op.create_index(op.f("ix_timestamp"), "trades", ["timestamp"], unique=False)
    op.create_index(op.f("ix_status"), "trades", ["status"], unique=False)

    # Convert trades to TimescaleDB hypertable (partitioned by timestamp)
    op.execute(
        """
        SELECT create_hypertable(
            'trades',
            'timestamp',
            chunk_time_interval => INTERVAL '1 week',
            if_not_exists => TRUE
        );
        """
    )

    # Create risk_checks table
    op.create_table(
        "risk_checks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=True),
        sa.Column("check_name", sa.String(length=50), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["trade_id"],
            ["trades.id"],
            name=op.f("fk_risk_checks_trade_id_trades"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_checks")),
    )
    op.create_index(
        op.f("ix_trade_id"), "risk_checks", ["trade_id"], unique=False
    )
    op.create_index(
        "ix_risk_checks_timestamp", "risk_checks", ["timestamp"], unique=False
    )

    # Create portfolio_snapshots table
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("total_value", sa.Float(), nullable=False),
        sa.Column("cash_balance", sa.Float(), nullable=False),
        sa.Column(
            "positions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("daily_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("daily_pnl_pct", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id", "timestamp", name=op.f("pk_portfolio_snapshots")),
    )
    op.create_index(
        "ix_portfolio_snapshots_timestamp",
        "portfolio_snapshots",
        ["timestamp"],
        unique=False,
    )

    # Convert portfolio_snapshots to TimescaleDB hypertable
    op.execute(
        """
        SELECT create_hypertable(
            'portfolio_snapshots',
            'timestamp',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        );
        """
    )

    # Create claude_decisions table (for future analysis)
    op.create_table(
        "claude_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=True),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("win_probability", sa.Float(), nullable=False),
        sa.Column("expected_gain_pct", sa.Float(), nullable=False),
        sa.Column("expected_loss_pct", sa.Float(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("data_sources", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trade_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["trade_id"],
            ["trades.id"],
            name=op.f("fk_claude_decisions_trade_id_trades"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_claude_decisions")),
    )
    op.create_index(
        "ix_claude_decisions_ticker",
        "claude_decisions",
        ["ticker"],
        unique=False,
    )
    op.create_index(
        "ix_claude_decisions_timestamp",
        "claude_decisions",
        ["timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_claude_decisions_trade_id",
        "claude_decisions",
        ["trade_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("claude_decisions")
    op.drop_table("portfolio_snapshots")
    op.drop_table("risk_checks")
    op.drop_table("trades")
