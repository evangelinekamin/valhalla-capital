"""Configuration management for FMP Data Client."""

from enum import Enum
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Tier(str, Enum):
    """FMP API subscription tiers."""

    STARTER = "starter"
    PREMIUM = "premium"
    ULTIMATE = "ultimate"


class FMPConfig(BaseSettings):
    """Configuration for FMP Data Client.

    Configuration can be loaded from environment variables with FMP_ prefix.
    Example: FMP_API_KEY=your_key, FMP_TIER=premium
    """

    model_config = SettingsConfigDict(
        env_prefix="FMP_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # API Configuration
    api_key: str = Field(..., description="FMP API key")
    tier: Tier = Field(default=Tier.STARTER, description="API subscription tier")

    # Cache Configuration
    cache_enabled: bool = Field(default=False, description="Enable MySQL caching")
    mysql_host: str = Field(default="localhost", description="MySQL host")
    mysql_port: int = Field(default=3306, description="MySQL port")
    mysql_user: str = Field(default="root", description="MySQL username")
    mysql_password: str = Field(default="", description="MySQL password")
    mysql_database: str = Field(default="fmp_cache", description="MySQL database name")
    mysql_pool_size: int = Field(default=5, description="MySQL connection pool size")

    # Summarization Configuration
    summarization_enabled: bool = Field(
        default=False,
        description="Enable LLM summarization for transcripts and filings"
    )
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude"
    )
    default_model: str = Field(
        default="claude-3-haiku-20240307",
        description="Default Claude model for summarization"
    )

    # Rate Limiting Configuration
    calls_per_minute: Optional[int] = Field(
        default=None,
        description="API calls per minute limit (auto-determined from tier if not set)"
    )
    max_concurrent_requests: int = Field(
        default=10,
        description="Maximum concurrent API requests"
    )

    # Request Configuration
    request_timeout: int = Field(default=30, description="API request timeout in seconds")
    retry_attempts: int = Field(default=3, description="Number of retry attempts for failed requests")

    @field_validator("tier", mode="before")
    @classmethod
    def validate_tier(cls, v: str | Tier) -> Tier:
        """Convert string to Tier enum."""
        if isinstance(v, Tier):
            return v
        try:
            return Tier(v.lower())
        except ValueError:
            raise ValueError(
                f"Invalid tier: {v}. Must be one of: {', '.join(t.value for t in Tier)}"
            )

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_anthropic_key(cls, v: Optional[str], info) -> Optional[str]:
        """Validate Anthropic API key is provided when summarization is enabled."""
        # Access other field values through info.data
        summarization_enabled = info.data.get("summarization_enabled", False)
        if summarization_enabled and not v:
            raise ValueError(
                "anthropic_api_key must be provided when summarization_enabled=True"
            )
        return v

    def get_rate_limit(self) -> int:
        """Get rate limit based on tier.

        Returns:
            Calls per minute limit for the current tier
        """
        if self.calls_per_minute is not None:
            return self.calls_per_minute

        # Default rate limits by tier
        tier_limits = {
            Tier.STARTER: 300,
            Tier.PREMIUM: 750,
            Tier.ULTIMATE: 3000,
        }
        return tier_limits[self.tier]

    @classmethod
    def from_env(cls) -> "FMPConfig":
        """Create configuration from environment variables.

        Returns:
            FMPConfig instance loaded from environment
        """
        return cls()

    def model_dump_safe(self) -> dict:
        """Dump configuration with sensitive data masked.

        Returns:
            Dictionary with API keys masked
        """
        data = self.model_dump()
        if data.get("api_key"):
            data["api_key"] = f"{data['api_key'][:4]}...{data['api_key'][-4:]}"
        if data.get("anthropic_api_key"):
            data["anthropic_api_key"] = f"{data['anthropic_api_key'][:4]}...{data['anthropic_api_key'][-4:]}"
        if data.get("mysql_password"):
            data["mysql_password"] = "***"
        return data
