"""Discord webhook notification adapter."""
from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog

log = structlog.get_logger()


class DiscordNotifier:
    """
    Sends alerts to Discord via webhooks.

    Provides formatted embeds for trades, rejections, and emergencies.
    """

    def __init__(self, webhook_url: str, enabled: bool = True, timeout: float = 10.0):
        """
        Initialize Discord notifier.

        Args:
            webhook_url: Discord webhook URL
            enabled: If False, disables all notifications
            timeout: HTTP request timeout in seconds
        """
        self.webhook_url = webhook_url
        self.enabled = enabled
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)
        self.logger = log.bind(component="discord_notifier")

    def send_trade_executed(
        self,
        ticker: str,
        action: str,
        quantity: int,
        price: float,
        reason: str,
    ) -> bool:
        """
        Send notification of successful trade execution.

        Args:
            ticker: Stock ticker
            action: BUY or SELL
            quantity: Number of shares
            price: Fill price
            reason: Trade reasoning

        Returns:
            True if sent successfully
        """
        return self._send_embed(
            title=f"✅ Trade Executed: {action} {ticker}",
            description=f"**{quantity} shares @ ${price:.2f}**\n\n"
            f"Total: ${quantity * price:,.2f}\n\n"
            f"Reason: {reason}",
            color=0x00FF00,  # Green
        )

    def send_trade_rejected(
        self, ticker: str, action: str, failed_checks: list
    ) -> bool:
        """
        Send notification of rejected trade.

        Args:
            ticker: Stock ticker
            action: BUY or SELL
            failed_checks: List of failed RiskCheck objects

        Returns:
            True if sent successfully
        """
        checks_str = "\n".join([f"• {c.name}: {c.message}" for c in failed_checks])

        return self._send_embed(
            title=f"⚠️ Trade Rejected: {action} {ticker}",
            description=f"**Failed risk checks:**\n{checks_str}",
            color=0xFFAA00,  # Orange
        )

    def send_panic_triggered(self, reason: str) -> bool:
        """
        Send notification of panic mode triggered.

        Args:
            reason: Why panic was triggered

        Returns:
            True if sent successfully
        """
        return self._send_embed(
            title="🚨 TRADING HALTED - PANIC MODE 🚨",
            description=f"**All trading stopped**\n\n"
            f"Reason: {reason}\n\n"
            f"All open orders have been cancelled.\n"
            f"Manual reset required.",
            color=0xFF0000,  # Red
        )

    def send_panic_reset(self) -> bool:
        """
        Send notification of panic mode reset.

        Returns:
            True if sent successfully
        """
        return self._send_embed(
            title="✅ Trading Resumed",
            description="Panic mode has been manually reset.\n"
            "Normal trading operations resumed.",
            color=0x00FF00,  # Green
        )

    def send_daily_summary(
        self,
        trades_count: int,
        total_pnl: float,
        total_pnl_pct: float,
        portfolio_value: float,
    ) -> bool:
        """
        Send daily trading summary.

        Args:
            trades_count: Number of trades executed today
            total_pnl: Total P&L in dollars
            total_pnl_pct: Total P&L as percentage
            portfolio_value: Current portfolio value

        Returns:
            True if sent successfully
        """
        pnl_emoji = "📈" if total_pnl >= 0 else "📉"
        pnl_color = 0x00FF00 if total_pnl >= 0 else 0xFF0000

        return self._send_embed(
            title=f"{pnl_emoji} Daily Trading Summary",
            description=f"**Trades**: {trades_count}\n"
            f"**P&L**: ${total_pnl:,.2f} ({total_pnl_pct:+.2%})\n"
            f"**Portfolio Value**: ${portfolio_value:,.2f}",
            color=pnl_color,
        )

    def send_error_alert(self, error_type: str, error_message: str) -> bool:
        """
        Send error alert notification.

        Args:
            error_type: Type of error
            error_message: Error details

        Returns:
            True if sent successfully
        """
        return self._send_embed(
            title=f"❌ Error: {error_type}",
            description=error_message,
            color=0xFF0000,  # Red
        )

    def _send_embed(
        self, title: str, description: str, color: int = 0x0099FF
    ) -> bool:
        """
        Send Discord embed message.

        Args:
            title: Embed title
            description: Embed description
            color: Embed color (hex)

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            self.logger.debug("discord_notification_skipped", title=title)
            return False

        payload = {
            "embeds": [
                {
                    "title": title,
                    "description": description,
                    "color": color,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "footer": {"text": "IBKR Trading Gateway"},
                }
            ]
        }

        try:
            response = self.client.post(self.webhook_url, json=payload)
            response.raise_for_status()

            self.logger.info("discord_notification_sent", title=title)
            return True

        except httpx.HTTPStatusError as e:
            self.logger.error(
                "discord_notification_failed",
                title=title,
                status_code=e.response.status_code,
                error=str(e),
            )
            return False

        except Exception as e:
            self.logger.error(
                "discord_notification_failed", title=title, error=str(e)
            )
            return False

    def test_connection(self) -> bool:
        """
        Test Discord webhook connection.

        Returns:
            True if webhook is accessible
        """
        return self._send_embed(
            title="🔔 Test Notification",
            description="Discord webhook connection test successful!",
            color=0x0099FF,  # Blue
        )

    def close(self):
        """Close HTTP client."""
        self.client.close()
