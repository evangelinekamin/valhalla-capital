import logging
import os
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

import requests
from sqlalchemy.orm import Session

from db.connection import get_engine, session_scope
from db.schema import Tweet
from filters.pre_filter import PreFilter
from filters import patterns
from llm.triage import TriageEngine

logger = logging.getLogger(__name__)


class MinifluxClient:
    """Client for Miniflux RSS reader API with retry logic."""

    def __init__(self, base_url: str, api_key: str, max_retries: int = 3):
        """
        Initialize Miniflux client.

        Args:
            base_url: Miniflux base URL
            api_key: Miniflux API key
            max_retries: Maximum retry attempts for transient failures
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            'X-Auth-Token': self.api_key
        })

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Make HTTP request with retry logic for transient failures.

        Args:
            method: HTTP method (get, put, post)
            url: Request URL
            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            requests.RequestException: After all retries exhausted
        """
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = getattr(self.session, method)(url, **kwargs)
                response.raise_for_status()
                return response
            except requests.ConnectionError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = 2 ** (attempt + 1)
                    logger.warning(f"Miniflux connection error (attempt {attempt + 1}), retrying in {delay}s: {e}")
                    time.sleep(delay)
            except requests.Timeout as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = 2 ** (attempt + 1)
                    logger.warning(f"Miniflux timeout (attempt {attempt + 1}), retrying in {delay}s: {e}")
                    time.sleep(delay)
            except requests.HTTPError as e:
                # Don't retry client errors (4xx), only server errors (5xx)
                if e.response is not None and e.response.status_code < 500:
                    raise
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = 2 ** (attempt + 1)
                    logger.warning(f"Miniflux server error (attempt {attempt + 1}), retrying in {delay}s: {e}")
                    time.sleep(delay)
        raise last_error

    def get_unread_entries(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get unread entries from Miniflux.

        Args:
            limit: Maximum number of entries to fetch

        Returns:
            List of entry dictionaries
        """
        response = self._request_with_retry(
            'get',
            f"{self.base_url}/v1/entries",
            params={
                'status': 'unread',
                'limit': limit,
                'order': 'published_at',
                'direction': 'desc'
            },
            timeout=30,
        )
        data = response.json()
        return data.get('entries', [])

    def mark_entries_read(self, entry_ids: List[int]):
        """
        Mark entries as read.

        Args:
            entry_ids: List of entry IDs to mark as read
        """
        if not entry_ids:
            return

        self._request_with_retry(
            'put',
            f"{self.base_url}/v1/entries",
            json={
                'entry_ids': entry_ids,
                'status': 'read'
            },
            timeout=30,
        )


class ProcessingPipeline:
    """Main processing pipeline for tweet classification."""

    def __init__(
        self,
        miniflux_url: Optional[str] = None,
        miniflux_api_key: Optional[str] = None,
        filter_config_path: Optional[str] = None,
        account_config_path: Optional[str] = None
    ):
        """
        Initialize processing pipeline.

        Args:
            miniflux_url: Miniflux URL (defaults to env var)
            miniflux_api_key: Miniflux API key (defaults to env var)
            filter_config_path: Path to filter config
            account_config_path: Path to account config
        """
        # Initialize Miniflux client
        # Local default targets host-mapped Miniflux port from docker-compose.
        # In-container deployments should set MINIFLUX_URL explicitly
        # (e.g. http://miniflux:8080).
        self.miniflux_url = miniflux_url or os.getenv('MINIFLUX_URL', 'http://localhost:8081')
        self.miniflux_api_key = miniflux_api_key or os.getenv('MINIFLUX_API_KEY')

        if not self.miniflux_api_key:
            raise ValueError("MINIFLUX_API_KEY not found in environment")

        self.miniflux = MinifluxClient(self.miniflux_url, self.miniflux_api_key)

        # Initialize pre-filter
        self.pre_filter = PreFilter(
            filter_config_path=filter_config_path,
            account_config_path=account_config_path
        )

        # Initialize triage engine
        self.triage_engine = TriageEngine()

        # Initialize database
        self.engine = get_engine()

        # Statistics
        self.stats = {
            'total_fetched': 0,
            'total_stored': 0,
            'pre_filter_skip': 0,
            'pre_filter_accept': 0,
            'pre_filter_triage': 0,
            'pre_filter_extract_only': 0,
            'llm_processed': 0,
            'skipped_at_storage': 0,
            'errors': 0
        }

    def process_batch(self, limit: int = 100) -> Dict[str, Any]:
        """
        Process a batch of unread entries.

        Pipeline stages:
        1. Fetch unread entries from Miniflux
        2. Pre-filter entries (skip/accept/triage)
        3. Batch triage for entries needing LLM
        4. Store to database with all fields
        5. Mark as read in Miniflux

        Args:
            limit: Maximum number of entries to process

        Returns:
            Processing statistics
        """
        logger.info(f"Starting batch processing (limit={limit})")

        try:
            # Stage 1: Fetch unread entries
            entries = self.miniflux.get_unread_entries(limit=limit)
            self.stats['total_fetched'] += len(entries)

            if not entries:
                logger.info("No unread entries to process")
                return self.stats

            logger.info(f"Fetched {len(entries)} unread entries")

            # Stage 2: Pre-filter entries
            filtered_entries = self._pre_filter_entries(entries)

            # Stage 2b: Separate extract_only entries
            extract_entries = [
                e for e in filtered_entries
                if e.get('pre_filter_action') == 'extract_only'
            ]
            non_extract_entries = [
                e for e in filtered_entries
                if e.get('pre_filter_action') != 'extract_only'
            ]

            # Stage 3a: Process extract_only with regex (no LLM)
            processed_extract = self._process_extract_only(extract_entries)

            # Stage 3b: Batch triage for entries needing LLM
            triaged_entries = self._triage_entries(non_extract_entries)

            # Stage 3c: Recombine and apply Tier 1 classification boost
            all_entries = triaged_entries + processed_extract
            all_entries = self._apply_tier1_boost(all_entries)

            # Stage 4: Store to database
            stored_ids = self._store_entries(all_entries)

            self.stats['total_stored'] += len(stored_ids)

            # Stage 5: Mark as read
            entry_ids = [entry['id'] for entry in entries]
            self.miniflux.mark_entries_read(entry_ids)

            logger.info(f"Marked {len(entry_ids)} entries as read")

            # Log statistics
            self._log_stats()

            return self.stats

        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            self.stats['errors'] += 1
            raise

    def _pre_filter_entries(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply pre-filter to entries.

        Args:
            entries: List of Miniflux entries

        Returns:
            Filtered entries with pre_filter_action and pre_filter_reason
        """
        filtered = []

        for entry in entries:
            # Extract username from feed title or URL
            username = self._extract_username(entry)
            content = entry.get('content', '') or entry.get('title', '')

            # Apply pre-filter
            filter_result = self.pre_filter.filter_tweet(username, content)

            # Add filter result to entry
            entry['pre_filter_action'] = filter_result['action']
            entry['pre_filter_reason'] = filter_result['reason']
            entry['username'] = username
            entry['tier'] = filter_result.get('tier', 'tier_2')
            if filter_result.get('author_context'):
                entry['author_context'] = filter_result['author_context']

            # Update stats
            action = filter_result['action']
            if action == 'skip':
                self.stats['pre_filter_skip'] += 1
            elif action == 'accept':
                self.stats['pre_filter_accept'] += 1
            elif action == 'triage':
                self.stats['pre_filter_triage'] += 1
            elif action == 'extract_only':
                self.stats['pre_filter_extract_only'] += 1

            filtered.append(entry)

        logger.info(
            f"Pre-filter: skip={self.stats['pre_filter_skip']}, "
            f"accept={self.stats['pre_filter_accept']}, "
            f"triage={self.stats['pre_filter_triage']}"
        )

        return filtered

    def _triage_entries(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply LLM triage to entries needing classification.

        Args:
            entries: Pre-filtered entries

        Returns:
            Entries with LLM classification results
        """
        # Process through triage engine
        triaged = self.triage_engine.process_batch(entries)

        # Count LLM-processed entries
        llm_count = sum(1 for e in triaged if e.get('pre_filter_action') == 'triage')
        self.stats['llm_processed'] += llm_count

        logger.info(f"LLM processed {llm_count} entries")

        return triaged

    # Classification boost map for Tier 1 accounts
    CLASSIFICATION_BOOST = {
        'SKIP': 'ROUTINE',
        'ROUTINE': 'IMPORTANT',
        'IMPORTANT': 'CRITICAL',
        'CRITICAL': 'CRITICAL',
    }

    def _process_extract_only(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process extract_only entries with regex-only extraction (no LLM).

        Args:
            entries: Flow data entries

        Returns:
            Entries with regex-extracted tickers and metadata
        """
        processed = []
        for entry in entries:
            content = entry.get('content', '') or entry.get('title', '')
            tickers = patterns.extract_tickers_regex(content)

            entry['classification'] = 'ROUTINE'
            entry['confidence'] = 0.5
            entry['tickers'] = tickers
            entry['sentiment'] = 'neutral'
            entry['reasoning'] = f'Flow data extraction: {len(tickers)} tickers'
            entry['processed'] = True
            processed.append(entry)

        if processed:
            logger.info(f"Processed {len(processed)} extract_only entries with regex")

        return processed

    def _apply_tier1_boost(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Boost classification one level for Tier 1 accounts.

        Args:
            entries: All processed entries

        Returns:
            Entries with boosted classifications for Tier 1
        """
        for entry in entries:
            if entry.get('tier') == 'tier_1':
                original = entry.get('classification', 'ROUTINE')
                boosted = self.CLASSIFICATION_BOOST.get(original, original)
                if boosted != original:
                    entry['pre_boost_classification'] = original
                    entry['classification'] = boosted
                    logger.debug(
                        f"T1 boost for {entry.get('username')}: "
                        f"{original} -> {boosted}"
                    )
        return entries

    def _store_entries(self, entries: List[Dict[str, Any]]) -> List[int]:
        """
        Store entries to database, excluding pre-filtered SKIPs and LLM-classified SKIPs.

        Args:
            entries: Processed entries with all fields

        Returns:
            List of stored tweet IDs
        """
        stored_ids = []

        # Filter out entries that should not be stored
        storable_entries = [
            entry for entry in entries
            if entry.get('pre_filter_action') != 'skip'
            and entry.get('classification') != 'SKIP'
        ]

        skipped_count = len(entries) - len(storable_entries)
        if skipped_count > 0:
            logger.info(f"Filtered out {skipped_count} entries (pre-filter SKIP or LLM SKIP)")
            self.stats['skipped_at_storage'] += skipped_count

        with session_scope(self.engine) as session:
            for entry in storable_entries:
                try:
                    tweet = self._create_tweet_from_entry(entry, session)

                    if tweet:
                        session.add(tweet)
                        stored_ids.append(entry['id'])

                except Exception as e:
                    logger.error(f"Error storing entry {entry.get('id')}: {e}")
                    self.stats['errors'] += 1

        logger.info(f"Stored {len(stored_ids)} tweets to database")

        return stored_ids

    def _create_tweet_from_entry(
        self,
        entry: Dict[str, Any],
        session: Session
    ) -> Optional[Tweet]:
        """
        Create Tweet object from Miniflux entry.

        Args:
            entry: Miniflux entry
            session: Database session

        Returns:
            Tweet object or None if already exists
        """
        miniflux_id = entry['id']

        # Check if already exists
        existing = session.query(Tweet).filter(
            Tweet.miniflux_id == miniflux_id
        ).first()

        if existing:
            logger.debug(f"Tweet {miniflux_id} already exists, skipping")
            return None

        # Parse published_at
        published_at = None
        if entry.get('published_at'):
            try:
                published_at = datetime.fromisoformat(
                    entry['published_at'].replace('Z', '+00:00')
                )
            except Exception as e:
                logger.warning(f"Failed to parse published_at: {e}")

        # Create tweet
        tweet = Tweet(
            miniflux_id=miniflux_id,
            feed_id=entry.get('feed_id'),
            tweet_id=self._extract_tweet_id(entry),
            username=entry.get('username'),
            title=entry.get('title'),
            content=entry.get('content'),
            url=entry.get('url'),
            published_at=published_at,
            pre_filter_action=entry.get('pre_filter_action'),
            pre_filter_reason=entry.get('pre_filter_reason'),
            tier=entry.get('tier'),
            classification=entry.get('classification'),
            confidence=entry.get('confidence'),
            tickers=entry.get('tickers'),
            sentiment=entry.get('sentiment'),
            processed=True,
            processed_at=datetime.now()
        )

        return tweet

    def _extract_username(self, entry: Dict[str, Any]) -> str:
        """
        Extract Twitter username from entry.

        Args:
            entry: Miniflux entry

        Returns:
            Username (without @)
        """
        # Try feed title (often contains username)
        feed_title = entry.get('feed', {}).get('title', '')
        if feed_title:
            # Nitter format: "Display Name / handle"
            if ' / ' in feed_title:
                username = feed_title.split(' / ')[-1].replace('@', '').strip()
            else:
                # Legacy format: "handle / Twitter" or plain handle
                username = feed_title.replace(' / Twitter', '').replace('@', '').strip()
            if username:
                return username

        # Try extracting from URL
        url = entry.get('url', '')
        if 'twitter.com/' in url or 'nitter' in url:
            parts = url.split('/')
            for i, part in enumerate(parts):
                if part in ['twitter.com', 'nitter', 'nitter:8080'] and i + 1 < len(parts):
                    return parts[i + 1]

        return 'unknown'

    def _extract_tweet_id(self, entry: Dict[str, Any]) -> Optional[str]:
        """
        Extract tweet ID from entry URL.

        Args:
            entry: Miniflux entry

        Returns:
            Tweet ID or None
        """
        url = entry.get('url', '')
        if '/status/' in url:
            parts = url.split('/status/')
            if len(parts) > 1:
                tweet_id = parts[1].split('?')[0].split('#')[0]
                return tweet_id

        return None

    def _log_stats(self):
        """Log processing statistics."""
        logger.info("="*50)
        logger.info("Processing Statistics:")
        logger.info(f"  Total fetched: {self.stats['total_fetched']}")
        logger.info(f"  Pre-filter:")
        logger.info(f"    Skip: {self.stats['pre_filter_skip']}")
        logger.info(f"    Accept: {self.stats['pre_filter_accept']}")
        logger.info(f"    Triage: {self.stats['pre_filter_triage']}")
        logger.info(f"    ExtractOnly: {self.stats['pre_filter_extract_only']}")
        logger.info(f"  LLM processed: {self.stats['llm_processed']}")
        logger.info(f"  Skipped at storage: {self.stats['skipped_at_storage']}")
        logger.info(f"  Total stored: {self.stats['total_stored']}")
        logger.info(f"  Errors: {self.stats['errors']}")

        # Calculate skip rate
        if self.stats['total_fetched'] > 0:
            skip_rate = self.stats['pre_filter_skip'] / self.stats['total_fetched']
            logger.info(f"  Pre-filter skip rate: {skip_rate:.1%}")

        logger.info("="*50)

        # Log triage engine stats
        self.triage_engine.log_stats_summary()

    def get_stats(self) -> Dict[str, Any]:
        """
        Get processing statistics.

        Returns:
            Statistics dictionary
        """
        return {
            **self.stats,
            'triage_stats': self.triage_engine.get_stats()
        }

    def reset_stats(self):
        """Reset statistics counters."""
        self.stats = {
            'total_fetched': 0,
            'total_stored': 0,
            'pre_filter_skip': 0,
            'pre_filter_accept': 0,
            'pre_filter_triage': 0,
            'pre_filter_extract_only': 0,
            'llm_processed': 0,
            'skipped_at_storage': 0,
            'errors': 0
        }
        self.pre_filter.reset_stats()
        self.triage_engine.reset_stats()
