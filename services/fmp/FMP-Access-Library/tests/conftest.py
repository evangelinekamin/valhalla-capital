"""Shared pytest fixtures for FMP Data Client tests."""

import pytest
from fmp_data_client.config import FMPConfig, Tier


@pytest.fixture
def minimal_config() -> FMPConfig:
    """Create a minimal valid configuration for testing."""
    return FMPConfig(
        api_key="test_api_key_12345678",
        tier=Tier.STARTER,
        cache_enabled=False,
        summarization_enabled=False,
    )


@pytest.fixture
def premium_config() -> FMPConfig:
    """Create a premium tier configuration for testing."""
    return FMPConfig(
        api_key="test_api_key_premium",
        tier=Tier.PREMIUM,
        cache_enabled=True,
        mysql_host="localhost",
        mysql_port=3306,
        mysql_user="test_user",
        mysql_password="test_password",
        mysql_database="test_fmp_cache",
        summarization_enabled=False,
    )


@pytest.fixture
def ultimate_config_with_llm() -> FMPConfig:
    """Create an ultimate tier configuration with LLM summarization."""
    return FMPConfig(
        api_key="test_api_key_ultimate",
        tier=Tier.ULTIMATE,
        cache_enabled=True,
        mysql_host="localhost",
        mysql_port=3306,
        mysql_user="test_user",
        mysql_password="test_password",
        mysql_database="test_fmp_cache",
        summarization_enabled=True,
        anthropic_api_key="test_anthropic_key_12345",
    )
