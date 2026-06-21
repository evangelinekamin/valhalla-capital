#!/usr/bin/env python3
"""
Test LLM connection and estimate costs.

Usage:
    python test_llm_connection.py [options]

Examples:
    python test_llm_connection.py --sample-size 10
    python test_llm_connection.py --test-batch
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Dict

# Add scraper to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.llm import AnthropicClient, TriageEngine


# Sample tweets for testing
SAMPLE_TWEETS = [
    {
        "username": "elonmusk",
        "content": "Tesla Q4 deliveries exceeded expectations. Production scaling nicely. $TSLA"
    },
    {
        "username": "BillAckman",
        "content": "Pershing Square has taken a significant position in a new company. Details to follow next week."
    },
    {
        "username": "crypto_pumper",
        "content": "🚀🚀🚀 TO THE MOON! 100X GEM! BUY NOW! 🔥🔥🔥 #crypto #moonshot"
    },
    {
        "username": "unusual_whales",
        "content": "Unusual options activity detected: AAPL 200 strike calls, volume 10,000+, expiry 30 days"
    },
    {
        "username": "random_user",
        "content": "Good morning! Hope everyone has a great day trading today!"
    },
    {
        "username": "MarketWatch",
        "content": "BREAKING: Federal Reserve announces emergency rate cut of 50 basis points amid economic concerns"
    },
    {
        "username": "analyst123",
        "content": "Technical analysis on $SPY shows potential breakout pattern forming. Watch resistance at 450."
    },
    {
        "username": "spam_account",
        "content": "RT @someone Check out my amazing trading course! Limited time offer! Click here -> bit.ly/scam123"
    },
    {
        "username": "GerberKawasaki",
        "content": "Apple's AI strategy is misunderstood by the market. $AAPL has significant upside from here."
    },
    {
        "username": "news_bot",
        "content": "Microsoft announces layoffs affecting 10,000 employees as part of restructuring. $MSFT down 3% premarket."
    }
]


def test_connection(api_key: str) -> bool:
    """
    Test basic API connection.

    Args:
        api_key: Anthropic API key

    Returns:
        True if connection successful
    """
    try:
        print("Testing API connection...")
        client = AnthropicClient(api_key=api_key)

        # Simple test with 1 tweet
        result = client.classify_batch([SAMPLE_TWEETS[0]], max_tokens=200)

        print("✓ Connection successful!")
        print(f"  Model: {client.model}")
        print(f"  Test result: {result[0]['classification']}")

        return True

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False


def test_batch_processing(api_key: str, sample_size: int = 10):
    """
    Test batch processing and get cost estimates.

    Args:
        api_key: Anthropic API key
        sample_size: Number of sample tweets to process
    """
    try:
        print(f"\nTesting batch processing with {sample_size} tweets...")

        # Create triage engine
        engine = TriageEngine()

        # Prepare sample tweets
        sample = SAMPLE_TWEETS[:sample_size]

        # Mark all as needing triage
        for tweet in sample:
            tweet['pre_filter_action'] = 'triage'

        # Process batch
        results = engine.process_batch(sample)

        # Display results
        print(f"\n{'='*70}")
        print("Classification Results:")
        print(f"{'='*70}")

        for i, (tweet, result) in enumerate(zip(sample, results), 1):
            print(f"\n[{i}] @{tweet['username']}")
            print(f"    Content: {tweet['content'][:60]}...")
            print(f"    Classification: {result.get('classification', 'N/A')}")
            print(f"    Confidence: {result.get('confidence', 0):.2f}")
            print(f"    Tickers: {result.get('tickers', [])}")
            print(f"    Sentiment: {result.get('sentiment', 'N/A')}")

        # Get statistics
        stats = engine.get_stats()

        print(f"\n{'='*70}")
        print("Statistics:")
        print(f"{'='*70}")
        print(f"Total processed: {stats['total_processed']}")
        print(f"\nClassification breakdown:")
        for classification, count in stats['classifications'].items():
            print(f"  {classification}: {count}")

        print(f"\nToken usage:")
        print(f"  Input tokens: {stats['token_usage']['input_tokens']:,}")
        print(f"  Output tokens: {stats['token_usage']['output_tokens']:,}")
        print(f"  Total tokens: {stats['token_usage']['total_tokens']:,}")

        print(f"\nCost estimate:")
        print(f"  Input cost: ${stats['cost_estimate']['input_cost']:.4f}")
        print(f"  Output cost: ${stats['cost_estimate']['output_cost']:.4f}")
        print(f"  Total cost: ${stats['cost_estimate']['total_cost']:.4f}")

        # Extrapolate costs
        tweets_per_day = 10000
        tweets_after_filter = int(tweets_per_day * 0.2)  # 80% filtered
        batches_per_day = tweets_after_filter / sample_size

        daily_cost = stats['cost_estimate']['total_cost'] * batches_per_day
        monthly_cost = daily_cost * 30

        print(f"\n{'='*70}")
        print("Cost Projections (with 80% pre-filter):")
        print(f"{'='*70}")
        print(f"Assumed tweets/day: {tweets_per_day:,}")
        print(f"After 80% filter: {tweets_after_filter:,}")
        print(f"Est. daily cost: ${daily_cost:.2f}")
        print(f"Est. monthly cost: ${monthly_cost:.2f}")

    except Exception as e:
        print(f"\n✗ Error during batch processing: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test LLM connection and estimate costs"
    )
    parser.add_argument(
        '--api-key',
        default=os.getenv('ANTHROPIC_API_KEY'),
        help="Anthropic API key (default: ANTHROPIC_API_KEY env var)"
    )
    parser.add_argument(
        '--sample-size',
        type=int,
        default=10,
        help="Number of sample tweets to test (default: 10)"
    )
    parser.add_argument(
        '--test-batch',
        action='store_true',
        help="Test batch processing with cost estimates"
    )

    args = parser.parse_args()

    # Validate API key
    if not args.api_key:
        print("Error: Anthropic API key not provided", file=sys.stderr)
        print("Set ANTHROPIC_API_KEY environment variable or use --api-key", file=sys.stderr)
        sys.exit(1)

    print("="*70)
    print("LLM Connection Test")
    print("="*70)

    # Test basic connection
    if not test_connection(args.api_key):
        sys.exit(1)

    # Test batch processing if requested
    if args.test_batch:
        test_batch_processing(args.api_key, args.sample_size)

    print(f"\n{'='*70}")
    print("✓ All tests completed!")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
