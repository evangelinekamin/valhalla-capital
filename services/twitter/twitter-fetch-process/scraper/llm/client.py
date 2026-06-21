import json
import time
import os
from typing import List, Dict, Any, Optional
import logging

import httpx

from .prompts import build_system_prompt, build_batch_prompt

logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemma-4-26b-a4b-it"

# Pricing per million tokens (for cost estimation)
MODEL_PRICING = {
    "google/gemma-4-26b-a4b-it": {"input": 0.13, "output": 0.40},
    "google/gemma-4-31b-it": {"input": 0.14, "output": 0.40},
    "deepseek/deepseek-v3.2": {"input": 0.26, "output": 0.38},
}


class OpenRouterClient:
    """Client for classifying tweets via OpenRouter API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        max_retries: int = 3,
        retry_delay: float = 2.0
    ):
        self.api_key = api_key or os.getenv('OPENROUTER_API_KEY')
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment or provided")

        self.model = os.getenv('LLM_MODEL') or model or DEFAULT_MODEL
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Token counting for cost estimation
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_requests = 0

    def classify_batch(
        self,
        tweets: List[Dict[str, Any]],
        max_tokens: int = 500,
        temperature: float = 0.1
    ) -> List[Dict[str, Any]]:
        """
        Classify a batch of tweets via OpenRouter.

        Args:
            tweets: List of tweet dictionaries with 'username' and 'content'
            max_tokens: Maximum tokens for response
            temperature: Sampling temperature

        Returns:
            List of classification results matching input order
        """
        if not tweets:
            return []

        system_prompt = build_system_prompt()
        user_prompt = build_batch_prompt(tweets)

        for attempt in range(self.max_retries):
            try:
                response = httpx.post(
                    OPENROUTER_API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "X-Title": "Valkyrie Overseer",
                                            },
                    json={
                        "model": self.model,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()

                # Track token usage
                usage = data.get("usage", {})
                self.total_input_tokens += usage.get("prompt_tokens", 0)
                self.total_output_tokens += usage.get("completion_tokens", 0)
                self.total_requests += 1

                # Parse response
                content = data["choices"][0]["message"]["content"]
                results = self._parse_response(content, len(tweets))

                logger.info(
                    f"Classified {len(tweets)} tweets via {self.model}. "
                    f"Tokens: {usage.get('prompt_tokens', '?')} in, "
                    f"{usage.get('completion_tokens', '?')} out"
                )

                return results

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 429:
                    logger.warning(f"Rate limit hit on attempt {attempt + 1}")
                elif status >= 500:
                    logger.warning(f"Server error {status} on attempt {attempt + 1}")
                else:
                    logger.error(f"HTTP error {status} on attempt {attempt + 1}: {e}")
                    raise

                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.info(f"Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    raise

            except httpx.TimeoutException as e:
                logger.warning(f"Timeout on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.info(f"Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    raise

            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                raise

        raise RuntimeError("Max retries exceeded")

    def _parse_response(self, content: str, expected_count: int) -> List[Dict[str, Any]]:
        """Parse JSON response from the model."""
        try:
            content = content.strip()

            # Remove markdown code blocks if present
            if content.startswith('```'):
                lines = content.split('\n')
                json_lines = []
                in_code_block = False
                for line in lines:
                    if line.strip().startswith('```'):
                        in_code_block = not in_code_block
                        continue
                    if in_code_block or not line.strip().startswith('```'):
                        json_lines.append(line)
                content = '\n'.join(json_lines)

            results = json.loads(content)

            if not isinstance(results, list):
                results = [results]

            validated_results = []
            for result in results:
                validated = self._validate_result(result)
                validated_results.append(validated)

            # Pad with fallback results if needed
            while len(validated_results) < expected_count:
                validated_results.append(self._fallback_result())

            return validated_results[:expected_count]

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response content: {content}")
            return [self._fallback_result() for _ in range(expected_count)]

        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            return [self._fallback_result() for _ in range(expected_count)]

    def _validate_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize a classification result."""
        valid_classifications = {'CRITICAL', 'IMPORTANT', 'ROUTINE', 'SKIP'}
        valid_sentiments = {'bullish', 'bearish', 'neutral'}

        classification = result.get('classification', 'ROUTINE').upper()
        if classification not in valid_classifications:
            classification = 'ROUTINE'

        confidence = result.get('confidence', 0.5)
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.5

        tickers = result.get('tickers', [])
        if not isinstance(tickers, list):
            tickers = []

        sentiment = result.get('sentiment', 'neutral').lower()
        if sentiment not in valid_sentiments:
            sentiment = 'neutral'

        reasoning = result.get('reasoning', '')

        return {
            'classification': classification,
            'confidence': confidence,
            'tickers': tickers,
            'sentiment': sentiment,
            'reasoning': reasoning
        }

    def _fallback_result(self) -> Dict[str, Any]:
        """Return fallback result when parsing fails."""
        return {
            'classification': 'ROUTINE',
            'confidence': 0.5,
            'tickers': [],
            'sentiment': 'neutral',
            'reasoning': 'Fallback classification due to parsing error'
        }

    def get_token_usage(self) -> Dict[str, int]:
        """Get total token usage statistics."""
        return {
            'input_tokens': self.total_input_tokens,
            'output_tokens': self.total_output_tokens,
            'total_tokens': self.total_input_tokens + self.total_output_tokens
        }

    def estimate_cost(self) -> Dict[str, float]:
        """Estimate API costs based on token usage."""
        pricing = MODEL_PRICING.get(self.model, {"input": 0.13, "output": 0.40})
        input_cost = (self.total_input_tokens / 1_000_000) * pricing["input"]
        output_cost = (self.total_output_tokens / 1_000_000) * pricing["output"]
        total_cost = input_cost + output_cost

        return {
            'input_cost': round(input_cost, 6),
            'output_cost': round(output_cost, 6),
            'total_cost': round(total_cost, 6)
        }

    def get_usage_stats(self) -> Dict[str, int]:
        """Get usage statistics including request count."""
        return {
            'input_tokens': self.total_input_tokens,
            'output_tokens': self.total_output_tokens,
            'total_tokens': self.total_input_tokens + self.total_output_tokens,
            'total_requests': self.total_requests
        }

    def reset_usage_stats(self):
        """Reset token usage statistics."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_requests = 0


# Backwards compatibility — triage.py imports this name
AnthropicClient = OpenRouterClient
