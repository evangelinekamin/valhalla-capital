import feedparser
import asyncio
import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, time, timedelta
import pytz
import requests

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

sys.path.insert(0, str(Path(__file__).parent))

try:
    import httpx
except ImportError:
    print("[ERROR] httpx package not installed")
    print("Run: pip install httpx")
    sys.exit(1)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_TRIAGE_MODEL = "google/gemma-4-26b-a4b-it"

from alert_manager import AlertManager
from discord_notifier import DiscordNotifier

class NewsWorker:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "feeds.json"
        self.config_path = Path(config_path)

        # Load configuration
        self.config = self._load_config()
        self.rss_feeds = self._get_enabled_feeds()

        # Resolve OpenRouter API key: env var first, config fallback
        openrouter_key = os.getenv('OPENROUTER_API_KEY') or self.config.get('openrouter_api_key')
        if not openrouter_key:
            raise ValueError(
                "OpenRouter API key not set. Set OPENROUTER_API_KEY env var "
                "or add 'openrouter_api_key' to config/feeds.json."
            )
        self.openrouter_api_key = openrouter_key
        self.triage_model = os.getenv('TRIAGE_MODEL', DEFAULT_TRIAGE_MODEL)

        self.alert_manager = AlertManager()

        # Discord notifications: config file first, env var fallback
        discord_webhook_url = self.config.get('discord_webhook_url') or os.getenv('DISCORD_WEBHOOK_URL')
        self.discord = DiscordNotifier(webhook_url=discord_webhook_url)
        self._last_summary_date = None

        # Deduplication tracking (persisted to disk)
        self.seen_file = Path(__file__).parent.parent / "data" / "seen_articles.json"
        self.seen_urls = {}       # url -> datetime
        self.seen_headlines = {}  # headline_hash -> datetime
        self._load_seen()

        # Market hours configuration
        self.feed_fetch_timeout = self.config.get('feed_fetch_timeout', 15)
        self.market_config = self.config.get('market_hours', {})
        self.timezone = pytz.timezone(self.market_config.get('timezone', 'America/New_York'))

        market_hours_str = f"{self.market_config.get('start_time')} - {self.market_config.get('end_time')} ET"
        print(f"[INFO] Loaded {len(self.rss_feeds)} RSS feeds from config")
        print(f"[INFO] Market hours: {market_hours_str}")

        self.discord.notify_startup(len(self.rss_feeds), market_hours_str)

    def _load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            return config
        except FileNotFoundError:
            print(f"[WARN] Config file not found at {self.config_path}, using defaults")
            return self._get_default_config()
        except json.JSONDecodeError as e:
            print(f"[WARN] Error parsing config file: {e}, using defaults")
            return self._get_default_config()

    def _get_default_config(self):
        return {
            "anthropic_api_key": "",
            "discord_webhook_url": "",
            "feeds": [
                {
                    "name": "Google News - All",
                    "url": "https://news.google.com/rss/",
                    "priority": 1,
                    "enabled": True
                }
            ],
            "market_hours": {
                "timezone": "America/New_York",
                "trading_days": [0, 1, 2, 3, 4],
                "start_time": "09:30",
                "end_time": "16:00",
                "check_interval_market": 5,
                "check_interval_off_market": 30
            },
            "deduplication": {
                "enabled": True,
                "lookback_hours": 24,
                "similarity_threshold": 0.85
            },
            "max_articles_per_feed": 10,
            "feed_fetch_timeout": 15
        }

    def _get_enabled_feeds(self):
        feeds = self.config.get('feeds', [])
        enabled_feeds = [
            {
                'name': feed['name'],
                'url': feed['url'],
                'priority': feed.get('priority', 2)
            }
            for feed in feeds
            if feed.get('enabled', True)
        ]
        return sorted(enabled_feeds, key=lambda x: x['priority'])

    def _is_market_hours(self) -> bool:
        now = datetime.now(self.timezone)

        trading_days = self.market_config.get('trading_days', [0, 1, 2, 3, 4])
        if now.weekday() not in trading_days:
            return False

        start_time_str = self.market_config.get('start_time', '09:30')
        end_time_str = self.market_config.get('end_time', '16:00')

        start_hour, start_min = map(int, start_time_str.split(':'))
        end_hour, end_min = map(int, end_time_str.split(':'))

        market_open = time(start_hour, start_min)
        market_close = time(end_hour, end_min)

        current_time = now.time()

        return market_open <= current_time <= market_close

    def _get_check_interval(self) -> int:
        if self._is_market_hours():
            interval = self.market_config.get('check_interval_market', 5)
            print(f"[INFO] Market hours - checking every {interval} minutes")
            return interval
        else:
            interval = self.market_config.get('check_interval_off_market', 30)
            print(f"[INFO] Off-market hours - checking every {interval} minutes")
            return interval

    def _hash_headline(self, headline: str) -> str:
        normalized = headline.lower()
        for word in ['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for']:
            normalized = normalized.replace(f' {word} ', ' ')

        normalized = ''.join(c for c in normalized if c.isalnum() or c.isspace())

        return hashlib.md5(normalized.encode()).hexdigest()

    def _load_seen(self):
        if not self.seen_file.exists():
            return
        try:
            data = json.loads(self.seen_file.read_text())
            for url, ts in data.get('urls', {}).items():
                self.seen_urls[url] = datetime.fromisoformat(ts)
            for h, ts in data.get('headlines', {}).items():
                self.seen_headlines[h] = datetime.fromisoformat(ts)
            self._prune_seen()
            print(f"[INFO] Loaded dedup cache: {len(self.seen_urls)} URLs, {len(self.seen_headlines)} headlines")
        except Exception as e:
            print(f"[WARN] Failed to load dedup cache: {e}")

    def _save_seen(self):
        self._prune_seen()
        data = {
            'urls': {url: ts.isoformat() for url, ts in self.seen_urls.items()},
            'headlines': {h: ts.isoformat() for h, ts in self.seen_headlines.items()}
        }
        try:
            self.seen_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.seen_file.with_suffix('.tmp')
            tmp.write_text(json.dumps(data))
            tmp.rename(self.seen_file)
        except Exception as e:
            print(f"[WARN] Failed to save dedup cache: {e}")

    def _prune_seen(self):
        lookback_hours = self.config.get('deduplication', {}).get('lookback_hours', 24)
        cutoff = datetime.now() - timedelta(hours=lookback_hours)
        self.seen_urls = {k: v for k, v in self.seen_urls.items() if v >= cutoff}
        self.seen_headlines = {k: v for k, v in self.seen_headlines.items() if v >= cutoff}

    def _is_duplicate(self, article: dict) -> bool:
        dedup_config = self.config.get('deduplication', {})

        if not dedup_config.get('enabled', True):
            return False

        url = article['url']
        headline = article['headline']
        lookback = timedelta(hours=dedup_config.get('lookback_hours', 24))
        now = datetime.now()

        if url in self.seen_urls and now - self.seen_urls[url] < lookback:
            return True

        headline_hash = self._hash_headline(headline)
        if headline_hash in self.seen_headlines and now - self.seen_headlines[headline_hash] < lookback:
            return True

        return False

    def _mark_as_seen(self, article: dict):
        now = datetime.now()
        self.seen_urls[article['url']] = now
        self.seen_headlines[self._hash_headline(article['headline'])] = now

    async def classify_article(self, article: dict) -> str:
        prompt = f"""You are a news triage agent. Classify this news article into one of three categories:

CRITICAL - Requires immediate processing (minutes matter):
- Market circuit breakers triggered or imminent
- >2% moves in S&P 500/DJIA within 1 hour
- Fed emergency actions or unscheduled announcements
- Geopolitical events directly affecting US markets (wars involving major economies, attacks on US soil)
- Bankruptcy/default of systemically important institutions
- Major cybersecurity incidents affecting financial infrastructure

IMPORTANT - Include in next scheduled digest:
- Scheduled Fed decisions and economic data releases
- Earnings from large-cap companies
- >1% daily moves in major indices
- Significant M&A announcements
- Policy/regulatory changes affecting markets
- Geopolitical developments in major economies

ROUTINE - Archive only:
- Standard news cycle coverage
- Opinion/analysis pieces
- Minor corporate updates
- Entertainment/celebrity news
- Local news without market implications

Rules:
- When uncertain, choose the MORE urgent category
- Classify on actual events described, not headline sensationalism
- A "market crash" headline describing a 0.5% move = ROUTINE

Article:
Headline: {article['headline']}
Summary: {article.get('summary', 'N/A')}
Source: {article['source']}

Respond with ONLY one word: CRITICAL, IMPORTANT, or ROUTINE"""

        response = httpx.post(
            OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "Content-Type": "application/json",
                "X-Title": "Valkyrie Overseer",
                            },
            json={
                "model": self.triage_model,
                "max_tokens": 20,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        classification = data["choices"][0]["message"]["content"].strip().upper()

        if classification not in ['CRITICAL', 'IMPORTANT', 'ROUTINE']:
            print(f"[WARN] Invalid classification '{classification}', defaulting to ROUTINE")
            return 'ROUTINE'

        return classification

    async def fetch_full_article(self, url: str) -> str:
        try:
            from bs4 import BeautifulSoup

            response = requests.get(url, timeout=10, headers={
                'User-Agent': DEFAULT_USER_AGENT
            })
            soup = BeautifulSoup(response.content, 'html.parser')

            paragraphs = soup.find_all('p')
            text = ' '.join([p.get_text() for p in paragraphs[:10]])
            return text[:3000]
        except Exception as e:
            print(f"[WARN] Failed to fetch article: {e}")
            return ""

    async def process_article(self, article: dict):
        if self._is_duplicate(article):
            print(f"[SKIP-DUP] {article['headline'][:60]}...")
            return

        self._mark_as_seen(article)

        classification = await self.classify_article(article)

        print(f"[{classification}] {article['headline'][:60]}...")

        if classification == "CRITICAL":
            full_text = await self.fetch_full_article(article['url'])
            article['full_text'] = full_text
            self.alert_manager.add_critical_alert(article)
            self.discord.notify_critical_alert(article)

    async def fetch_and_process_feeds(self):
        now = datetime.now(self.timezone)
        market_status = "MARKET HOURS" if self._is_market_hours() else "OFF-MARKET"

        print(f"\n{'='*60}")
        print(f"[INFO] Fetching news feeds - {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"[INFO] Status: {market_status}")
        print(f"{'='*60}\n")

        max_articles = self.config.get('max_articles_per_feed', 10)
        processed_count = 0
        skipped_count = 0

        for feed_info in self.rss_feeds:
            try:
                try:
                    resp = requests.get(
                        feed_info['url'],
                        timeout=self.feed_fetch_timeout,
                        headers={'User-Agent': DEFAULT_USER_AGENT}
                    )
                    resp.raise_for_status()
                    feed = feedparser.parse(resp.content)
                except requests.exceptions.Timeout:
                    print(f"[ERROR] Timeout fetching feed {feed_info['name']} ({self.feed_fetch_timeout}s)")
                    self.discord.notify_feed_error(
                        feed_info['name'], f"Feed fetch timed out after {self.feed_fetch_timeout} seconds"
                    )
                    continue
                except requests.exceptions.RequestException as e:
                    print(f"[ERROR] Failed to fetch feed {feed_info['name']}: {e}")
                    self.discord.notify_feed_error(feed_info['name'], str(e))
                    continue

                source = feed_info['name']

                print(f"[INFO] Processing {source} (Priority: {feed_info['priority']})...")

                for entry in feed.entries[:max_articles]:
                    try:
                        title = getattr(entry, 'title', None)
                        link = getattr(entry, 'link', None)
                        if not title or not link:
                            print(f"[WARN] Skipping entry with missing title or link in {source}")
                            continue

                        article = {
                            'headline': title,
                            'summary': entry.get('summary', ''),
                            'url': link,
                            'source': source,
                            'published': entry.get('published', '')
                        }

                        was_duplicate = self._is_duplicate(article)

                        await self.process_article(article)

                        if was_duplicate:
                            skipped_count += 1
                        else:
                            processed_count += 1
                    except Exception as e:
                        print(f"[ERROR] Failed to process article in {source}: {e}")

            except Exception as e:
                print(f"[ERROR] Error processing feed {feed_info['name']}: {e}")
                self.discord.notify_feed_error(feed_info['name'], str(e))

        self._save_seen()

        stats = self.alert_manager.get_stats()
        print(f"\n[INFO] Feed Stats: {processed_count} new articles, {skipped_count} duplicates skipped")
        print(f"[INFO] Alert Stats: {stats['total_today']} critical alerts ({stats['unacknowledged']} unacknowledged)")

        # Send daily summary once per day
        current_date = now.date()
        if self._last_summary_date != current_date:
            self.discord.notify_daily_summary(stats)
            self._last_summary_date = current_date

    async def run_continuous(self):
        while True:
            try:
                await self.fetch_and_process_feeds()
            except Exception as e:
                print(f"[ERROR] Error in main loop: {e}")
                self.discord.notify_error("Main loop", str(e))

            interval_minutes = self._get_check_interval()

            print(f"\n[INFO] Sleeping for {interval_minutes} minutes...\n")
            await asyncio.sleep(interval_minutes * 60)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='News Worker - RSS Feed Monitor')
    parser.add_argument('--config',
                       help='Path to configuration file')
    parser.add_argument('--once', action='store_true',
                       help='Run once and exit')
    args = parser.parse_args()

    worker = NewsWorker(config_path=args.config)

    if args.once:
        asyncio.run(worker.fetch_and_process_feeds())
    else:
        asyncio.run(worker.run_continuous())
