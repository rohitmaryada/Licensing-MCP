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
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_PROJECT_ROOT = Path(__file__).parent.parent


class MCPBridge:
    """
    Owns the stdio connection to the licensing-mcp server for the lifetime
    of the agent process — mirroring how Claude Desktop spawns the server
    once per app session, not once per request.
    """

    def __init__(self) -> None:
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
            env={
                **os.environ,
                "CS_ACTOR_ID": os.environ.get("CS_ACTOR_ID", "rep.sarah@mathworks.com"),
            },
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
        """
        if not self.session:
            raise RuntimeError("MCPBridge not started")
        result = await self.session.call_tool(name, arguments)
        parts = [c.text for c in result.content if c.type == "text"]
        return "\n".join(parts) if parts else "(empty result)"

    async def stop(self) -> None:
        if self._stack:
            await self._stack.aclose()
            self._stack = None
            self.session = None
