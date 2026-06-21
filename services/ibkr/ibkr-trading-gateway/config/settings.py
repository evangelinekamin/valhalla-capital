"""Application settings using Pydantic for type-safe configuration."""
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Main application settings loaded from environment and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # IBKR connection
    ibkr_username: str = Field(default="")
    ibkr_password: str = Field(default="")
    ibkr_host: str = Field(default="ib-gateway")
    ibkr_port: int = Field(default=4002)
    ibkr_client_id: int = Field(default=1)
    trading_mode: Literal["paper", "live"] = Field(default="paper")

    # Database
    database_url: str = Field(
        default="postgresql://trading:trading@postgres:5432/trading",
    )

    # Discord
    discord_webhook_url: str = Field(default="")

    # Risk limits
    max_position_fraction: float = Field(default=0.20, ge=0.0, le=1.0)
    max_daily_loss_pct: float = Field(default=0.03, ge=0.0, le=1.0)
    min_position_size_usd: float = Field(default=30.0, gt=0.0)
    max_position_size_usd: float = Field(default=2000.0, gt=0.0)
    max_trades_per_day: int = Field(default=10, gt=0)
    max_trades_per_week: int = Field(default=30, gt=0)
    max_portfolio_concentration: float = Field(default=0.30, ge=0.0, le=1.0)

    # Paths
    trade_requests_path: Path = Field(default=Path("/shared/trade_requests"))
    trade_results_path: Path = Field(default=Path("/shared/trade_results"))
    portfolio_state_path: Path = Field(default=Path("/shared/portfolio_state"))

    # Operational
    initial_portfolio_value: float = Field(default=500.0)
    dry_run_mode: bool = Field(default=True)
