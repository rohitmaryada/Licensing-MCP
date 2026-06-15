# Custom Agent Host

A self-contained agent that talks to the `licensing-mcp` server and exposes it
through a web chat UI — the same job Claude Desktop does, but built from scratch
so we control the loop, the client, and the interface.

This is the POC equivalent of a production CS-rep copilot. It is currently
**unauthenticated** — adding the auth layer (Keycloak / OIDC) is the next task
(see [Next: Authentication](#next-authentication-keycloak) at the bottom).

---

## What's in here

| File | Role |
|---|---|
| `app.py` | FastAPI host — serves the UI, exposes `/api/chat`, owns one MCP server subprocess for the app's lifetime |
| `agent_loop.py` | The hand-rolled agent loop — Claude API ⇄ tool calls, repeat until done |
| `mcp_bridge.py` | MCP **client** over stdio to `licensing-mcp` (we are the client here) |
| `static/index.html` | Chat UI — renders markdown, shows tool-call chips, Enter-to-send |

The data flow:

```
browser  →  POST /api/chat  →  agent_loop  →  Claude API
                                   ↓ tool calls
                               mcp_bridge  →  licensing-mcp (stdio)  →  SQLite
```

---

## Prerequisites

- **Python 3.13**
- **An Anthropic API key** with credits — get one at
  [console.anthropic.com](https://console.anthropic.com) → API Keys.
  A full demo run costs a few cents.

---

## Setup (first time)

From the **repo root** (`Licensing-MCP/`), not the `agent/` folder:

```bash
# 1. Virtual environment + dependencies
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .                      # editable install — needed for `python -m licensing_mcp`

# 2. API key — copy the template and paste your key into .env
cp .env.example .env
#    then edit .env:  ANTHROPIC_API_KEY=sk-ant-...
```

`.env` is git-ignored — **never commit your key**. The database
(`data/licensing.db`) is already committed, so there's nothing to seed.

---

## Run it

From the repo root:

```bash
.venv/bin/uvicorn agent.app:app --port 8100
```

Wait for:

```
MCP bridge up — 13 tools: get_license_products, ...
Application startup complete.
Uvicorn running on http://127.0.0.1:8100
```

Then open **http://127.0.0.1:8100** in your browser.

> Keep the terminal open — the server runs in it. `Ctrl+C` stops it.
> If you see `address already in use`, something is already on port 8100:
> `pkill -f "uvicorn agent.app"` then re-run.

---

## Try it

Click an example on the welcome screen, or type your own. Two flows to verify:

**Story 1 — query**
> What licenses does Acme Corp have?

Watch it call `list_licenses_by_entity`, then ask follow-ups
("what products does it cover?") — it carries the license ID across turns.

**Story 2 — diagnose & resolve (the CS action flow)**
> jane.doe@acmecorp.com can't activate Simulink on her new laptop. Look into why and resolve it.

It diagnoses (entitlements + seat capacity), finds the stale activation, and
**proposes a revoke — then waits for your confirmation** before executing.
Reply "yes" and it revokes, writes an audit record, and offers the audit trail.

> The revoke **mutates the demo database**. To reset it to pristine state:
> ```bash
> # stop the agent first (it holds a DB connection), then:
> rm -f data/licensing.db && .venv/bin/python scripts/seed.py
> # restart the agent so it picks up the fresh DB
> ```
> `seed.py` is **not** idempotent — it needs a fresh DB, hence the `rm`.

---

## How it works (read before adding auth)

**One server subprocess per app lifetime.** `app.py`'s FastAPI `lifespan`
starts the MCP bridge once at startup and stops it at shutdown — exactly how
Claude Desktop spawns the server once per session. Code changes to the agent or
the MCP server require a **restart** to take effect.

**The agent loop** (`agent_loop.py`) is the core concept: send the conversation
+ tool definitions to Claude; if Claude returns `tool_use` blocks, execute them
via the bridge, append the `tool_result`s, and loop; stop when Claude returns
plain text. Model is `claude-opus-4-8` with adaptive thinking and prompt caching
on the growing prefix.

**Identity today.** The MCP server resolves the acting CS rep from the
`CS_ACTOR_ID` env var (defaults to `rep.sarah@mathworks.com`), set when
`mcp_bridge.py` spawns the server. This is the POC placeholder for a validated
identity — which is exactly what the auth task replaces.

**Sessions** live in an in-memory dict keyed by `session_id` (POC shortcut;
resets on restart).

---

## Next: Authentication (Keycloak)

Goal: gate the agent behind real login so only authorized CS reps can use it —
the open-source realization of **Boundary 1** in
[`../security-considerations-mcp-access.md`](../security-considerations-mcp-access.md)
(§2 PingID/OAuth 2.1). Keycloak is a drop-in OIDC provider you can run locally;
the flow is identical to PingID in production.

**The shape of the work:**

1. **Run Keycloak** (Docker) with a realm, a confidential client for the agent,
   a group like `licensing-agent-users`, and a couple of test users mapped to CS
   roles (e.g. `rep.sarah@mathworks.com` → CS-L1, a CS-L3 user).

2. **Add the OAuth 2.1 Authorization Code + PKCE flow to `app.py`.**
   [Authlib](https://docs.authlib.org/) + Starlette's `SessionMiddleware` is the
   clean path:
   - Unauthenticated request to `/` → redirect to Keycloak login
   - `/auth/callback` → validate the token, store the user in the session
   - A `require_user` dependency that protects `/api/chat` and `/api/tools`
   - Reject users not in the `licensing-agent-users` group (this is the
     "10 of 500 reps" control from the security doc §1)

3. **Flow the authenticated identity into the actor.** The logged-in user's
   email is the real CS actor. For the POC, validate it matches a `cs_users`
   row and use it where `CS_ACTOR_ID` is read today. (Flowing per-user identity
   dynamically all the way to the MCP server — so two different reps in two
   browser sessions act as themselves — is the production step beyond that, and
   maps to putting an OAuth token on the MCP connection itself.)

4. **UI:** show "logged in as <user> · logout" in the header; the browser only
   needs the session cookie, so `static/index.html` barely changes.

**Reference:** the official MCP authorization tutorial uses Keycloak end-to-end
and is the closest worked example —
<https://modelcontextprotocol.io/docs/tutorials/security/authorization>.

Suggested new files when you build this:
```
agent/auth.py              # OIDC config, login/callback/logout, require_user
keycloak/docker-compose.yml
keycloak/realm-licensing.json   # pre-imported realm so setup is one command
```
Add `authlib`, `itsdangerous`, `httpx` to `requirements.txt`, and the Keycloak
URLs + a session secret to `.env.example`.
