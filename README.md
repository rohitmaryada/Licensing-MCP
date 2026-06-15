# Licensing Intelligence MCP

A local proof-of-concept MCP (Model Context Protocol) server that exposes MathWorks licensing and entitlement data to AI agents as two distinct capability surfaces:

- **Read Surface** — customer-facing queries (license status, entitlements, seat counts)
- **CS Action Surface** — role-gated write tools for Customer Service workflows, with full audit logging

Built on Python 3.13 + MCP SDK + SQLAlchemy + SQLite, running over stdio for Claude Desktop.

---

## Project Status

| Week | Focus | Status |
|---|---|---|
| Week 1 | Data foundation — schema, models, seeded database | ✅ Complete |
| Week 2 | MCP server + 6 read tools, inspector-tested, live in Claude Desktop | ✅ Complete |
| Week 3 | CS write surface — identity gate, 6 write tools, atomic audit log, MCP prompts | ✅ Complete |
| Week 4 | Demo rehearsal (Story 1 + Story 2 verified live), presentation deck | 🔄 In progress |

**13 tools + 2 prompts, all verified end-to-end.** Both demo stories have been rehearsed live through Claude Desktop. Remaining: final presentation polish and delivery.

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
├── data/
│   ├── raw/                       # Kaggle CSV (git-ignored)
│   └── licensing.db               # Seeded SQLite DB (committed)
├── licensing_mcp/
│   ├── models.py                  # SQLAlchemy ORM — all 17 tables
│   ├── database.py                # Session factory + LICENSING_DB_PATH override
│   ├── identity.py                # CS actor resolution + permission checks
│   ├── cs_executor.py             # Write pipeline: gate → mutate → audit → commit
│   ├── elicitation.py             # Spec-compliant elicitation schema base
│   ├── prompts.py                 # MCP prompts (user-invocable)
│   ├── server_instance.py         # Singleton FastMCP app
│   ├── server.py                  # Tool registration + stdio entry point
│   ├── data_access/
│   │   ├── license_queries.py     # Read queries (→ microservice calls in prod)
│   │   ├── write_queries.py       # Mutations with before/after state capture
│   │   └── audit.py               # Audit writer + history reader
│   └── tools/                     # One file per MCP tool (13 total)
├── scripts/
│   └── seed.py                    # Hybrid seeder: AWS SaaS + Faker
├── slides/                        # Slidev presentation deck
├── project-proposal.md
├── security-considerations-mcp-access.md
├── presentation-and-questions-notes.md
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
