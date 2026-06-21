# utils.py
"""Utilities for retry logic, cost tracking, and content hashing."""
import functools
import hashlib
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# Claude pricing per 1M tokens (as of late 2024, check for updates)
PRICING = {
    'claude-sonnet-4-6': {'input': 3.00, 'output': 15.00},
    'claude-opus-4-5-20251101': {'input': 15.00, 'output': 75.00},
    'claude-haiku-3-5-20241022': {'input': 0.80, 'output': 4.00},
}


def retry_with_backoff(max_retries=3, base_delay=1, max_delay=60, exceptions=(Exception,)):
    """Decorator for exponential backoff retry logic."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        break

                    # Exponential backoff with jitter
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    delay += delay * 0.1 * (hash(str(e)) % 10) / 10

                    logger.warning(f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s: {e}")
                    time.sleep(delay)

            raise last_exception
        return wrapper
    return decorator


def calculate_cost(model, input_tokens, output_tokens):
    """Calculate cost in USD for a Claude API call."""
    if model not in PRICING:
        # Default to sonnet pricing if unknown model
        model = 'claude-sonnet-4-6'

    rates = PRICING[model]
    input_cost = (input_tokens / 1_000_000) * rates['input']
    output_cost = (output_tokens / 1_000_000) * rates['output']

    return input_cost + output_cost


def content_hash(text):
    """Generate a hash for deduplication."""
    normalized = ' '.join(text.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


class CostTracker:
    """Track API costs across a session."""

    def __init__(self, conn):
        self.conn = conn
        self.session_start = datetime.now()
        self.session_costs = []

    def log_call(self, model, input_tokens, output_tokens, purpose=''):
        cost = calculate_cost(model, input_tokens, output_tokens)

        self.conn.execute('''
            INSERT INTO api_costs (model, input_tokens, output_tokens, cost_usd, purpose)
            VALUES (?, ?, ?, ?, ?)
        ''', (model, input_tokens, output_tokens, cost, purpose))
        self.conn.commit()

        self.session_costs.append(cost)
        return cost

    def session_total(self):
        return sum(self.session_costs)

    def all_time_total(self):
        row = self.conn.execute('SELECT SUM(cost_usd) FROM api_costs').fetchone()
        return row[0] or 0

    def print_summary(self):
        print(f"\n=== Cost Summary ===")
        print(f"This session: ${self.session_total():.4f}")
        print(f"All time:     ${self.all_time_total():.4f}")

        rows = self.conn.execute('''
            SELECT purpose, SUM(cost_usd), COUNT(*)
            FROM api_costs
            GROUP BY purpose
        ''').fetchall()

        if rows:
            print(f"\nBy purpose:")
            for purpose, total, count in rows:
                print(f"  {purpose or 'unknown'}: ${total:.4f} ({count} calls)")
