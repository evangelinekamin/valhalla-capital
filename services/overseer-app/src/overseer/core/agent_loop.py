from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import anthropic
import httpx
import structlog

from overseer.config import OverseerSettings
from overseer.core.openrouter_client import OpenRouterClient
from overseer.core.tool_registry import ToolRegistry

log = structlog.get_logger()

MAX_ITERATIONS = 25
MAX_TOOL_OUTPUT_CHARS = 4000
STOP_REASONS_TERMINAL = {"end_turn", "stop_sequence"}


async def run_agent_loop(
    settings: OverseerSettings,
    tool_registry: ToolRegistry,
    system_prompt: str,
    user_message: str,
    model: str,
    max_tokens: int = 4096,
    max_iterations: int = MAX_ITERATIONS,
    cycle_log_id: int | None = None,
) -> dict:
    # Route through OpenRouter for non-Anthropic models
    is_anthropic = model.startswith("claude-")
    if is_anthropic:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    else:
        client = OpenRouterClient(api_key=settings.openrouter_api_key)
    tools = tool_registry.get_tool_definitions()

    # Structure system prompt for prompt caching.
    # Mark the last block with cache_control so the entire system prompt
    # is cached across calls within the 5-minute TTL window.
    system_blocks = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    messages = [{"role": "user", "content": user_message}]

    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_read_tokens = 0
    total_cache_creation_tokens = 0
    total_openrouter_cost_usd = 0.0
    all_tool_calls = []
    iteration = 0
    final_text = ""

    log.info(
        "agent_loop_start",
        model=model,
        cycle_log_id=cycle_log_id,
        tool_count=len(tools),
    )

    while iteration < max_iterations:
        iteration += 1
        start = time.monotonic()

        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_blocks,
                tools=tools,
                messages=messages,
            )
        except anthropic.RateLimitError:
            log.warning("rate_limited", iteration=iteration)
            await asyncio.sleep(30)
            continue
        except anthropic.APIError as e:
            log.error("api_error", error=str(e), iteration=iteration)
            final_text += f"[API Error: {e}]"
            break
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                log.warning("rate_limited_openrouter", iteration=iteration)
                await asyncio.sleep(30)
                continue
            log.error("openrouter_http_error", status=e.response.status_code, iteration=iteration)
            final_text += f"[OpenRouter Error: {e.response.status_code}]"
            break
        except httpx.TimeoutException:
            log.warning("openrouter_timeout", iteration=iteration)
            await asyncio.sleep(10)
            continue

        elapsed_ms = int((time.monotonic() - start) * 1000)
        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens
        total_cache_read_tokens += getattr(response.usage, "cache_read_input_tokens", 0) or 0
        total_cache_creation_tokens += getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        total_openrouter_cost_usd += getattr(response.usage, "openrouter_cost_usd", 0.0) or 0.0

        log.debug(
            "agent_iteration",
            iteration=iteration,
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            elapsed_ms=elapsed_ms,
        )

        if response.stop_reason in STOP_REASONS_TERMINAL:
            for block in response.content:
                if block.type == "text":
                    final_text += block.text
            break

        if response.stop_reason == "tool_use":
            assistant_content = []
            tool_results = []

            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                    final_text += block.text
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

                    tool_output = await tool_registry.execute(
                        block.name, block.input, cycle_log_id=cycle_log_id
                    )

                    all_tool_calls.append({
                        "name": block.name,
                        "input": block.input,
                        "output_preview": tool_output[:200],
                    })

                    # Truncate large tool outputs to control context growth
                    if len(tool_output) > MAX_TOOL_OUTPUT_CHARS:
                        tool_output = (
                            tool_output[:MAX_TOOL_OUTPUT_CHARS]
                            + f"\n\n[OUTPUT TRUNCATED: {len(tool_output)} chars total, showing first {MAX_TOOL_OUTPUT_CHARS}]"
                        )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_output,
                    })

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})
        else:
            log.warning("unexpected_stop_reason", stop_reason=response.stop_reason)
            break

    log.info(
        "agent_loop_complete",
        iterations=iteration,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        tool_calls=len(all_tool_calls),
        cycle_log_id=cycle_log_id,
    )

    return {
        "final_text": final_text,
        "iterations": iteration,
        "tokens": {
            "input": total_input_tokens,
            "output": total_output_tokens,
            "cache_read": total_cache_read_tokens,
            "cache_creation": total_cache_creation_tokens,
            "total": total_input_tokens + total_output_tokens + total_cache_read_tokens + total_cache_creation_tokens,
            "openrouter_cost_usd": total_openrouter_cost_usd,
        },
        "tool_calls": all_tool_calls,
        "cycle_log_id": cycle_log_id,
    }
