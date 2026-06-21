import requests
from datetime import datetime
from typing import Optional, Dict


class DiscordNotifier:
    """Sends formatted notifications to a Discord webhook.

    Fails gracefully -- all public methods catch exceptions internally
    so that webhook issues never crash the calling program.
    """

    COLOR_CRITICAL = 0xFF0000   # Red
    COLOR_ERROR = 0xFF6600      # Orange
    COLOR_WARNING = 0xFFCC00    # Yellow
    COLOR_INFO = 0x3498DB       # Blue
    COLOR_SUCCESS = 0x2ECC71    # Green

    def __init__(self, webhook_url: Optional[str] = None, timeout: int = 10):
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.enabled = bool(self.webhook_url)
        if not self.enabled:
            print("[INFO] Discord notifications disabled (no webhook URL configured)")

    def _send_embed(self, title: str, description: str, color: int,
                    fields: Optional[list] = None, footer: Optional[str] = None):
        if not self.enabled:
            return

        embed = {
            "title": title,
            "description": description[:4096],
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if fields:
            embed["fields"] = fields[:25]
        if footer:
            embed["footer"] = {"text": footer[:2048]}

        payload = {"embeds": [embed]}

        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout
            )
            if resp.status_code == 429:
                print(f"[WARN] Discord rate limited, message dropped: {title}")
            elif resp.status_code >= 400:
                print(f"[WARN] Discord HTTP {resp.status_code} sending: {title}")
        except requests.RequestException as e:
            print(f"[WARN] Discord send failed: {e}")

    def notify_critical_alert(self, article: Dict):
        """Send notification for a CRITICAL classified article."""
        self._send_embed(
            title="CRITICAL ALERT",
            description=article.get('headline', 'Unknown headline'),
            color=self.COLOR_CRITICAL,
            fields=[
                {"name": "Source", "value": article.get('source', 'Unknown'), "inline": True},
                {"name": "URL", "value": article.get('url', 'N/A'), "inline": False},
                {"name": "Summary", "value": (article.get('summary', 'N/A'))[:1024], "inline": False},
            ],
        )

    def notify_error(self, context: str, error: str):
        """Send notification for a processing error."""
        self._send_embed(
            title="Processing Error",
            description=f"**{context}**\n```\n{error[:3000]}\n```",
            color=self.COLOR_ERROR,
        )

    def notify_feed_error(self, feed_name: str, error: str):
        """Send notification for a feed fetch/parse failure."""
        self._send_embed(
            title=f"Feed Error: {feed_name}",
            description=f"```\n{error[:3000]}\n```",
            color=self.COLOR_WARNING,
        )

    def notify_startup(self, feed_count: int, market_hours: str):
        """Send notification when the worker starts."""
        self._send_embed(
            title="News Worker Started",
            description=f"Monitoring {feed_count} feeds",
            color=self.COLOR_SUCCESS,
            fields=[
                {"name": "Market Hours", "value": market_hours, "inline": True},
            ],
        )

    def notify_shutdown(self, reason: str = "Manual stop"):
        """Send notification when the worker stops."""
        self._send_embed(
            title="News Worker Stopped",
            description=reason,
            color=self.COLOR_INFO,
        )

    def notify_daily_summary(self, stats: Dict):
        """Send end-of-day summary stats."""
        self._send_embed(
            title="Daily Summary",
            description="End-of-day alert statistics",
            color=self.COLOR_INFO,
            fields=[
                {"name": "Total Alerts", "value": str(stats.get('total_today', 0)), "inline": True},
                {"name": "Unacknowledged", "value": str(stats.get('unacknowledged', 0)), "inline": True},
                {"name": "Acknowledged", "value": str(stats.get('acknowledged', 0)), "inline": True},
            ],
        )
