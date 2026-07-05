# Deep-Hierarchy Schema — Design & ERD (T1)

> Delivers **T1** from [../TASKS.md](../TASKS.md): the deep-hierarchy data model
> that Data (generator) and Services both depend on.
> DDL: [schema.sql](schema.sql) · **v2**, validated on Postgres 16 (13 tables, 21 FKs, 45 indexes).
> Strategy: [../docs/scale-and-services-strategy.md](../docs/scale-and-services-strategy.md) §4–6.
> Last updated: 2026-07-05 · **v2 reconciled against the real MW specs — see §8.**

---

## 1. What this is (and what it replaces)

The POC's live model (`licensing_mcp/models.py`, SQLite) is **flat**: `entity →
license → {products, users, denormalized entitlements, activations}`. It works
for the demo but doesn't look like the enterprise.

This schema is the **deep hierarchy** the real MathWorks model has. It is a *new,
separate artifact* — `models.py` is deliberately left untouched so the current
SQLite demo keeps running until the Phase-3 MCP repoint. This DDL targets **Neon
Postgres** and is owned by the domain services; the MCP server never touches it.

```
entity  (customer — POC stand-in for MW Licensee → CDS account/contact)
  └─ master_license                     umbrella per customer          [NEW TIER]
       ├─ license                       a customer can have 100s
       │    ├─ license_product          the sellable offering + seats  [seats live here]
       │    │      (offering; may be a suite; license_id NULL = unallocated)
       │    └─ entitlement              LICENSE-scoped capability line  [NEW, first-class]
       │         │  (suite offering fans out to one per component)
       │         ├─ policy              1:1 — governs usage             [NEW]
       │         ├─ entitlement_person  who is ASSIGNED (MW join)       [NEW, v2]
       │         └─ activation          machine-level USE (× user × machine × heartbeat)
       └─ master_license_admin          administrators (MASTER scope)   [v2: was license-scoped]

app_user ──< license_end_user   >── license           (seat membership / "licensed end users")
app_user ──< entitlement_person >── entitlement        (assignment — who holds it)
app_user ──< activation         >── entitlement        (usage — where it runs)
product  ──< product_suite_component >── product        (suite → components; POC abstraction)
```

> **Assignment vs usage (the v2 correction):** MW separates *who holds an
> entitlement* (`EntitlementPerson`) from *where it runs* (activation). v1 folded
> both into activation; v2 restores the split. See §8.

---

## 2. Resolved open questions (the T1 decisions)

### Q1 — Entitlement scope: **license-scoped** ✅ (confirmed by the MW spec)
An `entitlement` is a grantable capability line **under a license**, derived from
a `license_product` offering. It is **not** user-owned. Confirmed by MW
`Entitlement.licenseId` + `masterLicenseId` (EntitlementWS). **v2 refinement:**
the user relationship splits into two MW-faithful joins — `entitlement_person`
(assignment: who holds it) and `activation` (usage: where it runs). v1 had only
the latter.

- **Why:** matches strategy §4 (entitlement sits under license, not user), and
  keeps seat/usage math on the license side. Suites fan out cleanly: one
  offering → one entitlement per component product.
- **Consequence:** `activation` carries `user_id` (who) + `machine_id` (where) +
  `entitlement_id` (what). Uniqueness = `(entitlement_id, user_id, machine_id)`.
- **Contrast with the flat POC**, where `entitlement` was a denormalized
  `user × license × product` row. That collapses here into
  `entitlement` (license side) + `activation` (user side).

### Q2 — Suite vs single product: **both, via a fan-out table** ✅
`product.is_suite` flags suite offerings; `product_suite_component` maps a suite
to its atomic products. A `license_product` whose product is a suite generates
one `entitlement` per component (the "CWS → ~8 entitlements" behaviour); an
atomic offering generates exactly one. The catalog holds both atomic parts and
suites in one `product` table — simplest thing that still models the fan-out.

### Q3 — Policy: **its own table, 1:1 with entitlement** ✅
`policy.entitlement_id` is `UNIQUE` → strictly one policy per entitlement (which
also matches the §6 proportions: entitlements ≈ policies). Kept as a separate
table (not inlined onto `entitlement`) because it's a distinct domain concept
owned by the **Entitlement service** and can evolve independently.

**Policy fields — chosen because each drives a real usage rule:**
| field | meaning | why it matters |
|---|---|---|
| `policy_type` | `named` \| `concurrent` | the two real licensing models |
| `max_activations` | per-user (named) or total (concurrent) | seat/usage enforcement |
| `activation_ttl_days` | heartbeat staleness window | **powers stale-activation detection** — the Story 2 demo |
| `allow_offline` | offline use permitted | realistic policy knob |
| `reactivation_limit` | install-reset budget | backs `reset_installation_slot` |

### Deferred (not in this DDL)
- **CS identity + audit** (`cs_*`, `cs_audit_log`) stay MCP-side / a future Audit
  service — out of this cut per TASKS "Out of this cut".
- **Audit as its own service vs per-service** — still open (strategy §5).

---

## 3. Modeling conventions & the rationale (teaching notes)

- **BIGINT surrogate PKs everywhere.** Child tables run to millions of rows; a
  compact integer FK is smaller in every index and far faster to bulk-`COPY`
  than a text key. The flat POC used `L-XXXXX` text as the license PK — fine at
  800 rows, wasteful at scale.
- **Human refs kept as `UNIQUE TEXT`** (`license_ref = 'L-99001'`,
  `master_license_ref = 'ML-99000'`). External callers and the demo look up by
  these; internal joins use the surrogate. Best of both.
- **Native `ENUM` types** for closed sets (statuses, `entitlement_type`,
  `activation_type`). Values mirror the MW enums. Postgres enums are stored as
  4-byte OIDs — cheap — and reject bad values at write time.
- **`app_user`, not `user`** — `user` is a reserved word in Postgres.
- **Every FK access path is indexed.** This is the single most important rule for
  the §5 "key-scoped / bounded lookups only" contract: at 10M rows a service
  endpoint must hit an index, never scan. `ix_activation_user_status` is a
  composite tuned for the `check_user_entitlements` path (filter a user's
  activations by status without touching the heap for the common case).
- **Declaration order = dependency order.** Postgres needs a referenced table to
  exist when an FK is declared (it does *not* defer that to COMMIT — only
  *DEFERRABLE constraint checks* are deferred). So `app_user` is declared before
  `activation`, etc. This bit us once in draft; the file is now ordered correctly.

---

## 4. Representative scale (starting point — tune in A2)

Strategy §6's proportions were rough placeholders and were internally
inconsistent with suite fan-out (they had fewer entitlements than offerings).
With license-scoped entitlements fanning out from suites, entitlements should
**exceed** offerings on suite lines. Proposed starting point (~13M rows):

| table | approx rows | note |
|---|---|---|
| entity | 15K | customers |
| app_user | 1.5M | end users across all entities |
| master_license | 20K | ~1.3 per entity |
| license | 300K | ~15 per master license |
| license_product | 1.2M | ~4 offerings per license |
| entitlement | 2.5M | fan-out: atomic=1, suites×~8 |
| policy | 2.5M | 1:1 with entitlement |
| entitlement_person | 4M | ~1.6 assignees per entitlement |
| activation | 3M | ~1.2 per entitlement |
| license_end_user | 4M | seat memberships |
| master_license_admin | 25K | ~1.3 per master license |

These are the generator's (A2) inputs to tune against real MathWorks ratios; the
schema itself is independent of the exact counts.

---

## 5. Demo scenario mapping (Story 1 + Story 2 must still run)

The Acme / L-99001 / jane.doe / MAC-OLD-7291 scenario plants cleanly:

| element | row |
|---|---|
| Acme Corp | `entity` |
| Acme umbrella | `master_license` ML-99000 |
| The license | `license` L-99001, status active |
| Simulink offering, 10 seats | `license_product` (seat_count=10), 10 `license_end_user` rows → **at capacity** |
| Simulink capability | `entitlement` under L-99001 (`activation_type = standalone_named_user`) |
| jane.doe **assigned** to it | `entitlement_person` (user=jane, role=user) — she *holds* the entitlement |
| Usage rule | `policy` (`activation_ttl_days`=30) |
| jane.doe's stale **activation** | `activation` on that entitlement, machine MAC-OLD-7291, `last_heartbeat` 94 days ago, status inactive → **94 > 30 = stale** |

Note the v2 split in action: jane is *assigned* (`entitlement_person`) yet her
*usage* (`activation`) has gone stale — the exact CS situation Story 2 diagnoses.

The stale-activation logic that was hard-coded in the POC now falls out of data:
`now() - last_heartbeat > policy.activation_ttl_days`. That's the point of giving
policy a real home — the rule becomes queryable, not magic. (This gets planted by
**A3**.)

---

## 6. How to apply / verify

```bash
# throwaway Postgres to validate the DDL (no Neon needed):
docker run -d --rm --name ddltest -e POSTGRES_PASSWORD=x -e POSTGRES_DB=lic postgres:16-alpine
docker cp db/schema.sql ddltest:/schema.sql
docker exec ddltest psql -U postgres -d lic -v ON_ERROR_STOP=1 -f /schema.sql
docker stop ddltest
```
Against Neon (once T0 provisions it): `psql "$NEON_URL" -f db/schema.sql`.

---

## 7. What this unblocks

- **A1** — this *is* the DDL; migrations wrap it.
- **A2** — the generator writes to exactly these tables/proportions via `COPY`.
- **T2 / B*** — service DTOs are shaped by these tables; the Licensing /
  Entitlement / Activation service boundaries fall on the tier lines above.
- **C1** — `data_access/` HTTP clients return these shapes.

---

## 8. MW-fidelity mapping (verified against the real service specs)

Cross-checked against two real MW service specs: **MasterLicenseWS** (REST,
`GET /v1/master-licenses/{id}`) and **EntitlementWS** (GraphQL `getEntitlements`).
Verdict: **the hierarchy spine is confirmed; v2 closed the five load-bearing gaps.**

### Confirmed by the spec (no change needed)
| Our schema | MW evidence |
|---|---|
| `master_license → license → license_product` | "Products belong to licenses… nested under `licenses[].licensedProducts[]`. Matches masterlicensewstypes model." |
| `license_product.seat_count` | `LicensedProduct.quantity` ("Seat quantity") |
| entitlement **license-scoped** | `Entitlement.licenseId` + `masterLicenseId`; `entitlementType: LICENSE` — anchored to license, not user |
| `policy` **1:1** with entitlement | `entitlementPolicy: EntitlementPolicy` — a single object per entitlement |

### Fixed in v2 (the critical set)
| Gap in v1 | MW reality | v2 change |
|---|---|---|
| No assignment join | `EntitlementPerson` (`entitlementId`, `webProfileId`, `role`) | added **`entitlement_person`** |
| Admins license-scoped | `administrators[]` sits on **MasterLicense** | added **`master_license_admin`** (dropped `license_admin`) |
| Master reachable only via join | `masterLicenseId` denormalized on LicensedProduct + Entitlement | added `master_license_id` to `license_product` + `entitlement` |
| `license_id` NOT NULL | `unallocatedProducts` = LicensedProduct with `licenseId = null` at master level | made `license_product.license_id` **nullable** |
| Only `LICENSE`, 3 statuses, `named/concurrent` | `entitlementType`; 6-value status; rich `activationType` | added `entitlement_type`, `activation_type`; widened `entitlement_status` |

### Divergences we keep on purpose (documented, not fixed)
| MW shape | Ours | Why the shortcut is OK |
|---|---|---|
| `EntitlementPolicy` = `policyName` + generic `policyRuleValue[]` (ruleName/ruleValue bag) | fixed columns (`activation_ttl_days`, `max_activations`, …) + `policy_name`, `quantity` | the specific rules that drive the POC read cleaner as columns; the bag is easy to add later if a service needs arbitrary rules |
| `product_suite_component` (our table) | — | **our invention** — MW resolves suites via `businessOfferingId`/configurator, not an explicit table; kept as a POC abstraction for fan-out |
| Customer identity in **CDS**, referenced by `Licensee.entityId`/`entityType` | local `entity` table | this *is* the "data_access replaces an external service" story — CDS becomes a service call in prod |
| Bare integer ids | `L-`/`ML-` text refs (+ BIGINT PKs) | POC lookup convenience; internal joins already use the surrogate |

### Deliberate scope cuts (out of this DDL)
Temporal/renewal detail (`currentServiceStartDate/EndDate`, `serviceDates[]`,
`renewalOptions[]`, `release`), `activationKeys[]`/FIK, and **TSUR** trial
entitlements. None are needed for Story 1/2 or the 3-service split; the
`entitlement_type` column reserves room for TSUR without generating it.

### Note on `activation`
The machine-level `activation` table (user × machine × heartbeat) is **not** in
either spec read — it belongs to the activation / LicenseUse service. It's our
faithful stand-in for that domain and stays as designed.
