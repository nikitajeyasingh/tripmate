"""Thin LLM interface so agents don't care whether they talk to Claude or to
the offline demo brain. Both return the same normalized shape:
    {"content": [ {type:text|tool_use, ...} ], "stop_reason": str, "usage": {...}}
"""
from __future__ import annotations

import os
from typing import Any, Protocol

from anthropic import BadRequestError

DEFAULT_MODEL = os.getenv("TRIPMATE_MODEL", "claude-sonnet-5-5")


class LLM(Protocol):
    name: str

    async def respond(self, *, agent: str, system: str, messages: list[dict],
                      tools: list[dict], tool_choice: dict | None = None) -> dict[str, Any]: ...


class ClaudeLLM:
    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 8000):
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY
        self.model, self.max_tokens = model, max_tokens
        self.name = f"Claude ({model})"
        # Some models reject a forced tool_choice. We find out on the first call
        # and stop sending it; agents.py then asks for the tool in the prompt instead.
        self.forced_tool_choice_ok = True

    async def respond(self, *, agent, system, messages, tools, tool_choice=None):
        kwargs: dict[str, Any] = dict(model=self.model, max_tokens=self.max_tokens,
                                      system=system, messages=messages)
        if tools:
            kwargs["tools"] = tools
            if tool_choice and self.forced_tool_choice_ok:
                kwargs["tool_choice"] = tool_choice
        try:
            r = await self.client.messages.create(**kwargs)
        except BadRequestError as e:
            if "tool_choice" not in kwargs or "tool_choice" not in str(e):
                raise
            self.forced_tool_choice_ok = False      # remember, so we don't retry every call
            kwargs.pop("tool_choice")
            r = await self.client.messages.create(**kwargs)
        blocks = []
        for b in r.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        return {"content": blocks, "stop_reason": r.stop_reason,
                "usage": {"input": r.usage.input_tokens, "output": r.usage.output_tokens}}


def make_llm(demo: bool | None = None) -> LLM:
    """Use Claude when an API key is present, otherwise the scripted demo brain."""
    if demo is None:
        demo = not os.getenv("ANTHROPIC_API_KEY")
    if demo:
        from .demo_llm import DemoLLM
        return DemoLLM()
    return ClaudeLLM()
