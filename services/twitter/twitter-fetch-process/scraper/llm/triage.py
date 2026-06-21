import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from .client import AnthropicClient
from .ticker_extractor import TickerExtractor
from .sentiment_analyzer import SentimentAnalyzer

logger = logging.getLogger(__name__)


class TriageEngine:
    """Engine for triaging tweets using LLM classification."""

    def __init__(
        self,
        client: Optional[AnthropicClient] = None,
        config_path: Optional[str] = None
    ):
        """
        Initialize triage engine.

        Args:
            client: AnthropicClient instance (creates new if not provided)
            config_path: Path to triage_config.json (uses default if not provided)
        """
        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'triage_config.json'
        else:
            config_path = Path(config_path)

        with open(config_path, 'r') as f:
            self.config = json.load(f)

        # Initialize client
        if client is None:
            llm_config = self.config['llm']
            self.client = AnthropicClient(
                model=llm_config['model'],
                max_retries=llm_config.get('retry_attempts', 3),
                retry_delay=llm_config.get('retry_delay_seconds', 2)
            )
        else:
            self.client = client

        # Initialize extractors
        max_tickers = self.config.get('extraction', {}).get('max_tickers_per_tweet', 10)
        self.ticker_extractor = TickerExtractor(max_tickers=max_tickers)
        self.sentiment_analyzer = SentimentAnalyzer()

        # Configuration
        self.batch_size = self.config['llm'].get('batch_size', 15)
        self.fallback_classification = self.config.get('fallback', {}).get('on_parse_error', 'ROUTINE')

        # Statistics
        self.stats = {
            'total_processed': 0,
            'classifications': {
                'CRITICAL': 0,
                'IMPORTANT': 0,
                'ROUTINE': 0,
                'SKIP': 0
            },
            'fallback_count': 0,
            'errors': 0
        }

    def process_batch(self, tweets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process a batch of tweets through LLM classification.

        Args:
            tweets: List of tweet dictionaries with:
                - username: Twitter username
                - content: Tweet content
                - (optional) other metadata

        Returns:
            List of enriched tweet dictionaries with:
                - classification: CRITICAL/IMPORTANT/ROUTINE/SKIP
                - confidence: 0.0-1.0
                - tickers: List of ticker symbols
                - sentiment: bullish/bearish/neutral
                - reasoning: LLM explanation
        """
        if not tweets:
            return []

        # Filter only tweets that need triage
        triage_tweets = [
            tweet for tweet in tweets
            if tweet.get('pre_filter_action') == 'triage'
        ]

        if not triage_tweets:
            logger.info("No tweets require LLM triage")
            return tweets

        logger.info(f"Processing {len(triage_tweets)} tweets through LLM")

        # Process in batches
        results = []
        for i in range(0, len(triage_tweets), self.batch_size):
            batch = triage_tweets[i:i + self.batch_size]
            batch_results = self._process_single_batch(batch)
            results.extend(batch_results)

        # Merge results back into original tweets
        enriched_tweets = []
        triage_idx = 0

        for tweet in tweets:
            if tweet.get('pre_filter_action') == 'triage':
                # Add LLM classification results
                enriched_tweet = {**tweet, **results[triage_idx]}
                enriched_tweets.append(enriched_tweet)
                triage_idx += 1
            else:
                # Keep pre-filtered tweets as-is
                enriched_tweets.append(tweet)

        return enriched_tweets

    def _process_single_batch(self, tweets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process a single batch of tweets.

        Args:
            tweets: Batch of tweets to process

        Returns:
            List of classification results
        """
        try:
            # Call LLM API
            llm_results = self.client.classify_batch(
                tweets,
                max_tokens=self.config['llm'].get('max_tokens', 500),
                temperature=self.config['llm'].get('temperature', 0.1)
            )

            # Pad LLM results if fewer than expected
            while len(llm_results) < len(tweets):
                llm_results.append({
                    'classification': self.fallback_classification,
                    'confidence': 0.3,
                    'tickers': [],
                    'sentiment': 'neutral',
                    'reasoning': 'Fallback - missing from LLM response'
                })

            # Enrich results with additional extraction
            enriched_results = []
            for tweet, llm_result in zip(tweets, llm_results):
                enriched = self._enrich_result(tweet, llm_result)
                enriched_results.append(enriched)

                # Update statistics
                self.stats['total_processed'] += 1
                classification = enriched.get('classification', 'ROUTINE')
                self.stats['classifications'][classification] = \
                    self.stats['classifications'].get(classification, 0) + 1

            return enriched_results

        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            self.stats['errors'] += len(tweets)

            # Return fallback results
            return [self._create_fallback_result(tweet) for tweet in tweets]

    VALID_CLASSIFICATIONS = {'CRITICAL', 'IMPORTANT', 'ROUTINE', 'SKIP'}
    VALID_SENTIMENTS = {'bullish', 'bearish', 'neutral'}

    def _enrich_result(
        self,
        tweet: Dict[str, Any],
        llm_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enrich LLM result with additional extraction and validation.

        Args:
            tweet: Original tweet data
            llm_result: LLM classification result

        Returns:
            Enriched and validated result dictionary
        """
        content = tweet.get('content', '')

        # Extract tickers (combine LLM + regex)
        tickers = self.ticker_extractor.extract(content, llm_result)

        # Analyze sentiment (LLM with keyword fallback)
        sentiment = self.sentiment_analyzer.analyze(content, llm_result)

        # Validate classification
        classification = llm_result.get('classification', self.fallback_classification)
        if isinstance(classification, str):
            classification = classification.upper()
        if classification not in self.VALID_CLASSIFICATIONS:
            classification = self.fallback_classification

        # Validate confidence (clamp to 0.0-1.0)
        confidence = llm_result.get('confidence', 0.5)
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.5

        # Validate sentiment
        if sentiment not in self.VALID_SENTIMENTS:
            sentiment = 'neutral'

        return {
            'classification': classification,
            'confidence': confidence,
            'tickers': tickers,
            'sentiment': sentiment,
            'reasoning': llm_result.get('reasoning', ''),
            'processed': True,
        }

    def _create_fallback_result(self, tweet: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create fallback result when LLM fails.

        Args:
            tweet: Original tweet data

        Returns:
            Fallback result dictionary
        """
        self.stats['fallback_count'] += 1

        content = tweet.get('content', '')

        # Use regex-only extraction
        tickers = self.ticker_extractor.extract_with_regex(content)
        sentiment = self.sentiment_analyzer.analyze_with_keywords(content)

        return {
            'classification': self.fallback_classification,
            'confidence': 0.3,
            'tickers': tickers,
            'sentiment': sentiment,
            'reasoning': 'Fallback classification due to LLM error',
            'fallback': True,
            'error': 'LLM classification failed',
        }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get processing statistics.

        Returns:
            Dictionary with processing stats
        """
        token_usage = self.client.get_token_usage()
        cost_estimate = self.client.estimate_cost()

        return {
            **self.stats,
            'token_usage': token_usage,
            'cost_estimate': cost_estimate
        }

    def reset_stats(self):
        """Reset statistics counters."""
        self.stats = {
            'total_processed': 0,
            'classifications': {
                'CRITICAL': 0,
                'IMPORTANT': 0,
                'ROUTINE': 0,
                'SKIP': 0
            },
            'fallback_count': 0,
            'errors': 0
        }
        self.client.reset_usage_stats()

    def log_stats_summary(self):
        """Log a summary of statistics."""
        stats = self.get_stats()

        logger.info("=== Triage Engine Statistics ===")
        logger.info(f"Total processed: {stats['total_processed']}")
        logger.info(f"Classifications: {stats['classifications']}")
        logger.info(f"Fallback count: {stats['fallback_count']}")
        logger.info(f"Errors: {stats['errors']}")
        logger.info(f"Token usage: {stats['token_usage']}")
        logger.info(f"Cost estimate: ${stats['cost_estimate']['total_cost']:.4f}")
