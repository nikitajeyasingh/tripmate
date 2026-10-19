"""A small, readable agent loop (no framework) on top of the Claude tool-use API.

Each Agent has:
  * a role-specific system prompt
  * a least-privilege subset of MCP tools (e.g. the weather agent can't touch currency)
  * a list of skills it may load (+ any code tools those skills ship)
  * optionally an `output_tool`: a JSON schema the agent must fill in, which gives
    the orchestrator structured, validated output instead of free text.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .llm import LLM
from .mcp_client import MCPToolbox
from .skills import SkillRegistry

EventFn = Callable[[dict], Awaitable[None] | None]


@dataclass
class AgentResult:
    agent: str
    text: str = ""
    output: dict | None = None                    # filled when output_tool is used
    tool_log: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {"input": 0, "output": 0})
    seconds: float = 0.0


@dataclass
class Agent:
    name: str
    emoji: str
    system: str
    mcp_tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    output_tool: dict | None = None
    max_turns: int = 8

    async def run(self, task: str, *, llm: LLM, toolbox: MCPToolbox | None,
                  registry: SkillRegistry, emit: EventFn | None = None) -> AgentResult:
        t0 = time.perf_counter()
        res = AgentResult(self.name)

        async def _emit(ev: dict):
            if emit:
                out = emit({"agent": self.name, "emoji": self.emoji, **ev})
                if asyncio.iscoroutine(out):
                    await out

        # ---- assemble this agent's toolset (least privilege) -------------- #
        tools = toolbox.tools_for(self.mcp_tools) if toolbox else []
        local = registry.local_tools(self.skills)
        tools += [schema for schema, _ in local.values()]
        system = self.system
        if self.skills:
            tools.append(registry.load_skill_schema(self.skills))
            system += "\n\n" + registry.catalog(self.skills)
        tool_choice = None
        if self.output_tool:
            tools.append(self.output_tool)
            if len(tools) == 1:  # nothing else to do -> force structured output
                tool_choice = {"type": "tool", "name": self.output_tool["name"]}
            # Also say it in the prompt, for models that don't support a forced tool_choice.
            system += (f"\n\nWhen you are finished, give your answer by calling the "
                       f"`{self.output_tool['name']}` tool. Do not answer in plain text.")

        await _emit({"type": "start", "tools": [t["name"] for t in tools]})
        messages: list[dict] = [{"role": "user", "content": task}]
        nudged = False

        for _ in range(self.max_turns):
            r = await llm.respond(agent=self.name, system=system, messages=messages,
                                  tools=tools, tool_choice=tool_choice)
            res.usage["input"] += r["usage"]["input"]
            res.usage["output"] += r["usage"]["output"]
            messages.append({"role": "assistant", "content": r["content"]})
            calls = [b for b in r["content"] if b["type"] == "tool_use"]
            text = "\n".join(b["text"] for b in r["content"] if b["type"] == "text").strip()

            # structured output reached?
            for c in calls:
                if self.output_tool and c["name"] == self.output_tool["name"]:
                    res.output, res.text = c["input"], text
                    res.seconds = time.perf_counter() - t0
                    await _emit({"type": "done", "seconds": res.seconds, "output": res.output})
                    return res

            if not calls:
                if self.output_tool and not nudged:  # ask once for the structured answer
                    nudged = True
                    messages.append({"role": "user", "content": f"Please call `{self.output_tool['name']}` with your answer."})
                    continue
                res.text = text
                break

            # run every tool the model asked for this turn *in parallel*
            async def run_one(c: dict) -> dict:
                await _emit({"type": "tool_call", "tool": c["name"], "input": c["input"]})
                try:
                    if c["name"] == "load_skill":
                        out = registry.load(c["input"]["name"])
                    elif c["name"] in local:
                        out = json.dumps(local[c["name"]][1](**c["input"]))
                    elif toolbox:
                        out = await toolbox.call(c["name"], c["input"])
                    else:
                        raise RuntimeError(f"Tool {c['name']} needs the MCP server")
                    err = False
                except Exception as e:  # tool errors go back to the model, not up the stack
                    out, err = f"Tool error: {e}", True
                res.tool_log.append({"tool": c["name"], "input": c["input"], "output": out})
                await _emit({"type": "tool_result", "tool": c["name"], "preview": out[:160], "error": err})
                return {"type": "tool_result", "tool_use_id": c["id"], "content": out, "is_error": err}

            results = await asyncio.gather(*(run_one(c) for c in calls))
            messages.append({"role": "user", "content": list(results)})

        res.seconds = time.perf_counter() - t0
        await _emit({"type": "done", "seconds": res.seconds, "text": res.text})
        return res
