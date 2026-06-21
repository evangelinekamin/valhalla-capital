"""Base summarizer class using Claude (Anthropic API)."""

import logging
from typing import Optional
from anthropic import AsyncAnthropic

from fmp_data_client.config import FMPConfig

logger = logging.getLogger(__name__)


class BaseSummarizer:
    """
    Base class for LLM-powered summarization using Claude.

    Provides common functionality for all summarizers including:
    - Anthropic API client management
    - Token usage tracking
    - Error handling
    - Model selection

    Attributes:
        config: FMP configuration with Anthropic API key
        client: Async Anthropic client
        model: Claude model to use for summarization
    """

    def __init__(
        self,
        config: FMPConfig,
        model: Optional[str] = None,
    ) -> None:
        """
        Initialize base summarizer.

        Args:
            config: FMP configuration with anthropic_api_key
            model: Claude model to use (defaults to config.default_model)

        Raises:
            ValueError: If summarization is not enabled in config
        """
        if not config.summarization_enabled:
            raise ValueError(
                "Summarization is not enabled. Set summarization_enabled=True "
                "and provide anthropic_api_key in config."
            )

        if not config.anthropic_api_key:
            raise ValueError("anthropic_api_key is required for summarization")

        self.config = config
        self.model = model or config.default_model
        self.client = AsyncAnthropic(api_key=config.anthropic_api_key)

        # Token usage tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0

        logger.info(f"Initialized {self.__class__.__name__} with model {self.model}")

    async def _call_claude(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        """
        Call Claude API with given prompt.

        Args:
            prompt: User prompt/content to summarize
            system_prompt: Optional system prompt for instruction
            max_tokens: Maximum tokens in response

        Returns:
            Claude's response text

        Raises:
            Exception: If API call fails
        """
        try:
            logger.debug(f"Calling Claude API with model {self.model}")
            logger.debug(f"Prompt length: {len(prompt)} characters")

            # Build messages
            messages = [{"role": "user", "content": prompt}]

            # Call Claude API
            kwargs = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": messages,
            }

            if system_prompt:
                kwargs["system"] = system_prompt

            response = await self.client.messages.create(**kwargs)

            # Track token usage
            self.total_input_tokens += response.usage.input_tokens
            self.total_output_tokens += response.usage.output_tokens

            logger.info(
                f"Claude API call successful. "
                f"Input tokens: {response.usage.input_tokens}, "
                f"Output tokens: {response.usage.output_tokens}"
            )

            # Extract text from response
            content = response.content[0].text

            return content

        except Exception as e:
            logger.error(f"Error calling Claude API: {e}")
            raise

    def get_token_usage(self) -> dict[str, int]:
        """
        Get total token usage statistics.

        Returns:
            Dictionary with input_tokens, output_tokens, and total_tokens
        """
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
        }

    def reset_token_usage(self) -> None:
        """Reset token usage counters."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        logger.debug("Token usage counters reset")

    async def close(self) -> None:
        """Close the Anthropic client."""
        await self.client.close()
        logger.debug("Anthropic client closed")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
