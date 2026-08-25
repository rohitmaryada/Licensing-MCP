# Licensing Intelligence MCP — 5-Minute Video Script & Storyboard

**Purpose:** a single, ready-to-produce script for a ~5-minute explainer video —
what the prototype is, what it achieves, and why **MCP** is the way forward for
*live, governed* enterprise data access, versus static trained data, skills, and
plugins.

**How to use this file:** the **Voiceover** column is the narration — paste it
into your video tool (or read it). **On-screen** is the title/caption for that
beat. **Visuals** tells you what to show (mostly screen recordings of the running
agent + two simple diagrams). Timings target ~150 words/min ≈ ~760 words total.

> Capture two screen recordings first (they're most of your B-roll):
> 1. The agent answering a **read** ("What licenses does Acme Corp have?" → drill into a license).
> 2. **Story 2**: diagnosing jane.doe's stuck Simulink activation → revoking it → showing the **audit trail**, then a **CS-L1 rep being denied** a CS-L3 action.

---

## Scene 1 — The hook (0:00–0:35)

**On-screen:** *"Your AI knows everything — except your business."*

**Voiceover:**
> Ask a general AI assistant about your company's licenses, and it will answer
> confidently — and be completely wrong. It has never seen your data. It can't
> tell you who's entitled to what, whether a seat is free, or when a contract
> expires. And it certainly can't safely *change* anything. That gap — between a
> clever model and your live, governed systems — is the problem this prototype
> solves.

**Visuals:** A generic chatbot giving a vague/hallucinated answer to "how many
Simulink seats does Acme have?" → hard cut to the title card.

---

## Scene 2 — What the prototype is (0:35–1:15)

**On-screen:** *"Licensing Intelligence MCP — an AI copilot for Customer Service"*

**Voiceover:**
> This is the Licensing Intelligence MCP server: a working prototype that lets an
> AI agent answer real licensing questions and take real support actions — safely.
> A customer-service rep types in plain English: "Find Jane Doe at Acme Corp and
> tell me what she can run." The agent looks it up against live data, diagnoses
> the issue, and — with the right permissions — fixes it. No dashboards, no SQL,
> no guessing. It turns a fifteen-minute manual investigation into one sentence.

**Visuals:** Screen recording — open the agent, click "Find a customer", show the
answer with the entitlements and the flagged stale activation.

---

## Scene 3 — Why MCP, not the alternatives (1:15–2:25)  ⭐ core message

**On-screen:** *"Static data · Skills · Plugins · — vs — MCP"*

**Voiceover:**
> So why build this on MCP — the Model Context Protocol — and not the usual
> approaches? Because none of the alternatives actually solve it. **Trained data**
> is frozen at training time — it can't see today's licenses, and it can only
> talk, never act. **Skills** teach a model *how* to do a task, but they still
> don't connect it to your live systems or let it perform governed actions.
> **Plugins** were a step forward, but every one is a bespoke, per-app bolt-on —
> each reinventing authentication, data formats, and security. **MCP is an open
> standard** — one consistent way for any AI client to reach live, authoritative
> data *and* take controlled, audited actions. Live data instead of stale
> memory. Real actions instead of just answers. And one protocol instead of a
> dozen brittle integrations.

**Visuals:** A 4-column comparison building in one at a time — Trained data
(❌ live, ❌ act), Skills (❌ live data, ❌ act), Plugins (⚠️ bespoke, ⚠️ governance),
**MCP (✅ live, ✅ act, ✅ standard, ✅ governed)**.

---

## Scene 4 — How it works: live, swappable data access (2:25–3:15)

**On-screen:** *"Live data through a real service architecture"*

**Voiceover:**
> Under the hood, the agent never touches a database directly. It calls tools;
> the tools call domain microservices; the services own the data. That means the
> agent works against *real* systems — and the data layer is just a connection
> string. The same agent runs against a local database or a hosted cloud one by
> changing a single variable — which means the data can stay entirely inside the
> enterprise. Nothing has to leave your walls for the AI to be useful. Swap our
> stand-in services for your production ones, and the agent doesn't change at all.

**Visuals:** Simple 3-tier diagram animating left-to-right —
`AI agent → MCP tools → domain services → database` — then a callout: "database =
one env var → local or cloud, data never leaves."

---

## Scene 5 — The real value: governed, role-gated writes with audit (3:15–4:15)  ⭐

**On-screen:** *"It doesn't just answer — it acts, safely."*

**Voiceover:**
> Reading data is table stakes. The real leap is letting AI *act* — and doing it
> safely. Watch: a customer can't activate Simulink on a new laptop. The agent
> diagnoses a stale activation holding her only seat, and proposes to revoke it.
> The rep confirms — and every write is role-gated and permanently audited: who
> did it, why, and the before-and-after state. And when a junior rep tries an
> action above their level, the system refuses and *logs the attempt*.
> Authorization and audit are enforced by the server, not left to the model's
> discretion. That's what makes an AI agent safe to put in front of real
> operations.

**Visuals:** Screen recording — the revoke flow end-to-end: diagnosis → confirm →
"activation revoked, audit AUD-… recorded" → open the audit trail → then log in as
a CS-L1 rep, attempt a CS-L3 action, show the **"permission denied, logged"**
response.

---

## Scene 6 — The bigger picture (4:15–4:45)

**On-screen:** *"From copilot to customer self-service — one architecture"*

**Voiceover:**
> And this is just the first rung. The same governed foundation extends outward:
> today, an internal copilot that makes support faster and safer; next, a
> customer-facing agent that configures and provisions licenses; with compliance
> and denied-party screening as the guardrail that makes autonomy safe. One
> architecture, a spectrum of increasing autonomy — all built on live data and
> enforced governance.

**Visuals:** A three-step "spectrum of autonomy" bar: *CS copilot (today) →
customer-facing config → autonomous commerce*, with "governed & audited"
underlining all three.

---

## Scene 7 — Close (4:45–5:00)

**On-screen:** *"Live data. Real actions. Enterprise-grade governance."* + logo/title

**Voiceover:**
> Static models can only talk about the past. MCP lets AI work with your live
> reality — and act on it, within the rules. That's the way forward for AI in the
> enterprise, and it's working today.

**Visuals:** Return to the title card; end on the tagline.

---

## Production notes

- **Length:** ~760 words ≈ 5:00 at a measured pace. Trim Scene 6 first if you run long.
- **Best-fit tools (any takes this script):**
  - *Screen-recording + AI voice + edit:* **Descript** (record the agent, paste the script, generate a natural voice) — best fit since half your value is the live demo.
  - *Script-to-video with an avatar narrator:* **Synthesia** or **HeyGen**.
  - *Script-to-video with stock/motion:* **Pictory** or **InVideo AI**.
  - *Slides-to-video:* **Gamma** or **Canva** (import Scenes as slides, add the recordings).
- **Two diagrams to make** (Scenes 3 & 4): the 4-way comparison and the 3-tier
  flow — a few minutes in Canva/Keynote, or ask and I'll generate them as clean
  SVG/graphics you can drop in.
- **Tone:** confident, concrete, business-first; let the demo footage carry the
  technical proof rather than jargon.
