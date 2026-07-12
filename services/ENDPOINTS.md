# Endpoints Spec — as-built

Every endpoint the three services expose today — reads and writes together,
in one place. This reflects the **code**, not the draft contract — see
[Gaps vs. the draft contract](#gaps-vs-the-draft-contract) at the bottom for
where this diverges from [CONTRACTS.md](CONTRACTS.md).

**Source of truth:** `services/{licensing,entitlement,activation}/`,
`services/shared/{dto,schemas,errors}.py`.
**Companions:** [CONTRACTS.md](CONTRACTS.md) (the T2 draft this was built
from) · [B1-SETUP.html](B1-SETUP.html) (scaffolding). The build plans
(`B2-READS-PLAN.md`, `B2-WRITES-PLAN.md`) live in the project vault, not this
repo.

---

## Architecture

```
AI agent → MCP tools (cs_executor: role gate + audit) ⇢ (C1, not wired yet)
                                                        ↓
        Licensing :8001  ·  Entitlement :8002  ·  Activation :8003
                                                        ↓
                                              Postgres :5433
```

The MCP → services hop isn't wired yet (that's **C1**) — the live MCP still
talks to SQLite directly. These endpoints are C1's target.

---

## Conventions (all endpoints)

### Auth headers

Every non-health route requires these (checked by `require_service_auth` — a
**presence check only** right now; real JWT verification is **B5**, not built):

| Header | Required | Meaning |
|---|---|---|
| `mathworks-access-key` | yes | Calling service's JWT access key |
| `X-MW-WS-Caller-Id` | yes | Which service is calling (e.g. `LICENSING-MCP`) |
| `mathworks-requestid` | yes | Trace id, propagated across services |
| `X-MW-WS-Security-Token` | optional | Pass-through user token, stashed on `request.state.user_token` |

### Pagination envelope — `Page<T>`

List endpoints take `page` (0-based, default `0`) and `size` (default `100`,
hard max `100` → `400` above that):

```json
{
  "items": [ /* T[] */ ],
  "pageInfo": {
    "currentPage": 0,
    "pageSize": 100,
    "totalPages": 3,
    "totalElements": 214,
    "hasNextPage": true
  }
}
```

### Write envelope — `Change<T>`

State-transition writes (PATCH; the two Activation actions) return the row
before and after the mutation in one response:

```json
{ "before": { /* T */ }, "after": { /* T */ } }
```

Creates/deletes don't use it — they return the created resource, or `204`.

### Error envelope

```json
{ "detail": "license 5001 not found", "detailType": "NOT_FOUND", "detailMessages": [] }
```

| HTTP | `detailType` | When |
|---|---|---|
| 400 | `BAD_REQUEST` | bad params, `size>100`, negative seat count, past expiry date, missing required filter |
| 401 | `UNAUTHORIZED` | missing service-auth header |
| 404 | `NOT_FOUND` | id/email not found; admin relationship doesn't exist |
| 409 | `CONFLICT` | write violates a business rule (capacity, status, duplicate, limit exhausted) |
| 500 | `INTERNAL_ERROR` | unhandled — caught by the catch-all, logged, generic body |

### Ids & casing

Path params are the **integer surrogate id** (or email, for user routes). Wire
JSON is **camelCase** (Pydantic `alias_generator=to_camel`); DB columns are
snake_case and map 1:1 into DTOs. Human refs (`licenseRef`, `masterLicenseRef`)
appear only on License/MasterLicense DTOs.

---

## Licensing service — `/licensing/v1` · :8001

Owns `entity`, `master_license`, `license`, `license_product`,
`master_license_admin`, `license_end_user`, `product`.

### Reads

#### `GET /licensees/{entity_id}`
One customer (licensee).

**Returns** `Licensee`
```json
{
  "id": 1, "name": "Acme Energy 1", "entityType": "enterprise",
  "industry": "Energy", "country": "US", "region": "AMER",
  "externalRef": "EXT-0001", "createdAt": "2024-01-15T00:00:00Z"
}
```
**404** licensee not found.

---

#### `GET /licensees/{entity_id}/licenses`
All licenses a customer holds, grouped by their owning master license.
Paginated at the license level, grouped in the router afterward.

**Returns** `LicensesByEntityResponse`
```json
{
  "licenseeId": 1,
  "licenseeName": "Acme Energy 1",
  "masterLicenses": [
    {
      "id": 1, "masterLicenseRef": "ML-0000001", "label": "Acme Master",
      "licenses": [
        { "id": 1, "licenseRef": "L-0000001", "status": "active",
          "expiryDate": "2027-02-28", "daysUntilExpiry": 231, "productCount": 2 }
      ]
    }
  ],
  "totalLicenses": 1
}
```
**404** licensee not found.

---

#### `GET /master-licenses/{ml_id}?include=`
Umbrella header, with optional sub-objects expanded on demand.

**Query** `include=` comma-separated: `licenses`, `administrators`, `licensee`, `unallocatedProducts`

**Returns** `MasterLicense`
```json
{
  "id": 1, "masterLicenseRef": "ML-0000001", "label": "Acme Master",
  "entityId": 1, "program": "Campus", "sponsor": "IT Dept",
  "createdAt": "2024-01-15T00:00:00Z",
  "licenses": null,
  "administrators": null,
  "licensee": null,
  "unallocatedProducts": null
}
```
(sub-objects populate only if requested via `include=`; `unallocatedProducts`
= `license_product` rows with `license_id IS NULL`)

**404** master license not found.

---

#### `GET /master-licenses/{ml_id}/licenses`
Licenses under one umbrella, paginated.

**Returns** `Page<LicenseSummary>` — items shaped like:
```json
{ "id": 1, "licenseRef": "L-0000001", "status": "active",
  "expiryDate": "2027-02-28", "daysUntilExpiry": 231, "productCount": 2 }
```

---

#### `GET /master-licenses/{ml_id}/administrators`
Admins on a master license (admins are master-scoped, per MW).

**Returns** `[Administrator]`
```json
[
  { "id": 125, "masterLicenseId": 1, "userId": 1,
    "userEmail": "ivan.volkov1@acmeenergy11.example",
    "renewalNotifications": true, "addedDate": "2026-07-12" }
]
```

---

#### `GET /licenses/{license_id}/administrators`
Convenience: resolves `license → master_license_id → admins` server-side.

**Returns** `[Administrator]` (same shape as above)
**404** license not found.

---

#### `GET /licenses/{license_id}`
The full license snapshot — master + licensee + products + end-user count,
assembled in one response.

**Returns** `License`
```json
{
  "id": 1, "licenseRef": "L-0000001", "status": "active",
  "expiryDate": "2027-02-28", "daysUntilExpiry": 231, "productCount": 2,
  "startDate": "2025-01-01",
  "master": { "id": 1, "masterLicenseRef": "ML-0000001", "label": "Acme Master" },
  "licensee": { "id": 1, "name": "Acme Energy 1", "entityType": "enterprise" },
  "products": [
    { "licenseProductId": 1, "productCode": "DLT", "productName": "Deep Learning Toolbox",
      "isSuite": false, "seatCount": 10, "seatsActive": 6,
      "businessOfferingId": 4001, "entitlementCount": 1 }
  ],
  "endUserCount": 6
}
```
**404** license not found.

---

#### `GET /licenses/{license_id}/products`
A license's products, paginated.

**Returns** `Page<LicensedProduct>` — items shaped like:
```json
{ "licenseProductId": 2, "productCode": "HDL", "productName": "HDL Coder",
  "isSuite": false, "seatCount": 999, "seatsActive": 6,
  "businessOfferingId": 4013, "entitlementCount": 1 }
```
> **Known simplification:** `seatsActive` is computed from `license_end_user`,
> which is *license*-scoped (no per-product seat-usage table exists) — the
> same value repeats across every product row of a license.

---

### Writes

#### `PATCH /license-products/{id}` — backs `update_seat_count`
**Body**
```json
{ "seatCount": 12 }
```
**Rules** 400 if `seatCount < 0` · 404 if not found · 409 if `seatCount` is
below the active `license_end_user` count on that product's license

**Returns** `Change<LicensedProduct>`
```json
{
  "before": { "licenseProductId": 2, "productCode": "HDL", "productName": "HDL Coder",
    "isSuite": false, "seatCount": 1, "seatsActive": 6, "businessOfferingId": 4013, "entitlementCount": 1 },
  "after":  { "licenseProductId": 2, "productCode": "HDL", "productName": "HDL Coder",
    "isSuite": false, "seatCount": 999, "seatsActive": 6, "businessOfferingId": 4013, "entitlementCount": 1 }
}
```

---

#### `PATCH /licenses/{id}` — backs `extend_license_expiry`
**Body**
```json
{ "expiryDate": "2027-02-28" }
```
**Rules** 404 if not found · 400 if `expiryDate` is before today. If the
license was `expired`, it flips back to `active` automatically.

**Returns** `Change<LicenseSummary>` *(lighter than the full `License`
composite — a deliberate deviation from the draft contract; a PATCH response
doesn't need the embedded master/licensee/products)*
```json
{
  "before": { "id": 1, "licenseRef": "L-0000001", "status": "active",
    "expiryDate": "2026-04-06", "daysUntilExpiry": -97, "productCount": 2 },
  "after":  { "id": 1, "licenseRef": "L-0000001", "status": "active",
    "expiryDate": "2027-02-28", "daysUntilExpiry": 231, "productCount": 2 }
}
```

---

#### `POST /licenses/{id}/end-users` — backs `add_user_to_license`
**Body**
```json
{ "userEmail": "ivan.volkov1@acmeenergy11.example" }
```
**Rules** 404 license/user not found · 409 if license isn't `active`/`trial` ·
409 if user is already an active end-user · 409 if license is at capacity
(active end-users ≥ sum of that license's product seat counts)

**Returns** `EndUser`
```json
{ "id": 12455, "licenseId": 1, "userId": 1,
  "userEmail": "ivan.volkov1@acmeenergy11.example",
  "addedDate": "2026-07-12", "status": "active" }
```
> **Side effect, same transaction:** also inserts one `entitlement_person` row
> per entitlement on the license, so the user shows up immediately in
> `check_user_entitlements`. Deliberate ownership exception — a real
> cross-service saga isn't worth it for this POC.

---

#### `POST /master-licenses/{id}/administrators` — backs `transfer_license_admin` (add side)
**Body**
```json
{ "userEmail": "ivan.volkov1@acmeenergy11.example", "renewalNotifications": true }
```
**Rules** 404 master license/user not found · 409 if already an administrator

**Returns** `Administrator`
```json
{ "id": 125, "masterLicenseId": 1, "userId": 1,
  "userEmail": "ivan.volkov1@acmeenergy11.example",
  "renewalNotifications": true, "addedDate": "2026-07-12" }
```

---

#### `DELETE /master-licenses/{id}/administrators/{userId}` — backs `transfer_license_admin` (remove side)
**Rules** 404 if that user isn't currently an administrator

**Returns** `204 No Content`

> W4 + W5 are the two primitives the MCP tool `transfer_license_admin`
> orchestrates in C1 (add new, then remove old) — there's no single
> "transfer" call.

---

## Entitlement service — `/entitlement/v1` · :8002

Owns `entitlement`, `policy`, `entitlement_person`, `product`. Resolves users
via `entitlement_person`; makes the one sanctioned cross-service call (→
Activation). **No write endpoints this slice** — see gaps below.

### Reads

#### `GET /entitlements/{entitlement_id}?include=`
One entitlement, with optional sub-objects expanded on demand.

**Query** `include=` comma-separated: `policy`, `people`

**Returns** `Entitlement`
```json
{
  "id": 5, "licenseId": 3, "licenseRef": "L-0000003",
  "masterLicenseId": 1, "masterLicenseRef": "ML-0000001",
  "licenseProductId": 4, "productCode": "SL", "productName": "Simulink",
  "entitlementType": "license", "activationType": "designated_computer", "status": "active",
  "assignmentRole": null, "assignedDate": null,
  "policy": { "id": 5, "entitlementId": 5, "policyName": "Named User", "quantity": 25,
    "maxActivations": 25, "activationTtlDays": 45, "allowOffline": false, "reactivationLimit": 1 },
  "staleActivations": [],
  "people": [
    { "id": 7, "entitlementId": 5, "userId": 35,
      "userEmail": "sara.novak35@acmeenergy11.example",
      "role": "manager", "addedDate": "2024-06-11", "status": "active" }
  ]
}
```
`assignmentRole`/`assignedDate` are per-user fields (they come from a specific
`entitlement_person` row) — they don't apply to a single-entitlement fetch
that isn't scoped to one user, so they're always `null` here. `staleActivations`
is always `[]` on this route (no per-user TTL context to scope it by).
**404** entitlement not found.

---

#### `GET /entitlements/{entitlement_id}/policy`
The entitlement's 1:1 usage policy, standalone.

**Returns** `Policy`
```json
{ "id": 5, "entitlementId": 5, "policyName": "Named User", "quantity": 25,
  "maxActivations": 25, "activationTtlDays": 45, "allowOffline": false, "reactivationLimit": 1 }
```
**404** entitlement not found, or no policy row exists for it.

---

#### `GET /entitlements/{entitlement_id}/people?page=&size=`
Who's assigned to this entitlement (`entitlement_person`), paginated.

**Returns** `Page<EntitlementPerson>` — items shaped like:
```json
{ "id": 7, "entitlementId": 5, "userId": 35,
  "userEmail": "sara.novak35@acmeenergy11.example",
  "role": "manager", "addedDate": "2024-06-11", "status": "active" }
```
**404** entitlement not found.

---

#### `GET /users/{email}/entitlements?status=&includeStaleActivations=&page=&size=`
Everything a user is entitled to, resolved through `entitlement_person` —
enriched with each entitlement's policy and, optionally, its stale
activations.

**Query** `status` (filter) · `includeStaleActivations` (bool, default
`false`) · `page`/`size`

**Returns** `UserEntitlementsResponse`
```json
{
  "user": { "id": 1, "email": "ivan.volkov1@acmeenergy11.example",
    "firstName": "Ivan", "lastName": "Volkov", "entityId": 1, "entityName": "Acme Energy 1" },
  "items": [
    { "id": 5, "licenseId": 1, "licenseRef": "L-0000001",
      "masterLicenseId": 1, "masterLicenseRef": "ML-0000001",
      "licenseProductId": 1, "productCode": "DLT", "productName": "Deep Learning Toolbox",
      "entitlementType": "license", "activationType": "standalone_named_user", "status": "active",
      "assignmentRole": null, "assignedDate": "2026-07-12",
      "policy": { "id": 3, "entitlementId": 5, "policyName": "Named User",
        "quantity": 1, "maxActivations": 1, "activationTtlDays": 30,
        "allowOffline": false, "reactivationLimit": 1 },
      "staleActivations": [],
      "people": null }
  ],
  "pageInfo": { "currentPage": 0, "pageSize": 100, "totalPages": 1, "totalElements": 1, "hasNextPage": false }
}
```
**Cross-service:** when `includeStaleActivations=true`, calls Activation per
entitlement using that policy's `activationTtlDays` as the staleness window.
**404** user not found.

> This is the **Story-2** entry point — it surfaces stale activations past
> their policy TTL in one enriched call.

---

#### `GET /entitlements?licenseId=&masterLicenseId=&licenseProductId=&status=&page=&size=`
Filtered entitlement search. **At least one filter is required** — an
unfiltered scan is rejected.

**Returns** `Page<EntitlementSummary>` — items shaped like:
```json
{ "id": 5, "licenseId": 1, "licenseRef": "L-0000001",
  "masterLicenseId": 1, "masterLicenseRef": "ML-0000001",
  "licenseProductId": 1, "productCode": "DLT", "productName": "Deep Learning Toolbox",
  "entitlementType": "license", "activationType": "standalone_named_user", "status": "active" }
```
**400** no filter supplied.

---

## Activation service — `/activation/v1` · :8003

Owns `activation`. Reads are **public and general-purpose** — the list
endpoint doubles as the internal call Entitlement's E1 makes
(`entitlementId`+`staleDays`) and a general filterable list any caller can use.

### Reads

#### `GET /activations?entitlementId=&userEmail=&status=&staleDays=&page=&size=`
Filtered list of activations. **At least one of `entitlementId` or
`userEmail` is required** — `status`/`staleDays` alone would be an unindexed
full scan (only `entitlement_id` and `user_id` are indexed on this table).
`staleDays=N` filters to `now() - last_heartbeat > N days` when supplied.

**Returns** `Page<StaleActivation>` — items shaped like:
```json
{ "id": 6, "entitlementId": 5, "userId": 70,
  "userEmail": "lena.novak70@acmeenergy11.example",
  "machineId": "MW-0000000006", "machineName": "SRV-6", "os": "macOS 15",
  "activationDate": "2026-05-09", "lastHeartbeat": "2026-07-12T18:15:58Z",
  "daysSinceHeartbeat": 0, "status": "active" }
```
`daysSinceHeartbeat` is always computed in SQL (`now()`, not Python — no
app/DB clock skew) regardless of whether `staleDays` is supplied; it's purely
informational when it isn't.

**400** neither `entitlementId` nor `userEmail` supplied.

---

#### `GET /activations/{activation_id}`
One activation, by id.

**Returns** `ActivationState`
```json
{ "id": 6, "entitlementId": 5, "userId": 70,
  "userEmail": "lena.novak70@acmeenergy11.example",
  "machineId": "MW-0000000006", "machineName": "SRV-6", "os": "macOS 15",
  "activationDate": "2026-05-09", "lastHeartbeat": "2026-07-12T18:15:58Z",
  "status": "active" }
```
**404** activation not found.

---

### Writes

#### `POST /activations/{id}/revoke` — backs `revoke_activation`
**Body** `{ "reason": "..." }` — accepted, **not persisted** (audit is MCP-side)

**Rules** 404 if not found. **Effect** `status → 'inactive'` — frees the seat
(the Story-2 op).

**Returns** `Change<ActivationState>`
```json
{
  "before": { "id": 6, "entitlementId": 5, "userId": 70,
    "userEmail": "lena.novak70@acmeenergy11.example",
    "machineId": "MW-0000000006", "machineName": "SRV-6", "os": "macOS 15",
    "activationDate": "2026-05-09", "lastHeartbeat": "2026-06-29T00:00:00Z", "status": "active" },
  "after": { "...same fields...", "status": "inactive" }
}
```

---

#### `POST /activations/{id}/reset` — backs `reset_installation_slot`
**Body** `{ "reason": "..." }` — accepted, not persisted

**Rules** 404 if not found · 409 if the entitlement's
`policy.reactivationLimit <= 0`. **Effect** `status → 'active'`,
`lastHeartbeat → now()` — re-arms the slot ("machine died, let them back on"),
gated by the reactivation budget.

**Returns** `Change<ActivationState>` (same shape as revoke, `status`
`inactive → active`, `lastHeartbeat` bumped to now)

> Revoke and reset are given genuinely different meanings on the same
> `activation` row — Postgres has no separate `installation` table.

---

## Health endpoints (all three services, unauthenticated)

| Path | Purpose |
|---|---|
| `GET /health/live` | process is up → `{"status":"ok"}` |
| `GET /health/ready` | DB reachable → `200`, else `503 {"status":"unready"}` |
| `GET /_demo` | auth'd smoke test — one row from the owned table (drop before prod) |

---

## MCP tool → endpoint map (the C1 target)

| MCP tool | Service call | Kind | Required role (MCP-side) |
|---|---|---|---|
| `list_licenses_by_entity` | `GET /licensing/v1/licensees/{id}/licenses` | read | — |
| `get_license_status` | `GET /licensing/v1/licenses/{id}` | read | — |
| `get_license_products` | `GET /licensing/v1/licenses/{id}/products` | read | — |
| `get_license_administrators` | `GET /licensing/v1/licenses/{id}/administrators` | read | — |
| `check_user_entitlements` | `GET /entitlement/v1/users/{email}/entitlements?includeStaleActivations=true` | read | — |
| `search_entitlements` | *no service endpoint yet* — see gaps | read | — |
| `update_seat_count` | `PATCH /licensing/v1/license-products/{id}` | write | CS-L2 |
| `extend_license_expiry` | `PATCH /licensing/v1/licenses/{id}` | write | CS-L3 |
| `add_user_to_license` | `POST /licensing/v1/licenses/{id}/end-users` | write | CS-L1 |
| `transfer_license_admin` | `POST` + `DELETE /licensing/v1/master-licenses/{id}/administrators` | write | CS-L3 |
| `revoke_activation` | `POST /activation/v1/activations/{id}/revoke` | write | CS-L1 |
| `reset_installation_slot` | `POST /activation/v1/activations/{id}/reset` | write | CS-L2 |
| `get_audit_history` | Audit service — deferred | — | — |

Role gating and audit-writing happen entirely MCP-side in
`cs_executor.execute_cs_write()` — none of it lives in these services. C1 is
purely: point each tool's HTTP call at the row above instead of at SQLite.

---

## Gaps vs. the draft contract

[CONTRACTS.md](CONTRACTS.md) is the draft this was built from; a few things
in it aren't built yet:

| Not built | Contract said | Notes |
|---|---|---|
| `GET /entities/search?name=` | backs `search_entitlements` | Parked — needs an indexing decision (trigram vs. denormalized search table); only `entity.name` has an index today |
| `GET /entities/{id}/master-licenses` (flat `Page<MasterLicenseSummary>`) | — | As-built takes a different shape: `/licensees/{id}/licenses`, grouped by master license |
| `GET /licenses/{id}/end-users` | seat membership list | Not exposed as its own endpoint — only a count (`endUserCount`) is embedded in `License` |
| Any Entitlement-service write | — | Parked per CONTRACTS §8 — no MCP tool needs one yet |
| Audit service (`get_audit_history`) | — | Entirely deferred, own open question (strategy §5) |
| Real service-to-service auth (B5) | headers "validated by a shared middleware (B5)" | `require_service_auth` is a presence-only stub today |

**Closed since the writes slice:** `GET /entitlements/{id}` (+`include=policy,people`),
`GET /entitlements/{id}/policy`, `GET /entitlements/{id}/people`,
`GET /activations/{id}`, and the public general-purpose `GET /activations`
filter (now one endpoint serving both the general case and E1's internal call)
are all built — see the Entitlement and Activation sections above.
