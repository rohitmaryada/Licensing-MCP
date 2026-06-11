"""
FastAPI host for the custom agent.

Composition:
    browser chat UI  →  POST /api/chat  →  agent loop  →  Claude API
                                              ↓ tool calls
                                          MCP bridge → licensing-mcp (stdio)

Lifecycle: ONE MCP server subprocess for the app's lifetime (FastAPI
lifespan), exactly like Claude Desktop. Conversations are kept in process
memory keyed by session_id — a POC shortcut; production would use Redis or
a DB, and per-user auth would scope sessions.

Run:
    uvicorn agent.app:app --port 8100
"""

import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent.agent_loop import run_agent_turn
from agent.mcp_bridge import MCPBridge

load_dotenv()  # reads ANTHROPIC_API_KEY (and optional CS_ACTOR_ID) from .env

_STATIC = Path(__file__).parent / "static"

bridge = MCPBridge()
client = anthropic.AsyncAnthropic()  # key from env
sessions: dict[str, list] = {}  # session_id → message history


@asynccontextmanager
async def lifespan(app: FastAPI):
    await bridge.start()
    print(f"MCP bridge up — {len(bridge.claude_tools)} tools: "
          f"{', '.join(t['name'] for t in bridge.claude_tools)}")
    yield
    await bridge.stop()


app = FastAPI(title="Licensing Intelligence Agent", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


@app.post("/api/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    messages = sessions.setdefault(session_id, [])

    messages.append({"role": "user", "content": req.message})
    reply, tool_trace = await run_agent_turn(client, bridge, messages)

    return {
        "session_id": session_id,
        "reply": reply,
        "tool_calls": tool_trace,
    }


@app.get("/api/tools")
async def tools():
    """Expose the live tool list — handy for demos and debugging."""
    return {
        "actor": os.environ.get("CS_ACTOR_ID", "rep.sarah@mathworks.com"),
        "tools": [
            {"name": t["name"], "description": t["description"].strip().split("\n")[0]}
            for t in bridge.claude_tools
        ],
    }


@app.get("/")
async def index():
    return FileResponse(_STATIC / "index.html")
