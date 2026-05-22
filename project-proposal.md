# Licensing Intelligence MCP: Agentic Access to Licensing & Entitlement Data

**Project Type:** Proof of Concept (POC)  
**Author:** Rohit Maryada  
**Platform:** Local (MacBook Pro M4), Python  
**Target Demo Audience:** Engineering, Product, and Leadership  
**Timeline:** 3–4 weeks

---

## Executive Summary

MathWorks licensing and entitlement systems today serve two distinct human populations: **customers** (who query their own account data through external-facing UIs) and **Customer Service representatives** (who query, diagnose, and mutate customer data to resolve issues — under strict role-based permissions and full audit logging).

The paradigm is shifting for both. AI agents are increasingly the consumers of enterprise data, and they operate fundamentally differently than humans: no UI, no session, no patience for click-through workflows. They query, reason, synthesize, and act on behalf of a user in ways that require clean, structured, callable interfaces.

This project proposes building a **Licensing Intelligence MCP (Model Context Protocol) server** — a local POC that exposes the licensing and entitlement domain to AI agents as two distinct capability surfaces:

- **A read-only Query Surface** — for customer-facing workflows, answering questions like *"Is this enterprise customer entitled to use MATLAB Compiler Toolbox?"* or *"Which licenses under Acme Corp expire in the next 30 days?"*

- **A role-scoped CS Action Surface** — for Customer Service workflows, where an AI agent assists a CS rep in diagnosing and resolving customer issues, with every action bound to the rep's permissions and written to an audit trail

This is not a chatbot wrapper around a database. It is a **structured, governed capability surface** where each tool corresponds to a well-defined domain operation, each write action is audited, and access is role-scoped from the ground up.

---

## The Problem: Two Paradigm Shifts, One Interface Layer

### The Customer-Facing Stack

Today the licensing stack serves customers through a familiar chain:

```
Database (MS SQL Server)
    → Microservices (REST APIs)
        → External-facing UIs
            → Customer (human)
```

Every assumption baked into this stack — session tokens, paginated responses, HTML dashboards — is optimized for a human at the end.

### The CS-Facing Stack

In parallel, Customer Service representatives work through internal tooling with a materially different contract:

```
Database (MS SQL Server)
    → Microservices (REST APIs)
        → Internal CS tooling / admin UIs
            → CS Rep (human, role-scoped, audited)
```

CS reps can do things customers cannot: they can edit licenses, provision seats, revoke activations, transfer admins, and fix broken entitlements. Everything they do is:
- **Role-gated** — a tier-1 rep cannot do what a tier-3 rep can
- **Audited** — every action produces an audit record: who, what, when, why
- **Reasoned** — the business justification must be captured, not just the action

### What Changes When Agents Consume These Systems

Agentic AI workflows break the assumptions in both stacks simultaneously:

- The agent has **no UI** — it receives structured data and reasons over it
- The agent needs **domain-aware tools** — not raw REST endpoints that require it to know your URL scheme
- Write operations need **identity + permissions passed at call time**, not encoded in a user session
- Audit records need to capture **the agent's reasoning chain**, not just the action

The ask from leadership is correct: this is not an AI wrapper problem. It requires rethinking the interface layer for a consumer that is fundamentally different from a human browser session.

---

## Two Agent Personas, One MCP Server

### Persona 1: The Query Agent

Read-only. Customer-scoped. Answers "what is the current state of X?"

Intended consumers: customer self-service agents, internal analytics workflows, account management tooling.

### Persona 2: The CS Action Agent

Read + write. Role-scoped to a CS representative's permission set. Every write produces an audit record. The agent proposes actions; actions execute under the rep's identity.

Intended consumers: CS rep copilots, tier-1 deflection agents, automated resolution pipelines for well-understood issue patterns.

The key design insight: **these are not two separate servers**. They are two scopes of the same server, differentiated by the caller's identity context. An unauthenticated call gets read-only tools. A call with a CS rep's credentials gets read + write tools, scoped to what that rep's role permits.

---

## Proposed Solution: `licensing-mcp`

### What is MCP?

The **Model Context Protocol (MCP)** is an open standard developed by Anthropic that allows AI agents to securely access external data sources and tools:

- A developer builds an **MCP server** — a process that exposes typed tools and optionally readable resources
- An AI client (Claude Desktop, Claude in Cowork, Cursor, etc.) **installs** the server via a config file
- The agent calls those tools as part of a conversation or workflow, with full awareness of what each tool does and what it returns

MCP is to agents what REST APIs are to web applications — the interface contract between consumer and provider.

### Architecture

```
┌─────────────────────────────────────────┐
│         AI Agent (Claude Desktop)       │
│  "jane.doe@acme.com can't run Simulink" │
└──────────────────┬──────────────────────┘
                   │  MCP Protocol (stdio)
                   ▼
┌─────────────────────────────────────────┐
│          licensing-mcp Server           │
│  ┌─────────────────────────────────┐    │
│  │        Tool Router              │    │
│  │  • Identity resolver            │    │
│  │  • Role/permission gate         │    │
│  │  • Audit log writer             │    │
│  └──────────────┬──────────────────┘    │
│                 │                        │
│  ┌──────────────▼──────────────────┐    │
│  │  Read Tools  │  CS Write Tools  │    │
│  │  (open)      │  (role-gated)    │    │
│  └──────────────┴──────────────────┘    │
└──────────────────┬──────────────────────┘
                   │  SQLAlchemy ORM
                   ▼
┌─────────────────────────────────────────┐
│         SQLite (local, POC)             │
│  Licensing schema + Entitlement schema  │
│  + CS identity schema + Audit log       │
└─────────────────────────────────────────┘
```

---

## MCP Tool Surface

### Read Tools (Query Surface — Open Access)

| Tool | Description | Example |
|------|-------------|---------|
| `get_license_status` | License status, expiry, seat count, type | *"Is license L-20041 active?"* |
| `check_user_entitlements` | Products a user is entitled to, with activation state | *"What can jsmith@acme.com run?"* |
| `list_licenses_by_entity` | All licenses for a company, university, or individual | *"List MIT's licenses"* |
| `get_license_products` | Product catalog on a license | *"What toolboxes are on L-20041?"* |
| `get_license_administrators` | Admin users who manage a license | *"Who administers Acme's enterprise license?"* |
| `search_entitlements` | Natural language → structured query | *"Which enterprise customers have unused seats expiring this quarter?"* |

### CS Write Tools (Action Surface — Role-Gated)

Every write tool accepts a `cs_actor_id` (the rep invoking the action) and a `reason` string (the business justification). The server validates the actor's role before executing and writes both to the audit log.

| Tool | Required Role | Description | Example |
|------|--------------|-------------|---------|
| `add_user_to_license` | CS-L1 | Add a user to a license's user list | *"Add jane.doe@acme.com to license L-20041"* |
| `revoke_activation` | CS-L1 | Deactivate a product activation (frees a seat) | *"Revoke the Simulink activation on her old laptop"* |
| `reset_installation_slot` | CS-L2 | Clear an installation record so user can reinstall on new machine | *"Reset her installation slot — she got a new laptop"* |
| `update_seat_count` | CS-L2 | Increase or decrease seat count on a license | *"Acme purchased 10 more seats — update L-20041"* |
| `extend_license_expiry` | CS-L3 | Extend a license's expiration date | *"Give them a 30-day extension while their renewal processes"* |
| `transfer_license_admin` | CS-L3 | Reassign license administration | *"The old admin left the company — transfer to the new IT contact"* |

**Role levels (simplified for POC):**
- `CS-L1` — Tier 1 support: user management, basic activation fixes
- `CS-L2` — Tier 2 support: installation management, seat adjustments
- `CS-L3` — Tier 3 / account management: contract-level changes

### The Audit Record: Where AI Adds Unique Value

In a human CS workflow, the audit record captures: *who, what, when* — and a free-text "reason" field that a rep fills in, often poorly ("fixed issue," "customer request").

With an AI agent, the audit record is materially richer. The agent's reasoning chain — what it observed, why it concluded the action was appropriate, what alternatives it considered — **becomes** the audit record automatically. A sample audit entry:

```json
{
  "audit_id": "AUD-001",
  "timestamp": "2026-05-19T14:32:11Z",
  "cs_actor": "rep.sarah@mathworks.com",
  "cs_role": "CS-L1",
  "action": "revoke_activation",
  "target": { "user": "jane.doe@acme.com", "product": "Simulink", "machine_id": "MAC-OLD-7291" },
  "reason": "User reported inability to activate Simulink on new machine. Checked entitlements — user is on license L-20041 which includes Simulink. Seat count (10) is at capacity. Identified an inactive activation on a decommissioned machine (last heartbeat 94 days ago). Revoking this activation to free a seat for the new machine.",
  "outcome": "success",
  "before": { "seat_utilization": "10/10" },
  "after": { "seat_utilization": "9/10" }
}
```

This level of audit quality is structurally impossible with a human filling in a text box. It's automatic with an agent.

---

## Data Model

### Licensing & Entitlement Schema (Existing Domain)

```sql
entities          -- companies, universities, individuals, government labs
entity_types      -- enterprise, academic, individual, government
licenses          -- license records linked to entities
license_types     -- enterprise, academic, individual, concurrent, trial
license_products  -- products on a given license
products          -- MATLAB, Simulink, toolboxes (~20 products)
license_users     -- end users on a license
license_admins    -- admin users who manage a license
entitlements      -- what a user is entitled to (license + membership derived)
installations     -- where software is installed (machine, OS, install date)
activations       -- active activations (user, product, machine, last_heartbeat)
```

### CS Identity & Permissions Schema (New for CS Surface)

```sql
cs_users          -- CS rep accounts (id, email, name, tier)
cs_roles          -- CS-L1, CS-L2, CS-L3 role definitions
cs_permissions    -- which roles can call which write tools
cs_role_members   -- which users have which roles
```

### Audit Log Schema (New for CS Surface)

```sql
cs_audit_log      -- immutable append-only log of every write tool call
                  -- (audit_id, timestamp, cs_actor_id, action, target_entity,
                  --  target_license, tool_name, args_json, reason, outcome,
                  --  before_state_json, after_state_json)
```

**Target dataset scale:**
- ~500 entities, ~1,000 licenses, ~5,000 users, ~8,000 entitlement records
- ~50 CS users across 3 role tiers
- ~2,000 synthetic audit records (pre-seeded to make audit queries interesting)

---

## Technical Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| MCP Server | Python + `mcp` SDK (official Anthropic) | Best SDK maturity, M4-native |
| Database | SQLite (local) | Zero infra, mirrors MS SQL schema concepts |
| ORM | SQLAlchemy | Clean query abstraction, easy to swap DB later |
| Identity (POC) | Static CS user table + env var for actor | Simulates auth without full OAuth for demo |
| Audit log | SQLite append-only table | Real audit behavior, queryable in demo |
| Data generation | Faker + Pandas + custom scripts | Rapid realistic data seeding |
| Transport | stdio (local) | Standard for local MCP, no networking needed |
| Client | Claude Desktop | Install via `claude_desktop_config.json` |

### Installation in Claude Desktop

```json
{
  "mcpServers": {
    "licensing-mcp": {
      "command": "python",
      "args": ["-m", "licensing_mcp"],
      "cwd": "/path/to/licensing-mcp",
      "env": {
        "CS_ACTOR_ID": "rep.sarah@mathworks.com"
      }
    }
  }
}
```

The `CS_ACTOR_ID` env var is how the POC simulates identity — the server resolves that actor's role and gates write tools accordingly. In production, this becomes a proper auth token.

---

## Implementation Plan

### Week 1 — Data Foundation

- [ ] Source public dataset from Kaggle (SaaS/subscription/CRM data)
- [ ] Design final SQLite schema: licensing + entitlement + CS identity + audit log
- [ ] Write data generation scripts (Faker-based seeding for all schemas)
- [ ] Load and validate full dataset including CS users and pre-seeded audit records
- [ ] Write SQLAlchemy models for all tables

**Milestone:** A fully seeded, queryable local database covering all four schemas.

### Week 2 — Read Tool Layer

- [ ] Initialize Python project with `mcp` SDK
- [ ] Implement all 6 read tools with typed inputs/outputs
- [ ] Write precise tool descriptions (agents use these to select the right tool)
- [ ] Test with `mcp dev` inspector
- [ ] Install in Claude Desktop, run first live demo queries

**Milestone:** All read tools working in Claude Desktop.

### Week 3 — CS Write Tools + Audit Layer

- [ ] Implement identity resolver and role/permission gate
- [ ] Implement all 6 CS write tools, each enforcing role checks
- [ ] Implement audit log writer called by every write tool
- [ ] Add a `get_audit_history` read tool (CS reps can ask "what happened to this license?")
- [ ] Test write tools end-to-end: CS rep persona → tool call → DB mutation → audit record
- [ ] Build and rehearse the full demo script (both scenarios)

**Milestone:** Full read + write surface working, audit log populated by live demo actions.

### Week 4 — Buffer + Presentation Prep

- [ ] Fix bugs surfaced during rehearsal
- [ ] Create architecture diagram for the presentation
- [ ] Prepare "Path to Production" talking points
- [ ] Optional stretch: package as `.plugin` file for Cowork installation

---

## Demo Script

The demo tells two connected stories — run them back to back for maximum effect.

### Story 1: Customer Query Agent
*Setting: An agent answering questions about an enterprise account*

1. *"What licenses does Acme Corp have?"* → `list_licenses_by_entity`
2. *"Is their main enterprise license still active, and when does it expire?"* → `get_license_status`
3. *"What products does it cover?"* → `get_license_products`
4. *"Which enterprise customers have seats expiring in the next 60 days?"* → `search_entitlements`

**Narrative:** Clean read-only access. Agent synthesizes multi-table answers from plain language. No SQL. No dashboard.

### Story 2: CS Action Agent
*Setting: A CS rep asking the agent to resolve a customer issue*

1. *"User jane.doe@acme.com says she can't activate Simulink on her new laptop."*
   → Agent calls `check_user_entitlements` → confirms she IS entitled to Simulink
2. *"Why can't she activate?"*
   → Agent calls `get_license_status` → seats are at capacity (10/10)
3. *"Are any of those activations inactive?"*
   → Agent calls a targeted query → finds an activation with a heartbeat 94 days ago on a decommissioned machine
4. *"Revoke that activation."*
   → Agent calls `revoke_activation` with `cs_actor_id=rep.sarah@mathworks.com`, `reason=<agent's reasoning>`
   → Seat freed. Audit record written with full reasoning.
5. *"Show me the audit trail for this license."*
   → Agent calls `get_audit_history` → shows the action just taken, plus prior history

**Narrative:** The agent doesn't just answer — it diagnoses, proposes, acts, and audits. And the audit record is richer than anything a human would have written. This is the moment that lands with leadership.

---

## Success Criteria

| Criterion | What "Done" Looks Like |
|-----------|----------------------|
| All 12 tools callable | Agent invokes every tool without errors in a live demo |
| Role gate works | A CS-L1 actor cannot call `extend_license_expiry` — server rejects with a clear message |
| Write → audit | Every successful write tool call produces a verifiable audit record |
| Multi-step reasoning | Agent chains 3+ tool calls to diagnose and resolve the CS scenario |
| Audit quality | Agent-generated audit reason is demonstrably more informative than a human free-text field |
| Non-technical legibility | A product manager watching Story 2 understands the value without explanation |
| Installable | Another engineer runs it in Claude Desktop in under 10 minutes |

---

## Path to Production

This POC answers the proof-of-concept question across both dimensions. If it succeeds, the next conversations are:

**Near-term (3–6 months):**
- Replace SQLite with the real MS SQL Server — SQLAlchemy makes this a config change
- Replace env-var identity with real auth token (OAuth / internal SSO)
- Scope to one CS tier (L1) and one issue pattern (activation fixes) — ship a narrow agent copilot to real CS reps
- Instrument the audit log to measure resolution time vs. manual baseline

**Medium-term (6–12 months):**
- Expand write tool surface and role tiers
- Multi-agent: a licensing agent that escalates to a billing agent or an account management agent
- Customer-facing agent: a self-service bot that answers "why can't I activate?" without CS involvement for Tier-1 issues
- Hosted MCP deployment with proper multi-tenancy and audit compliance

**The wedge use case:** The most defensible first production target is a **CS Tier-1 Copilot** — an agent that handles the "user can't activate / seat limit hit" pattern end-to-end. It's high-volume, well-understood, low-risk (activation revocation is reversible), and the ROI is measurable in handle time.

---

## Risks and Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| Public dataset doesn't map cleanly to licensing schema | Medium | Fall back to fully synthetic data — Faker is sufficient |
| `search_entitlements` NL→SQL quality is inconsistent | Medium | Scope to fixed parameterized queries for demo; full NL→SQL in v2 |
| Write tool scope creep extends timeline | Medium | Hard-cap CS write tools at 6 for the POC; stub anything beyond that |
| MCP SDK API changes (it's young) | Low | Pin SDK version; monitor changelog |
| Demo environment instability (Claude Desktop updates) | Low | Freeze desktop version before final rehearsal |

---

## Open Questions (For Team Discussion)

1. **CS role model:** Does the simplified 3-tier (L1/L2/L3) model map reasonably to how CS is actually structured at MathWorks? Getting this right matters for making the demo resonate with CS stakeholders.
2. **Audit compliance:** In production, audit logs have legal and compliance implications. Is there a compliance team that should be looped in early if this moves toward production?
3. **The self-service question:** For the customer-facing query surface, is there appetite to eventually expose this directly to customers (i.e., they use an agent to query their own account, rather than calling CS)? That changes the business case significantly.
4. **Canonical demo customer:** Is there a well-known synthetic "Acme Corp" equivalent used internally for demos that we should model the test data after?
5. **Wedge issue pattern:** What is the highest-volume, most predictable Tier-1 CS issue today? That should be the first write tool we build.

---

*This proposal was drafted based on a 3–4 week local POC timeline targeting a cross-functional demo audience. It is intended as a starting point for team discussion, not a finalized spec. Revised to include Customer Service agent workflow, role-based access control, and audit trail architecture.*
