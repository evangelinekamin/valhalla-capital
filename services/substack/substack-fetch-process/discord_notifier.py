# discord_notifier.py
"""
Discord webhook notification module for error monitoring.
Sends formatted error alerts to a Discord channel via webhook.

Rate-limited: sends the first error per (stage, error_type) immediately,
then suppresses duplicates for a cooldown window. A summary is sent when
flush_suppressed() is called (typically at pipeline end).
"""
import atexit
import logging
import requests
import traceback
from collections import defaultdict
from datetime import datetime
from time import monotonic
from typing import Optional, Dict, Any
import platform

logger = logging.getLogger(__name__)

# How long (seconds) to suppress duplicate errors for the same fingerprint
DEFAULT_COOLDOWN_SECS = 300  # 5 minutes


class DiscordNotifier:
    """Sends error notifications to Discord via webhook, with rate limiting."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        enabled: bool = True,
        cooldown_secs: int = DEFAULT_COOLDOWN_SECS,
    ):
        self.webhook_url = webhook_url
        self.enabled = enabled and bool(webhook_url)
        self.cooldown_secs = cooldown_secs

        # Rate-limiting state: {fingerprint: {"first_at": float, "count": int, "last_error": str}}
        self._suppressed: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"first_at": 0.0, "count": 0, "last_error": ""}
        )

        if not self.enabled and webhook_url:
            logger.info("Discord notifications disabled in configuration")
        elif not webhook_url:
            logger.debug("No Discord webhook URL configured")

    @staticmethod
    def _fingerprint(stage: str, error: Exception) -> str:
        """Create a dedup key from stage + error type + first line of message."""
        error_type = type(error).__name__
        msg_line = str(error).split("\n")[0][:120]
        return f"{stage}:{error_type}:{msg_line}"

    def send_error(
        self,
        error: Exception,
        stage: str,
        context: Optional[Dict[str, Any]] = None,
        severity: str = "error",
    ) -> bool:
        if not self.enabled:
            return False

        fp = self._fingerprint(stage, error)
        now = monotonic()
        state = self._suppressed[fp]

        # If we're within the cooldown window, just count and skip
        if state["count"] > 0 and (now - state["first_at"]) < self.cooldown_secs:
            state["count"] += 1
            state["last_error"] = str(error)[:200]
            logger.debug(
                f"Discord notification suppressed ({state['count']} total for {fp})"
            )
            return False

        # Either first occurrence or cooldown expired -- reset and send
        state["first_at"] = now
        state["count"] = 1
        state["last_error"] = str(error)[:200]

        try:
            embed = self._build_error_embed(error, stage, context, severity)
            payload = {"embeds": [embed]}

            response = requests.post(
                self.webhook_url, json=payload, timeout=10
            )
            response.raise_for_status()

            logger.debug(f"Discord notification sent for {stage} error")
            return True

        except Exception as e:
            logger.warning(f"Failed to send Discord notification: {e}")
            return False

    def flush_suppressed(self) -> bool:
        """Send a single summary message for all suppressed errors, then reset."""
        if not self.enabled:
            return False

        # Collect fingerprints that had more than 1 occurrence (i.e. suppressed some)
        summaries = []
        for fp, state in self._suppressed.items():
            suppressed_count = state["count"] - 1  # first one was sent
            if suppressed_count > 0:
                parts = fp.split(":", 2)
                stage = parts[0] if len(parts) > 0 else "unknown"
                error_type = parts[1] if len(parts) > 1 else "unknown"
                summaries.append(
                    f"**{stage}** / `{error_type}`: {suppressed_count} additional "
                    f"occurrence{'s' if suppressed_count != 1 else ''}"
                )

        self._suppressed.clear()

        if not summaries:
            return False

        description = (
            "The following errors were suppressed during this pipeline run:\n\n"
            + "\n".join(summaries)
        )

        return self.send_message(description, severity="warning")

    def send_message(self, message: str, severity: str = "info") -> bool:
        if not self.enabled:
            return False

        try:
            color = self._get_severity_color(severity)
            embed = {
                "title": f"Pipeline {severity.upper()}",
                "description": message[:4000],
                "color": color,
                "timestamp": datetime.utcnow().isoformat(),
            }

            response = requests.post(
                self.webhook_url, json={"embeds": [embed]}, timeout=10
            )
            response.raise_for_status()

            logger.debug("Discord message sent successfully")
            return True

        except Exception as e:
            logger.warning(f"Failed to send Discord message: {e}")
            return False

    def _build_error_embed(
        self,
        error: Exception,
        stage: str,
        context: Optional[Dict[str, Any]],
        severity: str,
    ) -> Dict[str, Any]:
        """Build Discord embed object for error notification."""
        color = self._get_severity_color(severity)
        error_type = type(error).__name__
        title = f"{severity.upper()}: {stage.title()} Stage Failed"

        description = f"**Error Type:** `{error_type}`\n"
        description += f"**Message:** {str(error)[:500]}"

        fields = [
            {"name": "Stage", "value": f"`{stage}`", "inline": True},
            {
                "name": "Time",
                "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "inline": True,
            },
            {"name": "Host", "value": f"`{platform.node()}`", "inline": True},
        ]

        if context:
            for key, value in context.items():
                if value is not None and len(fields) < 10:
                    str_value = str(value)[:100]
                    fields.append(
                        {
                            "name": key.replace("_", " ").title(),
                            "value": f"`{str_value}`",
                            "inline": True,
                        }
                    )

        tb = traceback.format_exc()
        footer_text = tb[-500:] if len(tb) > 500 else tb

        return {
            "title": title,
            "description": description,
            "color": color,
            "fields": fields,
            "footer": {
                "text": (
                    f"Traceback: ...{footer_text}"
                    if len(tb) > 500
                    else f"Traceback: {footer_text}"
                )
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _get_severity_color(self, severity: str) -> int:
        """Get Discord embed color for severity level."""
        colors = {
            "info": 0x3498DB,
            "warning": 0xF39C12,
            "error": 0xE74C3C,
            "critical": 0x992D22,
        }
        return colors.get(severity.lower(), 0x95A5A6)


# Global notifier instance (initialized in orchestrate.py)
_notifier: Optional[DiscordNotifier] = None


def init_notifier(
    webhook_url: Optional[str],
    enabled: bool = True,
    cooldown_secs: int = DEFAULT_COOLDOWN_SECS,
) -> DiscordNotifier:
    global _notifier
    _notifier = DiscordNotifier(webhook_url, enabled, cooldown_secs)
    # Auto-flush suppressed errors on exit so nothing is silently lost
    atexit.register(flush_suppressed)
    return _notifier


def get_notifier() -> Optional[DiscordNotifier]:
    return _notifier


def notify_error(
    error: Exception,
    stage: str,
    context: Optional[Dict[str, Any]] = None,
    severity: str = "error",
) -> bool:
    if _notifier:
        return _notifier.send_error(error, stage, context, severity)
    return False


def notify_message(message: str, severity: str = "info") -> bool:
    if _notifier:
        return _notifier.send_message(message, severity)
    return False


def flush_suppressed() -> bool:
    """Flush any suppressed error summaries to Discord."""
    if _notifier:
        return _notifier.flush_suppressed()
    return False
