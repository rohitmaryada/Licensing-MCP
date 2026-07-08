# Service API Contracts (T2)

> Delivers **T2** from [../TASKS.md](../TASKS.md): the contracts the **Services**
> workstream (B1–B4, P2) implements and the **MCP repoint** (C1) codes against —
> C1 can start on mocks of these *before* the real services exist.
>
> Grounded in [../db/schema.sql](../db/schema.sql) (the tables each service owns)
> and the two real MW service specs (MasterLicenseWS REST, EntitlementWS GraphQL) —
> auth headers, pagination, and error shapes mirror MW so this reads like prod.
>
> Status: DRAFT v1 for review. Format is readable-markdown; formalize to OpenAPI in
> B1 if wanted. Last updated: 2026-07-06.

---

## 1. Three services, clean ownership

| Service | Base path | Owns (tables) | MCP tools it backs |
|---|---|---|---|
| **Licensing** | `/licensing/v1` | `entity`, `master_license`, `license`, `license_product`, `master_license_admin`, `license_end_user` | `list_licenses_by_entity`, `get_license_status`, `get_license_products`, `get_license_administrators`, `search_entitlements`, `add_user_to_license`, `update_seat_count`, `extend_license_expiry`, `transfer_license_admin` |
| **Entitlement** | `/entitlement/v1` | `entitlement`, `policy`, `entitlement_person`, `product` | `check_user_entitlements` |
| **Activation** | `/activation/v1` | `activation` | `revoke_activation`, `reset_installation_slot` |

`get_audit_history` → **Audit** service, deferred (strategy §5 open question).

**The golden rule (DECIDED):** every endpoint is **key-scoped or bounded-search
only** — a lookup by id/email, or a filtered+paginated list. Never an unbounded
scan. This is what keeps per-request work an index seek at 1.5M+ rows.

---

## 2. Conventions (all services)

### Auth headers (Boundary 2 — service identity; mirrors MW)
| Header | Required | Meaning |
|---|---|---|
| `mathworks-access-key` | yes | Service JWT access key (the calling service's identity). |
| `X-MW-WS-Caller-Id` | yes | Which service is calling (e.g. `LICENSING-MCP`). |
| `mathworks-requestid` | yes | Trace id, propagated across services. |
| `X-MW-WS-Security-Token` | optional | Pass-through user/MWA token (Boundary 1) when present. |

In the POC these are validated by a shared middleware (B5). Boundary 1 (who the
*user* is) stays at the MCP/Keycloak layer and is unchanged.

### Pagination (mirrors EntitlementWS)
List endpoints take `page` (0-based, default `0`) and `size` (default `100`, **hard
max 100**). Responses are wrapped:

```json
{
  "items": [ ... ],
  "pageInfo": {
    "currentPage": 0, "pageSize": 100, "totalPages": 3,
    "totalElements": 214, "hasNextPage": true
  }
}
```

### Errors (mirrors MasterLicenseWS)
```json
{ "detail": "License not found for id: 5001", "detailType": "NOT_FOUND", "detailMessages": [] }
```
| HTTP | `detailType` | When |
|---|---|---|
| 400 | `BAD_REQUEST` | bad/missing params |
| 401 | `UNAUTHORIZED` | missing/invalid access key |
| 403 | `FORBIDDEN` | caller not permitted for this resource |
| 404 | `NOT_FOUND` | id not found |
| 409 | `CONFLICT` | write violates a rule (e.g. seats below current usage) |
| 500 | `INTERNAL_ERROR` | unexpected |

### Ids
Endpoints accept the **integer surrogate id** by default. Human refs
(`L-0012345`, `ML-0000123`) are accepted where noted via a `ref` lookup. Fields
carry both where the schema has them.

### Writes
Write endpoints **perform the mutation and return `{ before, after }`** state so
the MCP-side `cs_executor` can gate → mutate → audit atomically. The services do
**not** write the audit log in the POC (that's MCP-side / future Audit service).

---

## 3. Licensing service (`/licensing/v1`)

### Reads
| Method · Path | Purpose | Returns |
|---|---|---|
| `GET /entities/search?name=&page=&size=` | bounded entity name search (`search_entitlements`) | Page&lt;EntitySummary&gt; |
| `GET /entities/{id}` | one customer | Entity |
| `GET /entities/{id}/master-licenses?page=&size=` | a customer's umbrellas (`list_licenses_by_entity`) | Page&lt;MasterLicenseSummary&gt; |
| `GET /master-licenses/{id}?include=licenses,administrators,licensee` | umbrella header + optional sub-objects | MasterLicense |
| `GET /master-licenses/{id}/licenses?page=&size=` | licenses under an umbrella | Page&lt;License&gt; |
| `GET /master-licenses/{id}/administrators` | admins (master-scoped, per MW) (`get_license_administrators`) | [Administrator] |
| `GET /licenses/{id}` | one license, status, dates (`get_license_status`) | License |
| `GET /licenses/{id}/products` | offerings + seats (`get_license_products`) | [LicensedProduct] |
| `GET /licenses/{id}/end-users?page=&size=` | seat membership (drives capacity math) | Page&lt;EndUser&gt; |

### Writes
| Method · Path · Body | Purpose (MCP tool) | Returns |
|---|---|---|
| `PATCH /license-products/{id}` · `{ "seatCount": 12 }` | `update_seat_count` — 409 if below current usage | `{before, after}` LicensedProduct |
| `PATCH /licenses/{id}` · `{ "expiryDate": "2027-02-28" }` | `extend_license_expiry` | `{before, after}` License |
| `POST /licenses/{id}/end-users` · `{ "userEmail": "..." }` | `add_user_to_license` — 409 if at capacity | EndUser |
| `POST /master-licenses/{id}/administrators` · `{ "userEmail": "...", "renewalNotifications": true }` | `transfer_license_admin` (add side) | Administrator |
| `DELETE /master-licenses/{id}/administrators/{userId}` | `transfer_license_admin` (remove side) | 204 |

**Example** — `GET /licenses/5001/products`:
```json
[
  { "id": 9001, "licenseId": 5001, "masterLicenseId": 123, "productCode": "CWS",
    "productName": "Campus-Wide Suite", "isSuite": true, "seatCount": 25,
    "businessOfferingId": 4021 },
  { "id": 9002, "licenseId": 5001, "masterLicenseId": 123, "productCode": "DSP",
    "productName": "DSP System Toolbox", "isSuite": false, "seatCount": 5,
    "businessOfferingId": 4017 }
]
```

---

## 4. Entitlement service (`/entitlement/v1`)

### Reads
| Method · Path | Purpose | Returns |
|---|---|---|
| `GET /entitlements/{id}?include=policy,people` | one entitlement (+ optional sub-objects) | Entitlement |
| `GET /entitlements?licenseId=&masterLicenseId=&status=&productCode=&page=&size=` | filter entitlements (≥1 criterion required, per MW) | Page&lt;Entitlement&gt; |
| `GET /entitlements/{id}/policy` | the 1:1 usage policy | Policy |
| `GET /entitlements/{id}/people?page=&size=` | who's assigned (`entitlement_person`) | Page&lt;EntitlementPerson&gt; |
| `GET /users/{email}/entitlements?status=&page=&size=` | a user's entitlements (`check_user_entitlements`) — resolves via `entitlement_person` | Page&lt;Entitlement&gt; |

**Example** — `GET /users/jane.doe@acme.com/entitlements?status=active`:
```json
{
  "items": [
    { "id": 44012, "licenseId": 5001, "masterLicenseId": 123, "productCode": "SL",
      "productName": "Simulink", "entitlementType": "license",
      "activationType": "standalone_named_user", "status": "active",
      "policy": { "policyName": "Named User", "maxActivations": 1, "activationTtlDays": 30 } }
  ],
  "pageInfo": { "currentPage": 0, "pageSize": 100, "totalPages": 1, "totalElements": 1, "hasNextPage": false }
}
```

---

## 5. Activation service (`/activation/v1`)

### Reads
| Method · Path | Purpose | Returns |
|---|---|---|
| `GET /activations/{id}` | one activation | Activation |
| `GET /activations?userEmail=&entitlementId=&status=&staleDays=&page=&size=` | filter activations; `staleDays=N` → `now()-last_heartbeat > N days` | Page&lt;Activation&gt; |

### Writes
| Method · Path · Body | Purpose (MCP tool) | Returns |
|---|---|---|
| `POST /activations/{id}/revoke` · `{ "reason": "..." }` | `revoke_activation` → sets status `inactive` | `{before, after}` Activation |
| `POST /activations/{id}/reset` · `{ "reason": "..." }` | `reset_installation_slot` → frees the machine slot | `{before, after}` Activation |

**Example** — `GET /activations?userEmail=jane.doe@acme.com&staleDays=60`:
```json
{
  "items": [
    { "id": 700123, "entitlementId": 44012, "userEmail": "jane.doe@acme.com",
      "machineId": "MW-0000700123", "machineName": "LT-4821", "os": "macOS 15",
      "activationDate": "2025-11-02", "lastHeartbeat": "2026-04-03T09:14:00Z",
      "status": "inactive" }
  ],
  "pageInfo": { "currentPage": 0, "pageSize": 100, "totalPages": 1, "totalElements": 1, "hasNextPage": false }
}
```
This is exactly the Story-2 signal (a stale activation past its policy TTL).

---

## 6. DTOs (fields → schema source)

JSON keys are camelCase; the source column is the snake_case table column.

**EntitySummary / Entity** — `id, name, entityType, industry, country, region` (+ `externalRef` on full).
**MasterLicense** — `id, masterLicenseRef, entityId, label, program, sponsor` (+ optional `licenses[]`, `administrators[]`).
**License** — `id, licenseRef, masterLicenseId, status, startDate, expiryDate`.
**LicensedProduct** — `id, licenseId, masterLicenseId, productCode, productName, isSuite, seatCount, businessOfferingId` (`license_product` joined to `product`).
**Entitlement** — `id, licenseId, masterLicenseId, licenseProductId, productCode, productName, entitlementType, activationType, status, label, grantedAt` (+ optional `policy`, `people[]`).
**Policy** — `id, entitlementId, policyName, quantity, maxActivations, activationTtlDays, allowOffline, reactivationLimit`.
**EntitlementPerson** — `id, entitlementId, userId, userEmail, role, addedDate, status`.
**Activation** — `id, entitlementId, userId, userEmail, machineId, machineName, os, activationDate, lastHeartbeat, status`.
**EndUser** — `id, licenseId, userId, userEmail, addedDate, status` (`license_end_user`).
**Administrator** — `id, masterLicenseId, userId, userEmail, renewalNotifications, addedDate` (`master_license_admin`).
**Page&lt;T&gt;** — `{ items: T[], pageInfo }`.
**Error** — `{ detail, detailType, detailMessages }`.

`userEmail` fields are the `app_user.email` join — the services resolve
`webProfileId`/`email` ↔ `user_id` internally so callers never handle raw user ids.

---

## 7. MCP tool → endpoint map (the C1 target)

| MCP tool | Service call |
|---|---|
| `list_licenses_by_entity` | `GET /licensing/v1/entities/{id}/master-licenses` |
| `get_license_status` | `GET /licensing/v1/licenses/{id}` |
| `get_license_products` | `GET /licensing/v1/licenses/{id}/products` |
| `get_license_administrators` | `GET /licensing/v1/master-licenses/{id}/administrators` |
| `search_entitlements` | `GET /licensing/v1/entities/search?name=` |
| `check_user_entitlements` | `GET /entitlement/v1/users/{email}/entitlements` |
| `add_user_to_license` | `POST /licensing/v1/licenses/{id}/end-users` |
| `update_seat_count` | `PATCH /licensing/v1/license-products/{id}` |
| `extend_license_expiry` | `PATCH /licensing/v1/licenses/{id}` |
| `transfer_license_admin` | `POST` + `DELETE /licensing/v1/master-licenses/{id}/administrators` |
| `revoke_activation` | `POST /activation/v1/activations/{id}/revoke` |
| `reset_installation_slot` | `POST /activation/v1/activations/{id}/reset` |
| `get_audit_history` | Audit service (deferred) |

**No MCP tool handler changes** — only each `data_access/` function body flips from
SQLAlchemy to the HTTP call above. That's the whole bet.

---

## 8. Open items for review
- Assignment writes (add/remove `entitlement_person`) — not yet needed by a tool; add to Entitlement service if a workflow appears.
- Whether `search_entitlements` also needs an Entitlement-service search path (by product/expiry/seat-util) vs. staying entity/license-scoped on Licensing.
- Service-to-service auth mechanics (token issuance/validation) live in **B5**; this doc only fixes the header contract.
- **Add `entityId` + `entityName` to the `License` DTO?** Licensing owns `entity`,
  so denormalizing avoids a master-license hop for the common "who owns this license"
  need. (The mock already does this.)

### Seat-model reconciliation (surfaced by C1 — needs a decision)
The flat POC exposed a **single license-level `seat_count`** and a `10/10`
utilization. The deep model puts **`seatCount` on each `license_product`** (per
offering) and has **no license-level seat number**, so the current `get_license_products`
tool shape can't be reproduced 1:1. Two things to decide:

1. **License-level seats** — is "at capacity" now a **per-offering** concept
   (MATLAB 10/10, Simulink 10/10 separately)? The C1 adapter currently *sums*
   product seats as a stopgap (`10 + 10 = 20`), which changes the demo's "10/10"
   story to "10/20". Per-product utilization is almost certainly the correct model —
   **recommend the tool output evolves to per-product seat/usage.**
2. **`license_type`** — no deep equivalent (the deep model carries per-product
   `licenseTerm`/`activationType`). The adapter returns `null`; decide whether to
   drop the field or derive it.

These are the "tools stay identical" bet's real edges: the *handlers* don't change,
but a few *output fields* must, because the deep model is more correct than the flat one.
