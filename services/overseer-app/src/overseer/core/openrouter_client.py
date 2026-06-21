"""OpenRouter client adapter for the Overseer agent loop.

Translates between Anthropic's tool_use format and OpenRouter's
OpenAI-compatible format, so agent_loop.py needs minimal changes.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

log = structlog.get_logger()

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    openrouter_cost_usd: float = 0.0  # Actual cost reported by OpenRouter


@dataclass
class TextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class AnthropicStyleResponse:
    """Mimics anthropic.types.Message so agent_loop.py works unchanged."""
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=Usage)


def _anthropic_tools_to_openai(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool defs to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {}),
            },
        }
        for t in tools
    ]


def _anthropic_messages_to_openai(
    system_blocks: list[dict] | str,
    messages: list[dict],
) -> list[dict]:
    """Convert Anthropic message format to OpenAI chat format."""
    oai_messages = []

    # System prompt: Anthropic uses list of blocks, OpenAI uses plain string
    if isinstance(system_blocks, list):
        sys_text = "\n".join(b.get("text", "") for b in system_blocks if b.get("type") == "text")
    else:
        sys_text = system_blocks
    if sys_text:
        oai_messages.append({"role": "system", "content": sys_text})

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            if isinstance(content, str):
                oai_messages.append({"role": "user", "content": content})
            elif isinstance(content, list):
                # Check if it's tool results
                if content and isinstance(content[0], dict) and content[0].get("type") == "tool_result":
                    for tr in content:
                        oai_messages.append({
                            "role": "tool",
                            "tool_call_id": tr["tool_use_id"],
                            "content": tr.get("content", ""),
                        })
                else:
                    # Regular content blocks
                    text = "\n".join(
                        b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                    oai_messages.append({"role": "user", "content": text})

        elif role == "assistant":
            if isinstance(content, str):
                oai_messages.append({"role": "assistant", "content": content})
            elif isinstance(content, list):
                # May contain text + tool_use blocks
                text_parts = []
                tool_calls = []
                for block in content:
                    if block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block["input"]),
                            },
                        })

                assistant_msg = {"role": "assistant"}
                if text_parts:
                    assistant_msg["content"] = "\n".join(text_parts)
                else:
                    assistant_msg["content"] = None
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                oai_messages.append(assistant_msg)

    return oai_messages


def _openai_response_to_anthropic(data: dict) -> AnthropicStyleResponse:
    """Convert OpenAI chat completion response to Anthropic-style response."""
    choice = data["choices"][0]
    message = choice["message"]
    finish = choice.get("finish_reason", "stop")

    usage_data = data.get("usage", {})
    usage = Usage(
        input_tokens=usage_data.get("prompt_tokens", 0),
        output_tokens=usage_data.get("completion_tokens", 0),
        openrouter_cost_usd=usage_data.get("cost", 0.0) or 0.0,
    )

    content_blocks = []

    # Text content
    if message.get("content"):
        content_blocks.append(TextBlock(text=message["content"]))

    # Tool calls
    tool_calls = message.get("tool_calls", [])
    if tool_calls:
        for tc in tool_calls:
            fn = tc["function"]
            try:
                args = json.loads(fn["arguments"])
            except (json.JSONDecodeError, TypeError):
                args = {}
            content_blocks.append(ToolUseBlock(
                id=tc["id"],
                name=fn["name"],
                input=args,
            ))

    # Map finish_reason to Anthropic stop_reason
    if tool_calls:
        stop_reason = "tool_use"
    elif finish in ("stop", "length"):
        stop_reason = "end_turn"
    else:
        stop_reason = finish

    return AnthropicStyleResponse(
        content=content_blocks,
        stop_reason=stop_reason,
        usage=usage,
    )


class OpenRouterMessages:
    """Drop-in replacement for anthropic.AsyncAnthropic().messages"""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._http = httpx.AsyncClient(timeout=120.0)

    async def create(
        self,
        model: str,
        max_tokens: int,
        system: Any = None,
        tools: list[dict] | None = None,
        messages: list[dict] | None = None,
        **kwargs,
    ) -> AnthropicStyleResponse:
        oai_messages = _anthropic_messages_to_openai(system or [], messages or [])
        oai_tools = _anthropic_tools_to_openai(tools) if tools else None

        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": oai_messages,
        }
        if oai_tools:
            body["tools"] = oai_tools

        response = await self._http.post(
            OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://valhallacapital.local",
                "X-Title": "Valhalla Triage",
            },
            json=body,
        )
        response.raise_for_status()
        data = response.json()

        return _openai_response_to_anthropic(data)

    async def close(self):
        await self._http.aclose()


class OpenRouterClient:
    """Drop-in replacement for anthropic.AsyncAnthropic.

    Usage in agent_loop.py:
        # Before: client = anthropic.AsyncAnthropic(api_key=...)
        # After:  client = OpenRouterClient(api_key=...)
        # The rest of the code stays the same.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.messages = OpenRouterMessages(self.api_key)
