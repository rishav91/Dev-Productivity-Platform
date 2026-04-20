"""
Unified LLM caller — wraps litellm so nodes stay provider-agnostic.

Accepts Anthropic-format tool definitions (input_schema key) and converts
them to litellm/OpenAI format (parameters key) internally. Callers never
touch provider-specific APIs or response formats.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import litellm
from litellm.exceptions import RateLimitError

from backend.providers.config import get_llm_model

_RETRY_DELAYS = [10, 20, 40]  # seconds — covers Groq's free-tier TPM window


def _to_litellm_tool(anthropic_tool: dict) -> dict:
    """Repackage an Anthropic tool definition for litellm (OpenAI function format)."""
    return {
        "type": "function",
        "function": {
            "name": anthropic_tool["name"],
            "description": anthropic_tool.get("description", ""),
            "parameters": anthropic_tool["input_schema"],
        },
    }


async def call_with_tool(
    *,
    system: str,
    user: str,
    tool: dict,
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict[str, Any], float, int]:
    """
    Call the configured LLM requiring exactly one tool invocation.

    Args:
        tool: Anthropic-format tool definition (with 'input_schema' key).

    Returns:
        (tool_name, tool_args, cost_usd, latency_ms)

    Raises:
        RuntimeError: if the model did not call the expected tool.
    """
    model = get_llm_model()
    litellm_tool = _to_litellm_tool(tool)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    t0 = time.monotonic()
    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            print(f"  [rate limit] waiting {delay}s before retry {attempt}/{len(_RETRY_DELAYS)}…")
            await asyncio.sleep(delay)
        try:
            resp = await litellm.acompletion(
                model=model,
                messages=messages,
                tools=[litellm_tool],
                tool_choice={"type": "function", "function": {"name": tool["name"]}},
                max_tokens=max_tokens,
                temperature=temperature,
            )
            break
        except RateLimitError:
            if attempt == len(_RETRY_DELAYS):
                raise
    latency_ms = int((time.monotonic() - t0) * 1000)

    tool_calls = resp.choices[0].message.tool_calls or []
    if not tool_calls:
        raise RuntimeError(
            f"Model {model!r} did not call tool '{tool['name']}'. "
            "Check tool_choice support for this provider."
        )

    tc = tool_calls[0]
    try:
        # Pass model explicitly — some providers (e.g. Groq) return a bare model name
        # in the response object that litellm can't map back to a provider.
        cost = litellm.completion_cost(completion_response=resp, model=model) or 0.0
    except Exception:
        cost = 0.0
    return tc.function.name, json.loads(tc.function.arguments), cost, latency_ms
