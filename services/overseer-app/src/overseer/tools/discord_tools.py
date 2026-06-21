from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
import structlog

if TYPE_CHECKING:
    from overseer.config import OverseerSettings

log = structlog.get_logger()

MAX_MESSAGE_LENGTH = 2000


class DiscordNotifier:
    def __init__(self, settings: OverseerSettings) -> None:
        self.settings = settings
        self.channel_id = settings.discord_channel_id

        intents = discord.Intents.default()
        intents.message_content = True

        self.client = discord.Client(intents=intents)
        self._ready = asyncio.Event()
        self._task: asyncio.Task | None = None

        @self.client.event
        async def on_ready() -> None:
            log.info("discord_bot_ready", user=str(self.client.user))
            self._ready.set()

    async def start(self) -> None:
        log.info("starting_discord_bot")
        self._task = asyncio.create_task(
            self.client.start(self.settings.discord_bot_token)
        )

        try:
            await asyncio.wait_for(self._ready.wait(), timeout=10.0)
            log.info("discord_bot_connected")
        except asyncio.TimeoutError:
            log.error("discord_bot_connection_timeout")
            raise

    async def stop(self) -> None:
        log.info("stopping_discord_bot")
        if self.client.is_closed():
            return

        await self.client.close()

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                log.warning("discord_bot_stop_timeout")
                self._task.cancel()

    def _truncate_message(self, content: str) -> str:
        if len(content) <= MAX_MESSAGE_LENGTH:
            return content

        truncated = content[: MAX_MESSAGE_LENGTH - 15]
        return f"{truncated}...(truncated)"

    def _format_message(self, content: str, message_type: str) -> str:
        if message_type == "alert":
            return f"⚠️ **ALERT**: {content}"
        elif message_type == "trade":
            return f"📊 **TRADE**: {content}"
        elif message_type == "report":
            return f"```\n{content}\n```"
        else:
            return content

    async def send_message(
        self, content: str, message_type: str = "info"
    ) -> bool:
        if not self._ready.is_set() or self.client.is_closed():
            log.warning(
                "discord_bot_not_ready",
                message_type=message_type,
            )
            return False

        try:
            channel = self.client.get_channel(self.channel_id)
            if not channel:
                channel = await self.client.fetch_channel(self.channel_id)

            if not isinstance(channel, discord.TextChannel):
                log.error(
                    "invalid_channel_type",
                    channel_id=self.channel_id,
                )
                return False

            formatted_content = self._format_message(content, message_type)
            truncated_content = self._truncate_message(formatted_content)

            await channel.send(truncated_content)

            log.info(
                "discord_message_sent",
                message_type=message_type,
                length=len(content),
            )
            return True

        except discord.HTTPException as e:
            log.error(
                "discord_http_error",
                error=str(e),
                message_type=message_type,
            )
            return False
        except Exception as e:
            log.error(
                "discord_send_error",
                error=str(e),
                message_type=message_type,
            )
            return False

    async def send_trade_notification(
        self,
        ticker: str,
        action: str,
        quantity: int | float,
        price: float | None,
        reasoning: str,
    ) -> bool:
        if not self._ready.is_set() or self.client.is_closed():
            log.warning("discord_bot_not_ready", message_type="trade")
            return False

        try:
            channel = self.client.get_channel(self.channel_id)
            if not channel:
                channel = await self.client.fetch_channel(self.channel_id)

            if not isinstance(channel, discord.TextChannel):
                log.error("invalid_channel_type", channel_id=self.channel_id)
                return False

            embed = discord.Embed(
                title=f"Trade: {action.upper()} {ticker}",
                color=discord.Color.green() if action.lower() == "buy" else discord.Color.red(),
            )

            embed.add_field(name="Action", value=action.upper(), inline=True)
            embed.add_field(name="Ticker", value=ticker, inline=True)
            embed.add_field(name="Quantity", value=str(quantity), inline=True)

            if price is not None:
                embed.add_field(name="Price", value=f"${price:.2f}", inline=True)

            truncated_reasoning = self._truncate_message(reasoning)
            if len(truncated_reasoning) > 1024:
                truncated_reasoning = truncated_reasoning[:1021] + "..."

            embed.add_field(
                name="Reasoning",
                value=truncated_reasoning,
                inline=False,
            )

            await channel.send(embed=embed)

            log.info(
                "discord_trade_notification_sent",
                ticker=ticker,
                action=action,
            )
            return True

        except discord.HTTPException as e:
            log.error("discord_http_error", error=str(e), message_type="trade")
            return False
        except Exception as e:
            log.error("discord_send_error", error=str(e), message_type="trade")
            return False

    async def send_daily_report(self, report_text: str) -> bool:
        if not self._ready.is_set() or self.client.is_closed():
            log.warning("discord_bot_not_ready", message_type="report")
            return False

        try:
            channel = self.client.get_channel(self.channel_id)
            if not channel:
                channel = await self.client.fetch_channel(self.channel_id)

            if not isinstance(channel, discord.TextChannel):
                log.error("invalid_channel_type", channel_id=self.channel_id)
                return False

            formatted_report = f"📈 **Daily Report**\n```\n{report_text}\n```"

            if len(formatted_report) > MAX_MESSAGE_LENGTH:
                chunks = []
                lines = report_text.split("\n")
                current_chunk = []
                current_length = 0

                header_length = len("📈 **Daily Report**\n```\n") + len("\n```")

                for line in lines:
                    line_length = len(line) + 1
                    if current_length + line_length + header_length > MAX_MESSAGE_LENGTH:
                        chunks.append("\n".join(current_chunk))
                        current_chunk = [line]
                        current_length = line_length
                    else:
                        current_chunk.append(line)
                        current_length += line_length

                if current_chunk:
                    chunks.append("\n".join(current_chunk))

                for i, chunk in enumerate(chunks):
                    header = f"📈 **Daily Report** ({i + 1}/{len(chunks)})"
                    await channel.send(f"{header}\n```\n{chunk}\n```")
            else:
                await channel.send(formatted_report)

            log.info("discord_daily_report_sent", length=len(report_text))
            return True

        except discord.HTTPException as e:
            log.error("discord_http_error", error=str(e), message_type="report")
            return False
        except Exception as e:
            log.error("discord_send_error", error=str(e), message_type="report")
            return False

    async def send_alert(self, alert_text: str) -> bool:
        return await self.send_message(alert_text, message_type="alert")


_notifier: DiscordNotifier | None = None


async def get_notifier(settings: OverseerSettings) -> DiscordNotifier:
    global _notifier

    if _notifier is None:
        _notifier = DiscordNotifier(settings)
        await _notifier.start()

    return _notifier


async def send_discord_message(
    settings: OverseerSettings,
    content: str,
    message_type: str = "info",
) -> bool:
    notifier = await get_notifier(settings)
    return await notifier.send_message(content, message_type)
