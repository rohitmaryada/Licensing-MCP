# Architecture Deep-Dive — for the technical audience

A companion to [demo-video-script.md](demo-video-script.md): a technical scene
(and Q&A backup) that shows **how the MCP server is built** and, most importantly,
**where the LLM sits between the user and the enterprise data**. Add this as a new
scene after "Why MCP" (Scene 3) or expand "How it works" (Scene 4).

---

## The one idea to land: the LLM is a *bounded reasoning layer*, not a data path

The single most important architectural point for a technical crowd:

> **The LLM sits between the user and the tools — never between the user and the
> data.** It reasons over the request and decides *which tool to call*, but it
> never touches the database, never sees a credential, and never writes a line of
> SQL. It only ever sees the **structured results** the tools hand back.

Everything the model can do is a **known, typed tool**. Every *action* is checked
and audited by **deterministic server code** — tied to the authenticated rep, not
to the model's discretion. That's what makes it safe to point at real systems.

---

## The request flow (end to end)

```
                    ┌─────────────────── AGENT HOST ───────────────────┐
                    │                                                    │
  CS rep            │   ②           ③              ④                    │        ⑥
 (browser)  ──①──►  │  LLM (Claude) ──picks──► MCP client ──MCP/JSON──► │ ──► MCP SERVER ──► Domain service ──► DB
  "why can't        │  reasons over    a tool    bridge      -RPC over  │      tools →         (Licensing /       (owns
   Jane activate?"  │  NL + tool defs  + args    (stdio)     the wire   │      cs_executor →    Entitlement /     the
      ▲             │                                                    │      data_access      Activation)       data)
      │             │        ▲  the LLM lives HERE                       │        │                  ▲
      │  Keycloak   │        │  (sees only structured tool RESULTS,      │        │  ⑤ writes pass:  │ Boundary 2:
      │  OIDC       │        │   never the DB, never credentials)        │        │  gate→mutate→    │ service auth
      │ (Boundary 1)│        └────────────── ⑦ result flows back up ─────┼────────┘  audit→commit    │ (signed token)
      └──────⑧ plain-English answer ◄──────────────────────────────────┘
```

1. **Rep authenticates** (Keycloak / OIDC — **Boundary 1**) and asks in plain English.
2. The **agent host** sends the conversation **+ the tool catalog** to the **LLM**.
3. The **LLM reasons** and emits a `tool_use` — *which* tool, *what* arguments.
   It stops there; it does not fetch anything itself.
4. The host's **MCP client bridge** forwards the call over the **MCP protocol**
   (JSON-RPC) to the MCP server — the same protocol Claude Desktop would use.
5. **Reads** go straight to `data_access`. **Writes** funnel through **`cs_executor`**:
   resolve identity → **role gate** → mutate → **audit** → atomic commit.
6. `data_access` calls the owning **domain microservice** over HTTP (**Boundary 2**:
   service auth); the service queries the **database**.
7. The **structured result** travels back up — service → tool → MCP → host. The
   LLM receives a **typed, scoped result object**, not raw rows or SQL.
8. The LLM composes the **natural-language answer**. Multi-step tasks loop 2–7.

---

## How the MCP server is built (the layers)

The server is deliberately layered so the security-critical parts live in one
reviewed place and the data source is swappable:

| Layer | Responsibility | Why it matters |
|---|---|---|
| **`tools/`** (14 tools) | One file per tool: the MCP name, typed input schema, and error shaping. Thin. | This *is* the model's entire surface. A tool that isn't here can't be called. |
| **`cs_executor.py`** | The write pipeline: identity → **role gate** → mutate → **audit** → atomic commit. Every write funnels through it. | An **un-audited or un-authorized write is structurally impossible** — not a convention, an invariant. |
| **`data_access/`** | The **swap seam**. Same function signatures; the body is SQLAlchemy (POC) **or** `httpx` calls to the domain services (production). | *"Only this layer changes."* The tools and the LLM don't know or care where the data comes from. |
| **`identity.py`** | Resolves the acting CS rep → role → permissions. | Authorization is data-driven and server-side, decoupled from the model. |

Two **independent trust boundaries**, never conflated:
- **Boundary 1 — user → system:** Keycloak / OIDC today, PingID / OAuth 2.1 in prod. *Who is asking.*
- **Boundary 2 — MCP server → services:** signed service token. *Which service is calling.*

And the payoff of the `data_access` seam: **swap the stand-in services for the real
enterprise microservices and the agent, the tools, and the LLM don't change at all.**

---

## Video narration for this scene (~55s, technical)

> Let's look under the hood — because *where the model sits* is the whole story.
> When a rep asks a question, the agent host hands the request, plus the catalog of
> available tools, to the language model. This is the key: **the LLM sits between
> the user and the tools — not between the user and the data.** It reasons about
> the request and decides which tool to call and with what arguments — but it never
> touches the database, never sees a credential, and never writes a line of SQL. It
> only ever sees the structured result a tool hands back. That tool call travels
> over the open MCP protocol to our server, where — for any *write* — it passes
> through a single gate: the rep's role is checked and the action is permanently
> audited *before* it ever reaches the data. Then the tool calls a domain
> microservice that owns the data, and the result flows back up for the model to
> turn into a plain-English answer. So the model is powerful at reasoning, but
> **bounded** — every capability is a known tool, and every action is governed by
> deterministic server code, not by trusting the model. That's what makes it safe
> to put in front of real enterprise systems.

---

## Diagram blueprint (for Rohit K — same style as the other slides)

**Title:** *"Where the LLM sits — a bounded reasoning layer"*
**Theme:** navy background, teal accent, white headings, muted-gray sublabels (match the deck).

**Layout, left → right, five zones with numbered arrows between them:**

1. **Rep (browser)** — small user glyph; a teal badge underneath: *"Keycloak / OIDC · Boundary 1"*.
2. **Agent host** (a container box) holding two stacked pills:
   - **LLM (Claude)** — *reasons over NL + tool defs; picks a tool* — **highlight this box** (teal border) with a callout line: *"The LLM lives here — it never touches data or credentials; it only sees structured tool results."*
   - **MCP client bridge** — *speaks MCP (JSON-RPC)*.
3. **MCP server** (a container box) with three stacked pills, top-to-bottom:
   - **Tools** (14) — *the model's entire surface*
   - **cs_executor** — *gate · audit · atomic* — small lock icon
   - **data_access** — *swap seam: SQL ↔ HTTP* — dashed outline to signal "swappable"
4. **Domain services** — three chips: *Licensing · Entitlement · Activation*; a teal badge: *"service auth · Boundary 2"*.
5. **Database** — cylinder — *owns the data*.

**Arrows (label them 1–8** to match the flow above; keep the return path ⑦→⑧ as a
lighter arrow going right→left back to the rep). **Two accent callouts:** the LLM
box, and the `data_access` "swap seam."

---

## Q&A backup (for the technical crowd)

- **"Does the model see our data?"** Only the structured output of the specific
  tools it's allowed to call, scoped to that query — never the raw database, never
  credentials, never anything outside the tool's result shape.
- **"What stops it from doing something dangerous?"** The tool surface is the only
  thing it can do; every write is role-gated and audited by deterministic server
  code tied to the authenticated user. The model can't exceed the tools *or* the
  rep's permissions — we saw that live when the L1 rep was denied an L3 action.
- **"Where does the model run?"** Claude via API today; the agent loop is
  model-agnostic, so a self-hosted open model behind the same interface is a
  drop-in — which keeps *both* the data **and** the model inside the enterprise.
- **"How do you go to production?"** Change one layer — `data_access` — from SQL to
  authenticated HTTP calls to the real services. Tools, agent, and LLM are untouched.
- **"Is it really MCP-standard?"** Yes — the server speaks the same protocol Claude
  Desktop uses; our custom agent is just another MCP client. Any MCP-capable client
  can drive it.
