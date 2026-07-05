# Positioning — Why This Project Exists (and Why It Matters)

> Status: Living doc — the "motivation" companion to the strategy docs.
> Audience: MathWorks stakeholders, peers, leadership — anyone who asks
> "what is this and why should I care?"
> Last updated: 2026-07-05
> See also: [scale-and-services-strategy.md](scale-and-services-strategy.md) ·
> [../compliance/PRD.md](../compliance/PRD.md) · [../TASKS.md](../TASKS.md)

---

## The one-sentence version

> We built a working proof that an AI agent can safely operate over MathWorks'
> licensing data — and, more importantly, we built it on the three architectural
> seams that let the *same* system climb from an internal support copilot to a
> customer-facing commerce experience without being re-architected.

The demo is not the point. **The seams are the point.** Everything below explains
that claim.

---

## 1. The problem worth solving

Licensing is where MathWorks' commercial complexity lives: master-licenses,
licenses, licensed-products, entitlements, policies, activations, seat math,
administrators, end-users — a deep relational hierarchy (~40M licenses in
production) sitting behind Commerce as the system of record.

Two groups feel that complexity every day:

- **CS reps**, who navigate it by hand to answer "why can't this user activate?"
  and to perform gated operations (revoke, transfer, extend, adjust seats).
- **Customers**, who can't self-serve anything non-trivial — configuring a
  suite, adding seats, adjusting entitlements means a human on both sides.

An AI agent that genuinely *understands* this model can compress both. But
"put a chatbot on it" is the wrong frame — the value and the risk both scale
with **how much the agent is trusted to act.** That trust dimension is the
organizing idea of this project.

---

## 2. The spectrum of autonomy

Licensing-agent use-cases aren't one product. They sit on a spectrum defined by
how much the agent is allowed to *do on its own*. Naming the spectrum is what
turns a demo into a roadmap.

| Phase | Use-case | Who acts | Human boundary | Industry maturity |
|-------|----------|----------|----------------|-------------------|
| **1** | **CS copilot** (internal, assisted) | Agent proposes, rep confirms | Human confirms every mutation | Mainstream — shipping today |
| **2** | **Customer-facing assisted config** (external) | Agent configures, hands off to checkout | Human crosses the payment boundary | Emerging — **the reachable sweet spot** |
| **3** | **Autonomous commerce** (external) | Agent configures → pays → provisions | None | Frontier — not publicly done for complex licenses |

**Phase 1 — CS copilot. ← the POC is here, working.**
A rep talks to the agent; it reads entitlement state, diagnoses, and *proposes*
mutations that a human confirms. This is the mainstream band — every enterprise
SaaS is bolting a copilot onto its admin console. Tangible goal: cut CS
handle-time and error rate on license operations. Our Story 2 (diagnose stale
activation → propose revoke → human "yes" → atomic audit) *is* this use-case,
demonstrated end-to-end through a real agent loop.

**Phase 2 — Customer-facing assisted config. ← the pitch.**
An agent on MathWorks.com where the *customer* describes intent ("3 more Simulink
seats, add Stateflow"), the agent configures the entitlement bundle, validates
it, and **hands off to the existing checkout/provisioning rail** rather than
completing the transaction. This is the commercial sweet spot: high value, but
the human still crosses the payment boundary, so the risk surface stays bounded.
Worth pitching precisely because it's *reachable* from Phase 1 and **nobody in
the complex-license space has publicly nailed it.**

**Phase 3 — Autonomous commerce. The frontier.**
Agent configures → pays → provisions with no human in the loop. Agentic-commerce
rails are emerging industry-wide, but complex-license self-serve (suites, seat
math, entitlement policies, compliance gates) is *not* something Adobe, Autodesk,
or peers have publicly shipped autonomously. High-complexity, later — and only
safe once the compliance gate exists.

---

## 3. Why the POC is a foundation, not a demo

This is the part that separates "we built a chatbot" from "we built the thing
that scales." Three deliberate seams, each already in the code, each mapping to
a rung on the spectrum.

### Seam 1 — the `data_access/` indirection (the whole bet)

Tool handlers never touch SQL. They call `data_access/`, which today runs
SQLAlchemy but is *shaped like a service client*. That is why the move to
production scale — Neon Postgres, three domain microservices, tools calling over
`httpx` — is cheap: **only `data_access/` changes; tool handlers stay
byte-identical.** This seam is the concrete mechanism by which a POC becomes an
enterprise system, and it is why the same Phase 1 tools survive into Phase 2/3
without a rewrite.

### Seam 2 — two independent auth boundaries (mirrors the real topology)

- **User → server:** Keycloak / OIDC — *who is calling* (already wired).
- **Server → microservices:** asymmetric-key / OAuth client-credentials — the
  real MathWorks service-identity pattern.

Kept independent from day one. Moving to Phase 2's customer-facing surface just
swaps *who the user is*; the service-identity boundary underneath doesn't move.

### Seam 3 — gate → mutate → audit → commit (autonomy-ready by construction)

Every write in `cs_executor.py` is role-gated, executed, then audited atomically
— rejections and failures audited too. This is *exactly* the structure needed to
raise autonomy safely: as you move from Phase 1 (human confirms) toward Phase 3
(agent acts), the only thing that changes is **who or what satisfies the gate.**
The audit trail and atomicity are already there; the human confirmation step is
simply the trust dial, turned down as confidence grows.

---

## 4. Why compliance is the enabler, not a side-quest

You cannot let an agent provision licenses to arbitrary parties without
denied-party screening. The compliance gate (`compliance/PRD.md` — OFAC/CSL
screening, fuzzy matching, Pass/Hold/Override + audit) is therefore not extra
credit — **it is the constraint that makes Phase 2 → 3 legally possible.** No
compliance gate, no autonomy. It belongs on the critical path.

---

## 5. The through-line (say this out loud)

> The POC isn't demonstrating a chatbot. It's demonstrating the three seams —
> data-access indirection, dual auth, and gated+audited mutation — that let a
> licensing agent climb the autonomy spectrum from internal copilot to
> customer-facing commerce **without re-architecting.**

And each planning doc on `main` is one rung made concrete:

- **scale-and-services-strategy.md** → Seam 1 productionized (the data tier).
- **compliance/PRD.md** → the gate that unlocks external autonomy.
- **TASKS.md** → the near-term work to stand the service tier up at real scale.

---

## 6. The 60-second spoken version

"MathWorks licensing is a deep, high-value data model that today needs a human
on every non-trivial operation. We built a working AI agent over it — but the
real result isn't the demo, it's *how* it's built. There's a spectrum of how
autonomous such an agent can be: an internal CS copilot that proposes and a human
confirms; a customer-facing agent that configures a purchase and hands off to
checkout; and eventually fully autonomous commerce. Ours works at the first rung
today, and it's architected on three seams — a swappable data-access layer, two
independent auth boundaries, and a gated-and-audited write path — so the same
system moves up that spectrum without a rewrite. The customer-facing middle rung
is the commercial sweet spot, and nobody in the complex-license space has
publicly nailed it yet. The compliance gate we're building is what makes going
there safe."
