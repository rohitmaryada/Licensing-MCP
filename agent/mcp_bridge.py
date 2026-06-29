"""
MCP client bridge — connects to the licensing-mcp server and exposes its
tools in the shape the Claude Messages API expects.

Role reversal: in Weeks 1-3 we built the MCP SERVER and Claude Desktop was
the client. Here WE are the client — same `mcp` SDK, opposite side of the
stdio pipe. The server doesn't know or care: it sees initialize/tools-list/
tools-call exactly as it would from Claude Desktop.

The bridge is deliberately thin because MCP tool definitions were designed
to mirror the Claude API tool format:

    MCP:    {name, description, inputSchema}
    Claude: {name, description, input_schema}

One field rename. That symmetry IS the point of MCP.
"""

import os
import time
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from agent.observability import MCP_TOOL_CALLS, MCP_TOOL_DURATION

_PROJECT_ROOT = Path(__file__).parent.parent


class MCPBridge:
    """
    Owns the stdio connection to the licensing-mcp server for the lifetime
    of the agent process — mirroring how Claude Desktop spawns the server
    once per app session, not once per request.
    """

    def __init__(self, actor_email: str) -> None:
        self._actor_email = actor_email
        self._stack: AsyncExitStack | None = None
        self.session: ClientSession | None = None
        self.claude_tools: list[dict] = []

    async def start(self) -> None:
        """Spawn the MCP server subprocess, handshake, and load the tool list."""
        self._stack = AsyncExitStack()

        # Same launch config as claude_desktop_config.json: venv python,
        # -m licensing_mcp, CS actor identity via env.
        params = StdioServerParameters(
            command=str(_PROJECT_ROOT / ".venv" / "bin" / "python"),
            args=["-m", "licensing_mcp"],
            env={**os.environ, "CS_ACTOR_ID": self._actor_email},
        )

        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()

        # tools/list → Claude tool definitions. The agent loop passes these
        # straight into messages.create(tools=...).
        listed = await self.session.list_tools()
        self.claude_tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema,
            }
            for t in listed.tools
        ]

    async def call_tool(self, name: str, arguments: dict) -> str:
        """
        Execute one tool call against the MCP server and return its text
        payload — which becomes the content of a tool_result block.

        Instrumentation note: this is the single chokepoint for all 13 tools,
        so one counter + one histogram here covers the entire tool surface.
        The `tool_name` label lets us slice per tool in Grafana without
        duplicating instrumentation in every tool file.
        """
        if not self.session:
            raise RuntimeError("MCPBridge not started")

        start = time.perf_counter()
        outcome = "success"
        try:
            result = await self.session.call_tool(name, arguments)
            parts = [c.text for c in result.content if c.type == "text"]
            return "\n".join(parts) if parts else "(empty result)"
        except Exception:
            outcome = "error"
            raise
        finally:
            # Always record — even on error — so error rate queries work correctly.
            # rate(mcp_tool_calls_total{outcome="error"}[5m])
            #   / rate(mcp_tool_calls_total[5m])
            # gives the error rate per tool.
            elapsed = time.perf_counter() - start
            MCP_TOOL_CALLS.labels(tool_name=name, outcome=outcome).inc()
            MCP_TOOL_DURATION.labels(tool_name=name).observe(elapsed)

    async def stop(self) -> None:
        if self._stack:
            await self._stack.aclose()
            self._stack = None
            self.session = None
