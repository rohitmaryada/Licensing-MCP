"""
FastAPI host for the custom agent.

Composition:
    browser  →  /login  →  Keycloak  →  /callback  →  session cookie
    browser  →  POST /api/chat (cookie)  →  agent loop  →  Claude API
                                                ↓ tool calls
                                     per-session MCP bridge → licensing-mcp (stdio)

Auth boundary: this agent host. Keycloak proves identity (email in JWT).
The MCP server's identity.py + cs_executor.py handle all authorization.

Run:
    uvicorn agent.app:app --port 8100
"""

import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel

from agent.agent_loop import run_agent_turn
from agent.auth import CLIENT_ID, ISSUER, get_actor_email
from agent.mcp_bridge import MCPBridge
from agent.observability import (
    HTTP_REQUESTS,
    HTTP_DURATION,
    ACTIVE_SESSIONS,
    metrics_app,
    setup_tracing,
)

# Bootstrap tracing before the app starts receiving requests.
# Metrics instruments are created at import time (prometheus_client registers them
# globally on the default REGISTRY — no explicit setup call needed).
setup_tracing()

load_dotenv()

_STATIC = Path(__file__).parent / "static"

client = anthropic.AsyncAnthropic()
sessions: dict[str, list] = {}                # session_id → message history
authenticated_sessions: dict[str, dict] = {}  # session_id → {email: ...}
session_bridges: dict[str, MCPBridge] = {}    # session_id → MCPBridge


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for bridge in session_bridges.values():
        await bridge.stop()


app = FastAPI(title="Licensing Intelligence Agent", lifespan=lifespan)

# Auto-instrument FastAPI: every route gets a trace span with HTTP attributes.
# The instrumentor hooks into Starlette middleware — zero manual span creation needed.
FastAPIInstrumentor.instrument_app(app, excluded_urls="/metrics,/healthz")

# Expose Prometheus metrics at /metrics — this is what prometheus.yml scrapes.
# The make_asgi_app() returns a lightweight WSGI-compatible app that serializes
# all registered metrics in the Prometheus text exposition format.
app.mount("/metrics", metrics_app)


# ── HTTP observability middleware ─────────────────────────────────────────────
# Tracks RED metrics (Rate / Errors / Duration) for every request.
# Skips /metrics itself to avoid infinite feedback loops in the series.

@app.middleware("http")
async def record_http_metrics(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    # Normalize dynamic path segments so /api/chat doesn't fan out into
    # a separate label per session ID — high cardinality kills Prometheus.
    endpoint = request.url.path

    HTTP_REQUESTS.labels(
        method=request.method,
        endpoint=endpoint,
        status=str(response.status_code),
    ).inc()

    HTTP_DURATION.labels(
        method=request.method,
        endpoint=endpoint,
    ).observe(duration)

    return response


async def _get_bridge(session_id: str) -> MCPBridge:
    """Lazily start a per-session MCP subprocess on first tool call."""
    if session_id not in session_bridges:
        email = authenticated_sessions[session_id]["email"]
        bridge = MCPBridge(actor_email=email)
        await bridge.start()
        session_bridges[session_id] = bridge
        print(f"MCP bridge up for {email} — {len(bridge.claude_tools)} tools")
    return session_bridges[session_id]


def _session_id(request: Request) -> str | None:
    """Return the session_id cookie if it maps to an authenticated session."""
    sid = request.cookies.get("session_id")
    return sid if sid and sid in authenticated_sessions else None


# ── Auth endpoints ────────────────────────────────────────────────────────────

@app.get("/login")
async def login():
    auth_url = (
        f"{ISSUER}/protocol/openid-connect/auth"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri=http://localhost:8100/callback"
        f"&scope=openid email"
        f"&prompt=login"  # always show login form, even with active Keycloak session
    )
    return RedirectResponse(auth_url)


@app.get("/callback")
async def callback(code: str):
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{ISSUER}/protocol/openid-connect/token",
            data={
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": code,
                "redirect_uri": "http://localhost:8100/callback",
            },
        )
    actor_email = get_actor_email(resp.json()["access_token"])
    session_id = str(uuid.uuid4())
    authenticated_sessions[session_id] = {"email": actor_email}
    ACTIVE_SESSIONS.inc()
    response = RedirectResponse("/")
    response.set_cookie("session_id", session_id, httponly=True)
    return response


@app.get("/logout")
async def logout(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id:
        bridge = session_bridges.pop(session_id, None)
        if bridge:
            try:
                await bridge.stop()
            except Exception:
                pass  # subprocess may have already exited; cleanup still proceeds
        if session_id in authenticated_sessions:
            authenticated_sessions.pop(session_id, None)
            ACTIVE_SESSIONS.dec()
        sessions.pop(session_id, None)
    response = RedirectResponse("/")
    response.delete_cookie("session_id")
    return response


# ── API endpoints ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    session_id = _session_id(request)
    if not session_id:
        return Response(status_code=401, content="Not authenticated")

    messages = sessions.setdefault(session_id, [])
    bridge = await _get_bridge(session_id)

    messages.append({"role": "user", "content": req.message})
    reply, tool_trace = await run_agent_turn(client, bridge, messages)

    return {"reply": reply, "tool_calls": tool_trace}


@app.post("/api/chat/reset")
async def reset_chat(request: Request):
    """Clear message history for the current session (New Chat)."""
    session_id = _session_id(request)
    if session_id:
        sessions[session_id] = []
    return {"ok": True}


@app.get("/api/tools")
async def tools(request: Request):
    """Live tool list — also used by the frontend to check auth state on load."""
    session_id = _session_id(request)
    if not session_id:
        return Response(status_code=401, content="Not authenticated")
    bridge = await _get_bridge(session_id)
    return {
        "actor": authenticated_sessions[session_id]["email"],
        "tools": [
            {"name": t["name"], "description": t["description"].strip().split("\n")[0]}
            for t in bridge.claude_tools
        ],
    }


@app.get("/")
async def index():
    return FileResponse(_STATIC / "index.html")
