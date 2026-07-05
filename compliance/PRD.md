# PRD — License Creation Compliance Gate (Draft v0.1)

> Status: DRAFT — shaping phase. Open questions marked ❓.
> Decisions already made with Rohit marked **DECIDED**.
> Last updated: 2026-06-19

## 1. Problem Statement

Before a MathWorks license is created, the transaction must clear a set of
**compliance checks**: the customer must be a party MathWorks is legally
permitted to do business with, the products must be exportable to the
customer's destination and end use, the product set must be internally valid,
and the tax treatment must be determined. Today these checks are enforced
(❓ confirm current state: manually by trade-compliance staff? siloed per
system? only at order time, not license setup?), which means violations are
caught late or inconsistently — producing blocked orders, rework, and, in the
denied-party case, **regulatory exposure** (screening failures are federal
violations with monetary and criminal liability, not just process defects).

We will build a **License Creation Compliance Gate**: a single pre-flight
pipeline that runs every required check before a license is created, returns a
clear verdict, and records an auditable decision — including who overrode what
and why.

This extends the existing **Licensing Intelligence MCP**, whose `cs_executor`
already implements `gate → mutate → audit → commit`. The compliance gate
expands "gate" from a role check into a multi-check pipeline; the create + audit
machinery is reused.

## 1a. POC Framing (DECIDED)

A proof of concept to **sell the idea** of a unified compliance gate.

- Optimize for **demo impact and learning**, not production ops.
- No integration with real trade-compliance systems; we mimic them with
  **real public reference data + synthetic subjects** (see §8) — the same
  strategy as the Dependency Resolver POC.
- A POC deliverable is an **evidence-based production recommendation** (ADR):
  orchestration shape, fail-open vs fail-closed, list-monitoring scope.

## 2. Goals

- One **compliance gate** shared by license setup, the self-serve portal, and
  the CS agent — a single place where "can this license be created?" is answered.
- **Pluggable hooks**: each compliance domain (party screening, export, tax,
  dependency) is an independent check behind a common interface, added or
  removed without touching the orchestrator.
- A realistic **verdict model**: not just allow/deny, but a manual-review path
  and a documented override — because real compliance is rarely binary.
- **Auditable & point-in-time**: every decision records which data/list version
  it was evaluated against, reproducible months later.
- Prove the **service-oriented architecture** the existing MCP always promised
  (tools orchestrate services, not raw SQL) — see §9, §11.

## 3. Non-Goals (proposed — confirm)

- **Not the system of record** for screening lists, ECCN classifications, or tax
  tables — the gate *consumes* authoritative data, it doesn't own it.
- **Not the adjudication authority** — it surfaces and scores potential
  problems; a human compliance officer makes the final legal call on holds.
- **Not legal/tax advice** — it captures determinations, it doesn't replace
  trade-compliance counsel.
- Pricing/discounting; entitlement or install-time logic.

## 4. Users & Consumers

| Consumer | Mode | Needs |
|---|---|---|
| License-setup / CS tooling (the MCP agent) | sync, agent-facing | clear verdict, explainability, override-with-reason |
| Self-serve portal | sync, customer-facing | fast PASS for the clean majority; friendly "your order is under review" on HOLD |
| Compliance officer | async, review queue | adjudicate HOLDs, see match evidence, record decisions |
| ❓ Order management / CPQ | TBD | TBD |

## 5. The Compliance Gate Model (architecture centerpiece) — DECIDED shape

```
create_license(customer, productSet, context)
        │
        ▼  ── COMPLIANCE GATE ───────────────────────────────────
        │   run all required hooks (parallel where independent)
        │
        │   ① party screening   → PASS | HOLD | FAIL
        │   ② export control    → PASS | HOLD | FAIL
        │   ③ dependency check  → PASS | FAIL          (the resolver service)
        │   ④ tax determination → PASS | HOLD
        │
        │   aggregate verdict:
        │     any FAIL                → BLOCK
        │     else any HOLD           → NEEDS_REVIEW (queue)
        │     else                    → ALLOW
        ────────────────────────────────────────────────────────
        │  ALLOW (or NEEDS_REVIEW cleared by override + reason)
        ▼
   create license  +  compliance decision record (audit)
```

- **Hook interface (DECIDED):** every check satisfies one contract —
  `evaluate(subject, context) → Verdict{status, findings[], evidence, dataVersion}`.
  This is the compliance analogue of the resolver's `GraphRepository` port: the
  orchestrator depends only on the interface, hooks are swappable/independent.
- **Hooks are services**, not in-process functions — the dependency resolver is
  already a separate Go service. This is the forcing function that moves the MCP
  from "direct SQL in tools" to "tools orchestrate services" (§9).
- **Aggregation is conservative (DECIDED):** any FAIL blocks; any HOLD requires
  review; ALLOW only when all clear. Compliance defaults to caution.

## 6. First Hook (centerpiece): Denied-Party Screening — DECIDED

The deep, demo-leading hook. (The resolver's "LER engine" is its centerpiece;
this is ours.)

- **What it does:** screen the customer entity — and ❓ its principals,
  addresses, and ultimate parent? — against consolidated denied/sanctioned-party
  lists. Returns PASS (no match), HOLD (possible match → review), FAIL
  (confirmed/high-confidence match).
- **Real data (DECIDED strategy):** the US **Consolidated Screening List (CSL)**
  is published by the US government as a free, downloadable/API dataset
  combining OFAC SDN, BIS Denied Persons, BIS Entity List, and others. Real,
  recognizable, defensible — stakeholders see actual list structure.
  - ❓ POC jurisdiction scope: US (CSL) only, or also EU/UN consolidated lists?
- **The hard problem = fuzzy matching (the technical centerpiece).** Customer
  names never match list entries exactly — transliteration, aliases,
  abbreviations, "Acme Corp" vs "ACME Corporation Ltd", address variants. The
  engine must:
  1. normalize names/addresses,
  2. score candidate matches (token/edit-distance + alias expansion),
  3. map score → verdict via tunable thresholds
     (`≥ high → FAIL`, `band → HOLD`, `< low → PASS`).
  This scoring + threshold model is what makes the three-verdict design real and
  is the most interesting thing to build and demo.
- **Planted subjects (for repeatable demo + tests):** synthetic customers seeded
  to land in each band — a clean PASS, a near-name HOLD, and a deliberate SDN
  match FAIL — exactly like the resolver's planted violations.

## 7. Verdict & Adjudication Model — DECIDED (Pass / Hold / Override+audit)

| Verdict | Meaning | Flow |
|---|---|---|
| `PASS` | hook found no issue | proceeds |
| `HOLD` | possible issue, human judgment required | enters the **review queue**; license creation paused |
| `FAIL` | confirmed disqualifying issue | **BLOCK**; cannot proceed without override |
| `OVERRIDE` | an authorized actor proceeds despite a HOLD/FAIL | requires role + **documented reason** → audit |

- **Review queue (HOLD):** a compliance officer adjudicates — sees the match
  evidence (which list, which fields, the score) and records *cleared* or
  *confirmed*. ❓ who holds this role / SLA for review?
- **Override (DECIDED):** reuses the existing audit machinery. An override is a
  first-class audit record: actor, role, original verdict, justification,
  before/after — structurally identical to today's `cs_audit_log` writes. The
  agent's reasoning chain makes these overrides richer than a free-text box
  (the same selling point as the licensing MCP audit story).
- **Severity:** hooks report findings; the *aggregator* maps to BLOCK/REVIEW.
  Hooks don't self-grade beyond PASS/HOLD/FAIL.

## 8. Data Sourcing & Realism — DECIDED: "real reference data + synthetic subjects"

Addresses Rohit's core worry (current dataset is ~0.0001% of MW scale, and
tools query SQL directly). Two phases, **architecture realism first, then scale**:

**Phase A — architecture realism (do first).**
- Stand up the gate as a **service layer**: the MCP `create_license` tool calls
  the compliance orchestrator over HTTP; the orchestrator calls hook services;
  hooks own their data. No tool reaches into SQL directly. This is the
  `data_access/` → microservice transition the security doc always described,
  now realized because compliance checks are *inherently* external services.
- **Reference data is REAL:** CSL for screening (✓ public), PRPA for dependency
  (✓ the resolver already does this), published ECCN categories for export.
- **Subjects are SYNTHETIC + deterministic:** a seeded generator produces
  customers/entities/orders, including planted cases that hit each verdict band.
  Deterministic → repeatable demos + ground-truth tests.

**Phase B — scale (do second).**
- Generate large synthetic customer/order volumes (target ❓ — 10⁶ entities?
  10⁵ orders/day?) to stress screening throughput and the orchestrator.
- The CSL itself is real and non-trivial (tens of thousands of entries), so
  fuzzy-match-at-volume is a genuine performance story, not a toy.
- Output a **point-in-time, versioned** dataset (every decision references the
  `listVersion`/`datasetVersion` it screened against — §10).

## 9. Integration with the Existing Licensing MCP — DECIDED

- A new MCP **write tool** `create_license` (or `validate_license_creation`)
  routes through `cs_executor`, whose gate step now invokes the compliance
  orchestrator before any mutation.
- Verdicts and overrides extend the existing **audit log** — a compliance
  decision is just another audited action by an actor (reuses identity +
  cs_executor + audit).
- The two **auth boundaries** from the security doc apply unchanged: the user
  is authenticated (Keycloak/PingID); the orchestrator calls hook services with
  service identity.
- The dependency resolver (separate Go service) becomes **hook ③** with zero
  changes to its design — proof that the pluggable-hook architecture works
  across teams and languages.

## 10. Auditability & Point-in-Time (compliance-critical)

- Every decision records: hooks run, each verdict, the **data/list version**
  used, the actor, and any override + reason.
- **Reproducibility:** "was this customer clear *as of the order date*?" must
  return the same answer when audited later → screen against the list snapshot
  in effect at decision time, store the snapshot id.
- ❓ **List monitoring (big scope flag):** real programs re-screen the existing
  book of business whenever the list changes (a customer can become sanctioned
  *after* purchase). In/out of POC scope? At minimum, name it.

## 11. Non-Functional Requirements ❓ (POC targets in FSD)

- **Fail-closed (DECIDED default):** if a hook service is unreachable, the gate
  does **not** silently allow — screening you couldn't perform is a HOLD/BLOCK,
  not a PASS. (Opposite of a typical fail-open availability stance; compliance
  inverts it.) Confirm per hook.
- Latency: PASS path must be fast enough for the portal (❓ p99 target). Fuzzy
  screening at volume is the cost driver.
- AuthN/Z between services (MW standard / the asymmetric-key pattern from the
  security doc).
- Observability, versioned responses (§10).

## 12. Architecture Direction (DECIDED for POC)

- **Compliance orchestrator** service exposing the `Hook` interface; runs hooks
  (parallel where independent), aggregates, returns a decision.
- **Polyglot is fine and intentional:** orchestrator in **Python** (consistent
  with the MCP, fast to build) calling the **Go** dependency resolver and the
  denied-party hook over HTTP. Demonstrates the language-agnostic service
  boundary — a selling point, not an accident.
- Denied-party hook: Python service wrapping the CSL data + the fuzzy-match
  engine; storage ❓ (Postgres for entities + a match index? in-memory for POC?).
- **Production recommendation is a POC deliverable (ADR-001):** orchestration
  (sync gate vs event-driven), fail-closed policy per hook, list-monitoring
  architecture — written from measured experience.

## 13. Open Questions (rollup)

1. Current-state compliance at MW: manual? where in the order/license lifecycle
   do these checks run today (§1)?
2. What entity attributes are available to screen — name only, or address,
   country, principals, ultimate parent (§6)?
3. Jurisdiction scope for the POC: US CSL only, or EU/UN too (§6)?
4. Who adjudicates HOLDs, and what's the review SLA (§7)?
5. Is the gate at **license creation** only, or also order/quote (mirrors the
   resolver's config-type question) (§9)?
6. List-monitoring / re-screening the existing book of business — in scope (§10)?
7. Fail-closed confirmed per hook (export/tax may differ from screening) (§11)?
8. Scale targets that make the pitch credible (§8 Phase B)?

## 14. Milestones / Roadmap (proposed)

- **M1 — Orchestrator + hook interface + denied-party (exact match)** against
  real CSL data; the gate shape works end to end with one hook.
- **M2 — Fuzzy matching + scoring + three-verdict model** (the centerpiece);
  planted subjects hit each band.
- **M3 — HOLD review workflow + override+audit** wired into the existing audit
  log.
- **M4 — MCP integration:** `create_license` routes through the gate; stub
  export/tax hooks; integrate the dependency resolver as hook ③.
- **M5 — Phase-B scale + ADR-001** production recommendation + demo polish.

## 15. Next Steps

- [ ] Resolve open questions (this doc → v1.0).
- [ ] FSD: hook interface contract, verdict/decision schema, denied-party
      fuzzy-match algorithm + thresholds, orchestrator API, CSL ingestion +
      versioning, MCP `create_license` integration, synthetic-subject generator.
- [ ] Confirm doc home (this repo's `compliance/` vs a dedicated repo like the
      resolver).
