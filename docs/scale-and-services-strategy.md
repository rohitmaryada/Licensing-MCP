# Strategy — Scale, Real Data & Microservices (Draft v0.1)

> Status: DRAFT — for review. **DECIDED** = locked with Rohit; ❓ = open.
> Last updated: 2026-06-22

## 1. Why

The POC proves the architecture but doesn't *look* like the enterprise. Three
gaps to close before it can be demoed credibly to MathWorks stakeholders:

1. **Data footprint** — the seed DB is ~0.0001% of real scale and far shallower
   than the production hierarchy.
2. **Raw SQL in the tools** — `data_access/` runs SQLAlchemy directly; production
   tools must call enterprise services, not a database.
3. **Single flat DB** — production reads/writes go through a landscape of
   enterprise-grade microservices over a deep relational model.

## 2. The core move (DECIDED): introduce a service tier

All three gaps collapse into one architectural change — go from two layers to
three:

```
   AGENT / MCP tools            DOMAIN SERVICES                 CLOUD DATABASE
 ┌────────────────────┐      ┌────────────────────────┐      ┌──────────────────┐
 │ tool handlers       │─HTTP→│ Licensing service       │      │ deep hierarchy   │
 │ data_access =       │      │ Entitlement service     │─SQL→ │ entity→master→   │
 │   thin HTTP clients │      │ Activation service      │      │ license→product/ │
 │ (NO raw SQL)        │      │ (+ Compliance, later)   │      │ entitlement→     │
 └────────────────────┘      └────────────────────────┘      │ policy/activation│
        ▲ tool handlers &       owns all SQL; REST;            │ ~5–10M rows      │
          cs_executor           paginated; key-scoped;         └──────────────────┘
          UNCHANGED             read+write; service-auth
```

Consequences:
- Raw SQL leaves the MCP server entirely — it lives in the services (gap 2).
- The **DB engine becomes a hidden detail** behind the services — which is why
  Postgres is fine even though the enterprise runs SQL Server (gap 3).
- The pitch becomes: **"swap our stand-in services for your real microservices;
  the MCP doesn't change."** The endpoints mirror the
  `GET /licensing-service/v1/...` equivalents already in the `data_access`
  docstrings.

## 3. Locked decisions

| Decision | Choice | Rationale |
|---|---|---|
| Database | **Neon Postgres** | Serverless, generous free tier, scales to zero; the service layer hides the engine so SQL-Server fidelity isn't needed. |
| Scale | **Representative, ~5–10M rows** | Full depth + credible volume that stresses queries; literal 40M (→ billions of child rows) is neither feasible nor necessary. |
| Service shape | **Multiple domain services** | Looks like a real enterprise landscape; strongest "this mirrors prod" story. |
| Service→service auth | shaped like prod, simple for POC | Signed service token / client-credentials (security doc Boundary 2). |
| Dev runtime | local `docker-compose` for services + MCP, pointing at Neon cloud DB | No cloud needed for daily dev except the DB. ❓ optionally deploy services to a free host for a hosted demo. |

## 4. Target data model (the deep hierarchy)

Replaces the current flat model. Reflects the real structure Rohit described:

```
entity (customer, e.g. Boeing)
  └─ master_license                        umbrella per customer
       └─ license                          a customer can have 100s
            ├─ license_product             the sellable parts:
            │     {offering, seat_count}      offering + seats live here
            └─ entitlement                 what a user can install/use
                 │   (a suite license, e.g. CWS, yields up to ~8)
                 ├─ policy                 drives usage (named/concurrent,
                 │                           max activations, limits)
                 └─ activation             user × machine × heartbeat × status
```

New vs. POC: **master_license** tier, **offering + seat_count** on products,
**entitlement** as a first-class node, and the **entitlement → policy /
activation** chain. The demo scenario (Acme / L-99001 / jane.doe / MAC-OLD-7291)
is planted inside this model so Story 1 + Story 2 still run.

❓ Confirm: does an entitlement map to one product or a suite? Exact `policy`
attributes that drive usage?

## 5. Service landscape & tool mapping

Three services for the POC (Compliance added later per `compliance/PRD.md`):

| Service | Owns | Representative endpoints |
|---|---|---|
| **Licensing** | entity, master_license, license, license_product | `GET /master-licenses/{id}`, `GET /licenses?masterLicenseId=&page=`, `GET /licenses/{id}`, `GET /licenses/{id}/products`, `GET /entities/search?name=`, write: create/update-seats/extend/transfer-admin |
| **Entitlement** | entitlement, policy | `GET /entitlements?licenseId=`, `GET /entitlements/{id}`, `GET /users/{email}/entitlements`, `GET /entitlements/{id}/policies` |
| **Activation** | activation, installation | `GET /activations?userEmail=`, `POST /activations/{id}/revoke`, `POST /installations/{id}/reset` |
| **Audit** ❓ | audit log | shared service vs per-service — decide |

Every existing MCP tool maps onto these with **no change to its handler** — only
its `data_access` function body changes from SQLAlchemy to an HTTP call:

| MCP tool | Service call |
|---|---|
| `list_licenses_by_entity`, `get_license_status`, `get_license_products`, `get_license_administrators`, `search_entitlements` | Licensing |
| `check_user_entitlements` | Entitlement |
| `add_user_to_license`, `update_seat_count`, `extend_license_expiry`, `transfer_license_admin` | Licensing (write) |
| `revoke_activation`, `reset_installation_slot` | Activation (write) |
| `get_audit_history` | Audit |

Service rules (DECIDED): **key-scoped or bounded-search only** (never unbounded
scans — this is what keeps per-request work tiny at 10M rows), paginated,
read+write, service-auth on every call.

## 6. Scale plan

- **Deterministic bulk generator** (not ORM row-by-row) → Postgres `COPY` for
  fast load. Real reference data (product catalog; CSL/PRPA later) + synthetic
  subjects, with planted demo + test records.
- Rough proportions for ~10M rows (tune in Phase 1):
  | table | approx rows |
  |---|---|
  | entities | 20K |
  | master_licenses | 25K |
  | licenses | 750K |
  | license_products | 4M |
  | entitlements | 1.5M |
  | policies | 1.5M |
  | activations | 4M |
- **Storage check (❓ / risk):** Neon's free tier may not hold ~10M rows; budget
  for Neon's low-cost tier (Rohit OK to "pay a little") if needed.

## 7. Phased roadmap

| Phase | Delivers | Notes |
|---|---|---|
| **0 — Provision** | Neon project + DB; connection string in secrets (not git) | confirm storage tier |
| **1 — Schema + data** | deep-hierarchy schema; bulk generator; ~10M rows loaded incl. planted demo | "looks real" |
| **2 — Services** | Licensing / Entitlement / Activation (read first, then write); `docker-compose` to run the landscape; service-auth | "calls microservices" |
| **3 — Repoint MCP** | `data_access/` → `httpx` clients; raw SQL removed from MCP; tools + `cs_executor` unchanged | "no raw SQLAlchemy" |
| **4 — Verify at scale** | Story 1 + Story 2 through the new stack; latency measured; key-scoped tools confirmed cheap at 10M rows | "demo at scale" |
| **5 — Compliance (later)** | denied-party + hooks as services per `compliance/PRD.md` | the compliance thread |

## 8. Risks & gotchas

- **Cold-start latency:** Neon scales to zero; first query after idle can be
  seconds — warm the DB before a live demo, or disable auto-suspend during demos.
- **Neon free storage** may be too small for 10M rows → cheap paid tier.
- **Service orchestration:** multiple services = more to run — `docker-compose`
  keeps it one command (same pattern as the Keycloak setup).
- **Connection pooling** at scale → use Neon's pooled connection endpoint.
- **Secrets:** Neon connection string + service tokens via `.env`/secrets, never
  committed (same discipline as the Anthropic key and Keycloak).
- **Don't break the local story:** keep a local-DB option so dev doesn't always
  require the cloud.

## 9. Connections to existing work

- **Security doc:** this realizes the `data_access/` → microservice transition
  and Boundary 2 (service identity) it always described.
- **Compliance PRD:** the gate's hooks are just more services in this landscape.
- **Dependency resolver:** another service that plugs into the same tier.
- **Keycloak:** Boundary 1 (user auth) is unchanged; this adds Boundary 2.

## 10. Open questions

1. Entitlement ↔ product mapping (single vs suite) and `policy` attributes (§4).
2. Audit as its own service vs per-service (§5).
3. Neon storage tier for ~10M rows — free vs low-cost paid (§6).
4. Hosted demo: run services locally via compose, or deploy to a free host (§3).
5. Exact representative proportions (§6) — tune to the real ratios Rohit sees.

## 11. Next step

On approval: **Phase 0 + 1** — provision Neon, finalize the deep-hierarchy
schema, and build the bulk generator. Everything downstream (services, MCP
repoint) builds on that foundation.
