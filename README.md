# Licensing Intelligence MCP

A local proof-of-concept MCP (Model Context Protocol) server that exposes MathWorks licensing and entitlement data to AI agents as two distinct capability surfaces:

- **Read Surface** — customer-facing queries (license status, entitlements, seat counts)
- **CS Action Surface** — role-gated write tools for Customer Service workflows, with full audit logging

Built on Python 3.13 + MCP SDK + SQLAlchemy + SQLite, running over stdio for Claude
Desktop. Now **expanding toward a 3-tier enterprise architecture** (tools → domain
microservices → cloud Postgres) — see [Expansion Phase](#expansion-phase--scale-services--compliance-in-progress).

---

## Project Status

**Phase 1 — the local POC — is complete and demoed.** We are now in **Phase 2:
expanding the POC toward enterprise realism** (real scale, domain microservices,
a compliance gate). See **[TASKS.md](TASKS.md)** for the live tracker.

| Phase | Focus | Status |
|---|---|---|
| POC W1 | Data foundation — schema, models, seeded SQLite | ✅ Complete |
| POC W2 | MCP server + 6 read tools, live in Claude Desktop | ✅ Complete |
| POC W3 | CS write surface — identity gate, 6 write tools, atomic audit log, prompts | ✅ Complete |
| POC W4 | Demo rehearsal (Story 1 + Story 2 live), presentation deck | ✅ Complete |
| POC+ | Custom agent host (`agent/`) + Keycloak OIDC auth | ✅ Complete |
| **Scale** | Deep-hierarchy schema, ~1.5M-row generator, 3-service contracts | 🔄 **In progress** (see below) |

**13 tools + 2 prompts, all verified end-to-end** through both Claude Desktop and a
custom agent host. The scale phase is additive — the live POC keeps working while the
enterprise-grade data layer and services are built alongside it.

---

## What Has Been Built

### MCP Server (`licensing_mcp/`)

**Read tools (open access):**
| Tool | Answers |
|---|---|
| `get_license_status` | Is L-99001 active? Seat utilization? Expiry? |
| `check_user_entitlements` | What can jane.doe run? Any stale activations? |
| `list_licenses_by_entity` | What licenses does Acme Corp hold? |
| `get_license_products` | What products are on this license? |
| `get_license_administrators` | Who manages this license? |
| `search_entitlements` | Which enterprise licenses expire in 60 days? *(elicits narrowing when >50 results)* |

**CS write tools (role-gated, every call audited):**
| Tool | Required Role |
|---|---|
| `add_user_to_license` | CS-L1 |
| `revoke_activation` *(elicitation confirm)* | CS-L1 |
| `reset_installation_slot` | CS-L2 |
| `update_seat_count` | CS-L2 |
| `extend_license_expiry` | CS-L3 |
| `transfer_license_admin` | CS-L3 |
| `get_audit_history` | any CS role |

**MCP prompts (user-invocable from the "+" menu in Claude Desktop):**
- `license_health_review` — full account health check for an entity
- `diagnose_activation_issue` — the CS Tier-1 diagnostic workflow (Story 2 entry point)

### Architecture

```
tools/           MCP interface layer — descriptions, schemas, error shaping
  ↓
cs_executor.py   Write pipeline: resolve identity → role gate → mutate
                 → audit → atomic commit (unaudited writes are impossible;
                 rejections and failures are audited too)
  ↓
data_access/     SQLAlchemy queries standing in for microservice REST calls.
                 In production only this layer changes (→ authenticated HTTP).
  ↓
database.py      Single session factory; LICENSING_DB_PATH env override
                 lets tests run against a throwaway DB copy.
```

Identity: `CS_ACTOR_ID` env var resolved per call against `cs_users`/`cs_roles` —
the POC stand-in for a validated PingID JWT `sub` claim. Permissions live in the
`cs_permissions` table (grants are data changes, not deploys).

### Database (SQLite, `data/licensing.db` — committed for easy collaboration)

Seventeen tables across four schema groups: licensing & entitlement (12),
CS identity & permissions (4), audit log (1). Hybrid-seeded: 99 real companies
from the AWS SaaS Sales dataset + Faker for the rest. ~500 entities, ~800 licenses,
~3,900 users, ~22,000 entitlements, 51 CS reps, 2,000 pre-seeded audit records.

### Demo Scenario (pre-wired, verified live)

- **Entity:** Acme Corp · **License:** `L-99001` — 10 seats, 10/10 occupied, MATLAB + Simulink
- **Demo user:** `jane.doe@acmecorp.com` — entitled to Simulink, stale activation on `MAC-OLD-7291` (94 days, inactive)
- **Demo CS rep:** `rep.sarah@mathworks.com` — CS-L1

Story 2 flow: check entitlements → seats at capacity → find stale activation → confirm + revoke → audit record with the agent's full reasoning chain.

> After running the demo, restore pristine state with `python scripts/seed.py` (then restart Claude Desktop).

### Key Documents

| File | Purpose |
|---|---|
| `project-proposal.md` | Full POC proposal — architecture, tool surface, demo script, success criteria |
| `security-considerations-mcp-access.md` | Production security posture — PingID/OAuth 2.1, service-to-service auth, threat model, POC vs. production gap, real-world MCP auth survey |
| `presentation-and-questions-notes.md` | MCP concepts mapped to this codebase, presentation arc, Q&A prep |
| `slides/` | Slidev presentation deck (apple-basic theme) — `cd slides && npm install && npm run dev` |
| `agent/README.md` | Custom agent host — run instructions, architecture, and the Keycloak auth hand-off |
| `keycloak/` | One-command Keycloak auth (`docker compose up`) — pre-imported realm, client, and DB-matched CS users |
| **`TASKS.md`** | **Scale-phase tracker** — work breakdown, ownership (P1/P2), dependencies, status |
| **`docs/scale-and-services-strategy.md`** | The 3-tier plan (tools → services → cloud DB); locked decisions |
| **`docs/positioning.md`** | Why this exists — spectrum of autonomy + the architectural seams (pitch material) |
| **`db/SCHEMA.md`** | Deep-hierarchy schema — ERD, decisions, MW-fidelity mapping, generator guide |
| **`services/CONTRACTS.md`** | API contracts for the 3 domain services (read + write) — the T2 spec |
| **`compliance/PRD.md`** | Phase-5 license-creation compliance gate (denied-party screening) |

---

## Expansion Phase — Scale, Services & Compliance (in progress)

The POC proves the architecture but doesn't yet *look* like the enterprise. The
scale phase moves to a **3-tier system** — `AI agent → MCP tools → domain
microservices → cloud database` — so the pitch becomes literal: *"swap our
stand-in services for your real microservices; the MCP doesn't change."* Tracked
in [TASKS.md](TASKS.md).

> ⚠️ **Two data models live in this repo — don't confuse them:**
> - **Live POC (today):** flat SQLite at `data/licensing.db`, driven by
>   `licensing_mcp/models.py`. This is what the MCP server and demos run on now.
> - **Scale phase (next-gen):** the **deep-hierarchy Postgres** schema in `db/`,
>   filled by `scripts/generate_bulk.py`. **Not yet wired to the MCP** — the tools
>   repoint to it (via services) in the Phase-3 step. `models.py` is deliberately
>   left untouched until then so the live demo never breaks.

**What's built so far (all on `main`):**
- **Deep schema** — `db/schema.sql` (13 tables), reconciled against the real MW
  service specs. ERD + rationale in [db/SCHEMA.md](db/SCHEMA.md).
- **Bulk generator** — `scripts/generate_bulk.py`: deterministic, streaming
  Postgres `COPY`, ~1.5M realistic rows (free-tier-sized).
- **Service contracts** — [services/CONTRACTS.md](services/CONTRACTS.md): the 3
  domain services (Licensing / Entitlement / Activation), read + write.

**Run the deep-hierarchy DB locally (no cloud, no cost):**

```bash
cd db && docker compose up -d          # persistent Postgres on localhost:5433
LICENSING_PG_URL=postgresql://licensing:licensing@localhost:5433/licensing \
  .venv/bin/python scripts/generate_bulk.py --reset --verify   # ~1.5M rows
docker compose exec db psql -U licensing -d licensing          # explore
```

**Building the services?** Start at [TASKS.md](TASKS.md) → *Workstream B* (the
quickstart there is the same as above), and implement against
[services/CONTRACTS.md](services/CONTRACTS.md).

---

## Setup

### Prerequisites

- Python 3.13
- Claude Desktop (for the full experience) or the MCP Inspector (for tool testing)

### 1. Clone, create venv, install

```bash
git clone https://github.com/rohitmaryada/Licensing-MCP.git
cd Licensing-MCP
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .          # editable install — required for python -m licensing_mcp
```

### 2. Database

`data/licensing.db` is **committed** — you have a ready-to-query database on clone.
To regenerate from scratch (optional; requires a Kaggle token for the
[AWS SaaS Sales dataset](https://www.kaggle.com/datasets/nnthanh101/aws-saas-sales)):

```bash
kaggle datasets download -d nnthanh101/aws-saas-sales -p data/raw --unzip
python scripts/seed.py
```

### 3. Test with the MCP Inspector

```bash
npx @modelcontextprotocol/inspector .venv/bin/python -m licensing_mcp
```

Connect, list tools (you should see 13), and try `get_license_status` with `L-99001`.

### 4. Install in Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "licensing-mcp": {
      "command": "/absolute/path/to/Licensing-MCP/.venv/bin/python",
      "args": ["-m", "licensing_mcp"],
      "env": {
        "CS_ACTOR_ID": "rep.sarah@mathworks.com"
      }
    }
  }
}
```

Fully quit and relaunch Claude Desktop. The server appears under the
sliders icon ("Search and tools"); the two prompts appear in the "+" menu.

> **After any code change**, restart Claude Desktop (or disconnect/reconnect in
> the Inspector) — clients spawn the server once per connection.

### 5. Run the test suite pattern

Tests run against a **copy** of the database via the `LICENSING_DB_PATH` override:

```bash
cp data/licensing.db /tmp/licensing-test.db
LICENSING_DB_PATH=/tmp/licensing-test.db CS_ACTOR_ID=rep.sarah@mathworks.com \
  .venv/bin/python -m pytest   # or the in-memory client scripts
```

---

## Project Structure

```
Licensing-MCP/
├── licensing_mcp/                 # ── THE LIVE POC (flat SQLite) ──
│   ├── models.py                  # SQLAlchemy ORM — all 17 tables
│   ├── database.py                # Session factory + LICENSING_DB_PATH override
│   ├── identity.py                # CS actor resolution + permission checks
│   ├── cs_executor.py             # Write pipeline: gate → mutate → audit → commit
│   ├── elicitation.py             # Spec-compliant elicitation schema base
│   ├── prompts.py                 # MCP prompts (user-invocable)
│   ├── server.py                  # Tool registration + stdio entry point
│   ├── data_access/               # Read/write queries (→ HTTP service calls in prod)
│   └── tools/                     # One file per MCP tool (13 total)
├── data/
│   ├── raw/                       # Kaggle CSV (git-ignored)
│   └── licensing.db               # Seeded SQLite DB (committed) — the LIVE POC db
├── scripts/
│   ├── seed.py                    # Hybrid seeder for the SQLite POC (AWS SaaS + Faker)
│   └── generate_bulk.py           # ── SCALE: bulk Postgres generator (~1.5M rows) ──
├── db/                            # ── SCALE: deep-hierarchy Postgres schema ──
│   ├── schema.sql                 # DDL (13 tables) — reconciled vs. real MW specs
│   ├── SCHEMA.md                  # ERD, decisions, MW-fidelity mapping
│   └── docker-compose.yml         # One-command persistent local Postgres (:5433)
├── services/
│   └── CONTRACTS.md               # ── SCALE: T2 API contracts for the 3 services ──
├── agent/                         # Custom agent host (Claude API loop + MCP bridge + UI)
├── keycloak/                      # One-command Keycloak OIDC auth (docker compose)
├── compliance/PRD.md              # Phase-5 compliance gate spec
├── docs/                          # scale-and-services-strategy.md, positioning.md
├── slides/                        # Slidev presentation deck
├── TASKS.md                       # Scale-phase tracker (ownership, deps, status)
├── project-proposal.md · security-considerations-mcp-access.md · presentation-and-questions-notes.md
├── pyproject.toml
└── requirements.txt
```

---

## Security Reference

See [`security-considerations-mcp-access.md`](./security-considerations-mcp-access.md) for the full production security posture:
- PingID / OAuth 2.1 integration architecture (user identity boundary)
- Service-to-service auth — the MCP server as a registered service consumer (RFC 7523)
- Full threat model (authentication, authorization, prompt injection, data exposure, compliance)
- POC vs. production gap table
- Survey of real-world MCP server auth (Atlassian, MathWorks, MCP spec)

---

## Contributing

This is an internal POC. If you're a collaborator:
1. Complete setup steps above — the DB comes with the clone
2. New tools: one file under `licensing_mcp/tools/`, query logic in `data_access/`, then add the import line in `server.py`
3. Write tools must go through `cs_executor.execute_cs_write()` — never mutate directly
4. Elicitation schemas must inherit from `licensing_mcp.elicitation.ElicitationBase` (MCP spec restricts these to flat primitives)
5. Test against a DB copy: `LICENSING_DB_PATH=/tmp/test.db`

**Working on the scale phase (services / data)?** Start at **[TASKS.md](TASKS.md)** —
it has the work breakdown, ownership (P1/P2), and dependencies. Build services against
[services/CONTRACTS.md](services/CONTRACTS.md); run the deep-hierarchy DB locally per the
[Expansion Phase](#expansion-phase--scale-services--compliance-in-progress) quickstart.
