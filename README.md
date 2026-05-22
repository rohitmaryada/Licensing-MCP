# Licensing Intelligence MCP

A local proof-of-concept MCP (Model Context Protocol) server that exposes MathWorks licensing and entitlement data to AI agents as two distinct capability surfaces:

- **Read Surface** — customer-facing queries (license status, entitlements, seat counts)
- **CS Action Surface** — role-gated write tools for Customer Service workflows, with full audit logging

Built on Python + SQLAlchemy + SQLite, running over stdio for Claude Desktop.

---

## Project Status

| Week | Focus | Status |
|---|---|---|
| Week 1 | Data foundation — schema, models, seeded database | ✅ Complete |
| Week 2 | MCP server + read tools (6 tools) | 🔜 Next |
| Week 3 | CS write tools + audit layer | 🔜 Planned |
| Week 4 | Buffer, demo prep, presentation | 🔜 Planned |

---

## What Has Been Built (Week 1)

### Database Schema (SQLite, `data/licensing.db`)

Fourteen tables across four schema groups:

**Licensing & Entitlement**
- `entity_types` — enterprise, academic, individual, government
- `entities` — 500 companies/universities/individuals (99 seeded from real AWS SaaS data, 401 synthetic)
- `license_types` — enterprise, academic, individual, concurrent, trial
- `licenses` — ~812 license records linked to entities
- `products` — 20 MathWorks products (MATLAB, Simulink, toolboxes)
- `license_products` — which products are on each license, industry-matched
- `users` — ~3,900 end users with realistic domain emails
- `license_users` — who is on which license (60–95% seat utilization)
- `license_admins` — which users administer each license
- `entitlements` — denormalized user × license × product (~22,000 rows)
- `installations` — machine-level install records
- `activations` — active/stale activations; some >90 days old for demo realism

**CS Identity & Permissions**
- `cs_users` — 51 CS reps (26 L1 / 15 L2 / 10 L3) + named demo rep `rep.sarah@mathworks.com`
- `cs_roles` — CS-L1, CS-L2, CS-L3 role definitions
- `cs_permissions` — which roles can call which write tools
- `cs_role_members` — role assignments

**Audit Log**
- `cs_audit_log` — 2,000 pre-seeded audit records covering all write tool types

### Demo Scenario (pre-wired)

A deterministic scenario is seeded specifically for the CS Action Agent demo (Story 2):

- **Entity:** Acme Corp
- **License:** `L-99001` — 10-seat enterprise license for MATLAB + Simulink, active through 2026-12-31
- **Seat utilization:** 10/10 (at capacity)
- **Demo user:** `jane.doe@acmecorp.com` — entitled to Simulink, but has a stale activation on `MAC-OLD-7291` (last heartbeat 94 days ago, status = inactive)
- **Demo CS rep:** `rep.sarah@mathworks.com` — CS-L1 role

This is the exact scenario for: *"User can't activate Simulink on her new laptop → seats at capacity → find stale activation → revoke it → audit record written."*

### Key Documents

| File | Purpose |
|---|---|
| `project-proposal.md` | Full POC proposal — architecture, tool surface, demo script, success criteria |
| `security-considerations-mcp-access.md` | Production security posture — SSO/PingID integration, OAuth 2.1 architecture, threat model, POC vs. production gap |

---

## Setup

### Prerequisites

- Python 3.13 (`/opt/homebrew/bin/python3.13` on macOS with Homebrew)
- A Kaggle account with an API token at `~/.kaggle/` (for the raw dataset download)

### 1. Clone and create virtual environment

```bash
git clone https://github.com/<your-username>/licensing-mcp.git
cd licensing-mcp
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Download the raw dataset

The seed script uses the [Amazon AWS SaaS Sales dataset](https://www.kaggle.com/datasets/nnthanh101/aws-saas-sales) from Kaggle to seed realistic company names. Your Kaggle token must be in `~/.kaggle/kaggle.json` or exported as `KAGGLE_TOKEN`.

```bash
# Place your kaggle.json at ~/.kaggle/kaggle.json, then:
kaggle datasets download -d nnthanh101/aws-saas-sales -p data/raw --unzip
```

Or with a token env var:
```bash
KAGGLE_TOKEN=<your-token> kaggle datasets download -d nnthanh101/aws-saas-sales -p data/raw --unzip
```

### 3. Generate the database

```bash
python scripts/seed.py
```

This creates `data/licensing.db` (~5 MB). Expected output:
```
Creating database schema...
Seeding reference data...
Seeding entities (AWS SaaS + Faker)...  → 500 entities
Seeding licenses...                      → 812 licenses
Seeding users...                         → ~3,900 users
Seeding entitlements...                  → ~22,000 entitlements
Seeding demo scenario (Acme Corp)...
Seeding CS users...                      → 51 CS users
Seeding audit log (2,000 records)...
Done. Database at: data/licensing.db
```

### 4. Verify (optional)

```bash
python3 - <<'EOF'
import sqlite3
conn = sqlite3.connect("data/licensing.db")
for t in ["entities","licenses","users","entitlements","cs_users","cs_audit_log"]:
    n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"{t:<25} {n:>6} rows")
EOF
```

---

## Project Structure

```
licensing-mcp/
├── data/
│   ├── raw/                  # Downloaded Kaggle CSV (git-ignored)
│   └── licensing.db          # Generated SQLite database (git-ignored)
├── licensing_mcp/
│   ├── __init__.py
│   └── models.py             # SQLAlchemy ORM models (all 14 tables)
├── scripts/
│   └── seed.py               # Hybrid seeder: AWS SaaS + Faker
├── project-proposal.md       # Full POC proposal
├── security-considerations-mcp-access.md  # Production security reference
├── requirements.txt
└── README.md
```

---

## MCP Tool Surface (Planned — Week 2 & 3)

### Read Tools (open access)
| Tool | Description |
|---|---|
| `get_license_status` | License status, expiry, seat count, type |
| `check_user_entitlements` | Products a user is entitled to, with activation state |
| `list_licenses_by_entity` | All licenses for a company or institution |
| `get_license_products` | Product catalog on a license |
| `get_license_administrators` | Admin users who manage a license |
| `search_entitlements` | Filtered queries across the entitlement dataset |

### CS Write Tools (role-gated)
| Tool | Required Role | Description |
|---|---|---|
| `add_user_to_license` | CS-L1 | Add a user to a license |
| `revoke_activation` | CS-L1 | Deactivate a product activation (frees a seat) |
| `reset_installation_slot` | CS-L2 | Clear an installation record |
| `update_seat_count` | CS-L2 | Increase or decrease seat count |
| `extend_license_expiry` | CS-L3 | Extend a license's expiration date |
| `transfer_license_admin` | CS-L3 | Reassign license administration |
| `get_audit_history` | CS-L1+ | Retrieve audit trail for a license |

---

## Security Reference

See [`security-considerations-mcp-access.md`](./security-considerations-mcp-access.md) for the full production security posture, including:
- PingID / OAuth 2.1 integration architecture
- How to restrict installation to authorized personnel
- Full threat model (authentication, authorization, prompt injection, data exposure, compliance)
- POC vs. production gap table

---

## Contributing

This is an internal POC. If you're a collaborator:
1. Complete setup steps above
2. The database is **not** committed — run `python scripts/seed.py` after cloning
3. The raw Kaggle CSV is also **not** committed — download it first (Step 2 above)
4. All new code goes under `licensing_mcp/` (server) or `scripts/` (data tooling)
