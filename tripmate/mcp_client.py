"""MCP client: launches the travel MCP server over stdio and adapts its tools
into the JSON-schema format the Claude Messages API expects."""
from __future__ import annotations

import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parent.parent / "mcp_server" / "travel_server.py"


class MCPToolbox:
    """`async with MCPToolbox() as box:` starts the server; `box.call()` runs a tool."""

    def __init__(self, offline: bool = False):
        self.offline = offline
        self._stack = AsyncExitStack()
        self.session: ClientSession | None = None
        self.schemas: dict[str, dict] = {}

    async def __aenter__(self) -> "MCPToolbox":
        env = dict(os.environ)
        if self.offline:
            env["TRIPMATE_OFFLINE"] = "1"
        params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=env)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        for t in (await self.session.list_tools()).tools:
            self.schemas[t.name] = {"name": t.name, "description": t.description or "", "input_schema": t.inputSchema}
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        try:
            await self._stack.__aexit__(exc_type, exc, tb)
        except BaseException:
            if exc_type is None:
                raise
            # The pipeline already failed; don't let stdio teardown noise hide the real error.
        return False

    def tools_for(self, names: list[str]) -> list[dict]:
        return [self.schemas[n] for n in names if n in self.schemas]

    async def call(self, name: str, args: dict) -> str:
        assert self.session is not None
        result = await self.session.call_tool(name, args)
        return "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")

    async def read_resource(self, uri: str) -> str:
        assert self.session is not None
        res = await self.session.read_resource(uri)
        return "\n".join(getattr(c, "text", "") for c in res.contents)
