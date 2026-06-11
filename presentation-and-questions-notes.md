# MCP Concepts, Presentation Guide & Interview Prep

**Project:** Licensing Intelligence MCP
**Author:** Rohit Maryada
**Purpose:** Reference for explaining this project — to a team, a technical audience, or an interviewer.

---

## 1. Every MCP Concept, Mapped to This Codebase

The learning is being able to point at any file and explain why it exists.

| MCP concept | Where it lives | One-sentence explanation |
|---|---|---|
| **Server + transport** | `licensing_mcp/server.py` → `mcp.run(transport="stdio")` | The server is a process reading JSON-RPC 2.0 off stdin and writing to stdout; Claude Desktop spawns it as a subprocess. No port, no network — process isolation is the security boundary. |
| **Tools (model-invoked)** | `licensing_mcp/tools/*.py`, `@mcp.tool()` | A tool is a typed function the *model* chooses to call. The decorator reads type hints to generate the JSON Schema and the docstring to generate the description. |
| **Tool descriptions as routing** | Docstrings in every tool — incl. the "Do NOT use this for X" lines | Claude picks tools by reading descriptions, not code. Negative guidance prevents misrouting between similar tools. Prompt engineering embedded in the API contract. |
| **Tool results → grounding** | Dicts returned by `data_access/` — computed fields like `days_until_expiry`, `seat_utilization` | The result is injected into Claude's context window as text; Claude reads it and generates the answer. Pre-computing derived fields = better answers in fewer turns. |
| **Elicitation (server → user)** | `tools/search_entitlements.py` (narrow large result sets), `tools/revoke_activation.py` (confirm with computed context) | The server pauses mid-execution, asks the human a structured question, resumes with the answer. The only mechanism where *server code* talks to the user directly. |
| **Elicitation spec constraints** | `licensing_mcp/elicitation.py` → `ElicitationBase` | Flat primitives only — no unions (`Optional[X]` → `anyOf` is rejected), no null defaults. Debugged against a strict client; the wire format and the SDK abstraction are different layers. |
| **Prompts (user-invoked)** | `licensing_mcp/prompts.py`, `@mcp.prompt()` | The third primitive: named conversation starters the *user* picks from a menu ("+" in Claude Desktop). Tools = model decides; prompts = human decides. |
| **The three-primitive model** | tools / prompts / resources (resources deliberately unused) | Resources are app-attached context. Knowing what you *didn't* need is part of the design. |
| **Identity at call time** | `licensing_mcp/identity.py` — resolved per call, never cached | Matches token semantics: roles change, tokens expire. The env var is a placeholder for a JWT `sub` claim; the function signature is the production seam. |
| **Authorization as data** | `cs_permissions` table + `has_permission()` | Granting a role a tool is a row insert, not a deploy — mirrors IdP group management. |
| **Atomic audit** | `licensing_mcp/cs_executor.py` — one session, one commit for mutation + audit | Audit record and mutation succeed or fail together. An unaudited write is structurally impossible. Rejections and failures are audited too. |
| **Layered architecture** | `tools/` → `data_access/` → `database.py` | The interface contract is insulated from the data source. Production swaps SQLAlchemy bodies for authenticated HTTP calls; nothing above changes. |

### Meta-lessons (from debugging, not design)

1. **Spec vs SDK vs client — three validators, three strictness levels.** Code passed the Python SDK's validation and in-memory tests, then failed against the MCP Inspector's strict Zod validation. Cross-client testing is not optional.
2. **Process lifecycle.** MCP clients spawn the server once per connection. "My fix didn't work" was actually "my fix isn't running." Reconnect after every code change before judging a fix.
3. **Response metadata is part of the contract.** `filters_applied` once under-reported the filters actually used; Claude would have narrated a wrong story confidently. Whatever a tool returns, the agent treats as truth.

---

## 2. Presenting to a Technical Audience — the Five-Beat Arc

**Beat 1 — The premise (30s).** "Our licensing stack was built for humans at the end of a browser session. AI agents are a new consumer type: no UI, no session, structured calls — and they *act* on behalf of users. That requires rethinking the interface layer, not wrapping a chatbot around a database."

**Beat 2 — The architecture (2m).** Three layers: tool surface → data access → datastore. Land this sentence: *"MCP is to agents what REST is to web apps — an interface contract. And like REST, it's not a security boundary; security lives in the layers around it."* Then the two-surface design: one server, two scopes, differentiated by caller identity.

**Beat 3 — The live demo (5m).** Story 1 (read chain), then Story 2 (diagnose → confirm → revoke → audit). The moment that lands: show the agent-written audit record (`AUD-02001`, full reasoning chain in `reason`) next to a typical human entry ("fixed issue"). That contrast does more than any slide.

**Beat 4 — Security posture (2m).** One slide from the POC-vs-production gap table (security doc §7). Key sentence: *"Every gap is a known engineering problem using infrastructure we already operate — PingID for user identity, our existing service-registration process for the server's identity. Nothing requires novel tooling."*

**Beat 5 — The wedge (1m).** "First production target: the CS Tier-1 activation-fix copilot — high-volume, well-understood, reversible actions, ROI measurable in handle time."

**Avoid:** walking through code, explaining JSON-RPC, demoing the Inspector. Technical audiences trust working software plus honest gap analysis.

---

## 3. Interview Q&A

**"Walk me through what you built."**
> A Model Context Protocol server exposing a licensing/entitlement domain to AI agents as two capability surfaces: an open read surface — six query tools — and a role-gated write surface for customer-service workflows — six mutation tools plus audit history. Three-layer architecture: MCP tool definitions, a data-access layer standing in for our microservices, and the datastore. Every write goes through a single executor pipeline: resolve identity, check role permission, mutate, write audit, commit atomically.

**"How does authorization work?"**
> Two independent boundaries. Who's calling the server — in the POC an env var, designed to be replaced by a validated JWT claim from our IdP; the resolution function is the seam. And what the server itself may call downstream — service identity, our standard asymmetric-key registration (OAuth 2.0 Client Credentials + private_key_jwt, RFC 7523). The role-to-tool mapping lives in a permissions table, so grants are data changes. Rejections are audited, not just denied — a tier-1 rep probing a tier-3 tool is a signal.

**"What was the hardest technical problem?"**
> Elicitation spec compliance. The MCP wire format for mid-execution user prompts allows only flat primitive schemas — no unions, no null defaults. Pydantic's natural idioms produce both. The SDK's validation was looser than the spec, so it only surfaced against a strict client. I ended up with a base model that sanitizes the generated schema, and a habit: validate against the spec, not just the SDK.

**"Why MCP instead of an API + function calling?"**
> Function calling is per-app plumbing — each client integration is bespoke. MCP standardizes discovery, invocation, and the human-in-the-loop pieces (approval, elicitation), so one server works in any compliant client. Strategically: we define our domain's capability surface once, and it works in whatever agent products emerge.

**"What's the business value?"**
> Three things. Deflection and handle time — the tier-1 "can't activate, seats full" pattern is high-volume and the agent resolves it end-to-end. Audit quality — the agent's reasoning chain becomes the audit record automatically, richer than any free-text field a human fills in; that's a compliance asset. And optionality — the same read surface that powers a CS copilot powers customer self-service later, without rebuilding.

**"What would you do differently / what's missing for production?"** (tests self-awareness)
> Row-level scoping is the biggest gap — in the POC a rep can query any customer; production must scope reps to assigned accounts. Then real token validation, gateway rate limiting, and moving the audit log to an append-only store the actor can't modify. None are research problems; all are table stakes I'd sequence before any rollout.

**"How do you prevent the agent from doing something destructive?"**
> Defense in depth. Client-side: Claude Desktop's per-tool approval mode. Server-side: role gating per call, server-driven elicitation confirmation on destructive tools showing computed context (heartbeat age, seat impact), narrow single-purpose tools with no "run query" escape hatch, and atomic audit of every outcome including rejections. And the write tools are designed to be reversible where possible — a revoked activation can simply be re-activated.

**"How would this scale / move to production?"**
> Transport: stdio → Streamable HTTP behind an API gateway. Identity: env var → OAuth 2.1 + PKCE against PingID, validated per request. Data: SQLite → calls to existing microservices through the data-access seam — the tool layer doesn't change. The MCP server becomes a registered service consumer like any other, going through the same business-case approval and key registration we use today.

---

## 4. The Honest Framing on AI-Assisted Development

The typing was never the valuable part. The durable contributions were: choosing the domain and the two-surface design, making the architecture calls (layer separation, audit atomicity, permissions-as-data), pushing on the security model before any code existed, and debugging spec compliance against a real client. Those decisions are what get defended in design review — and they're what this document captures.
