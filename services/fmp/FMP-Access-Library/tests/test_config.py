"""Tests for configuration management."""

import pytest
from pydantic import ValidationError

from fmp_data_client.config import FMPConfig, Tier


class TestTierEnum:
    """Test Tier enum functionality."""

    def test_tier_values(self) -> None:
        """Test that all tier values are correct."""
        assert Tier.STARTER.value == "starter"
        assert Tier.PREMIUM.value == "premium"
        assert Tier.ULTIMATE.value == "ultimate"

    def test_tier_from_string(self) -> None:
        """Test creating Tier from string."""
        assert Tier("starter") == Tier.STARTER
        assert Tier("premium") == Tier.PREMIUM
        assert Tier("ultimate") == Tier.ULTIMATE


class TestFMPConfig:
    """Test FMPConfig class."""

    def test_minimal_config(self, minimal_config: FMPConfig) -> None:
        """Test creating minimal valid configuration."""
        assert minimal_config.api_key == "test_api_key_12345678"
        assert minimal_config.tier == Tier.STARTER
        assert minimal_config.cache_enabled is False
        assert minimal_config.summarization_enabled is False

    def test_tier_validation_case_insensitive(self) -> None:
        """Test tier validation is case insensitive."""
        config = FMPConfig(
            api_key="test_key",
            tier="PREMIUM",  # type: ignore
        )
        assert config.tier == Tier.PREMIUM

        config = FMPConfig(
            api_key="test_key",
            tier="Ultimate",  # type: ignore
        )
        assert config.tier == Tier.ULTIMATE

    def test_tier_validation_invalid(self) -> None:
        """Test that invalid tier raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            FMPConfig(
                api_key="test_key",
                tier="invalid_tier",  # type: ignore
            )
        assert "Invalid tier" in str(exc_info.value)

    def test_anthropic_key_required_when_summarization_enabled(self) -> None:
        """Test that anthropic_api_key is required when summarization is enabled."""
        with pytest.raises(ValidationError) as exc_info:
            FMPConfig(
                api_key="test_key",
                tier=Tier.STARTER,
                summarization_enabled=True,
                # Missing anthropic_api_key
            )
        assert "anthropic_api_key must be provided" in str(exc_info.value)

    def test_anthropic_key_optional_when_summarization_disabled(
        self, minimal_config: FMPConfig
    ) -> None:
        """Test that anthropic_api_key is optional when summarization is disabled."""
        assert minimal_config.summarization_enabled is False
        assert minimal_config.anthropic_api_key is None

    def test_get_rate_limit_starter(self, minimal_config: FMPConfig) -> None:
        """Test rate limit for starter tier."""
        assert minimal_config.get_rate_limit() == 300

    def test_get_rate_limit_premium(self, premium_config: FMPConfig) -> None:
        """Test rate limit for premium tier."""
        assert premium_config.get_rate_limit() == 750

    def test_get_rate_limit_ultimate(
        self, ultimate_config_with_llm: FMPConfig
    ) -> None:
        """Test rate limit for ultimate tier."""
        assert ultimate_config_with_llm.get_rate_limit() == 3000

    def test_get_rate_limit_custom(self) -> None:
        """Test custom rate limit override."""
        config = FMPConfig(
            api_key="test_key",
            tier=Tier.STARTER,
            calls_per_minute=500,
        )
        assert config.get_rate_limit() == 500

    def test_model_dump_safe(self) -> None:
        """Test that sensitive data is masked in dumps."""
        config = FMPConfig(
            api_key="test_api_key_1234567890",
            tier=Tier.ULTIMATE,
            cache_enabled=True,
            mysql_password="secret_password",
            summarization_enabled=True,
            anthropic_api_key="sk-ant-1234567890",
        )

        safe_dump = config.model_dump_safe()

        # API keys should be masked
        assert safe_dump["api_key"] == "test...7890"
        assert safe_dump["anthropic_api_key"] == "sk-a...7890"
        assert safe_dump["mysql_password"] == "***"

        # Other fields should be intact
        assert safe_dump["tier"] == Tier.ULTIMATE

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = FMPConfig(api_key="test_key")

        assert config.tier == Tier.STARTER
        assert config.cache_enabled is False
        assert config.mysql_host == "localhost"
        assert config.mysql_port == 3306
        assert config.mysql_user == "root"
        assert config.mysql_database == "fmp_cache"
        assert config.mysql_pool_size == 5
        assert config.summarization_enabled is False
        assert config.default_model == "claude-3-haiku-20240307"
        assert config.max_concurrent_requests == 10
        assert config.request_timeout == 30
        assert config.retry_attempts == 3
