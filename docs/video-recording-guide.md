# Video Recording Guide — Licensing Intelligence MCP (Descript)

A step-by-step guide to producing the ~5-minute explainer in **Descript**, using
the script in [demo-video-script.md](demo-video-script.md). Owner: **Rohit Khokle**.

**What you'll assemble:** narration (from the script) + **two screen recordings**
of the live agent + **two simple diagrams** + title/caption cards → one 5-min MP4.

---

## 0. Before you start — checklist

- [ ] Descript account (free tier is fine for a 5-min video).
- [ ] The stack running locally (Section 1).
- [ ] Browser cleaned up for recording: full-screen, no bookmarks bar, no
      personal tabs, **notifications muted** (macOS: turn on Do Not Disturb).
- [ ] ⚠️ **Record the browser only.** Do **not** screen-record a terminal or the
      `.env` — connection strings/keys must never appear on screen.
- [ ] Read the script once end-to-end so the click pacing matches the narration.

---

## 1. Prep the demo environment (once, before recording)

From the repo root, bring the stack up on the **local** DB (reliable — no cloud):

```bash
cd db && docker compose up -d
LICENSING_PG_URL=postgresql://licensing:licensing@localhost:5433/licensing \
  .venv/bin/python scripts/generate_bulk.py --reset --plant-demo
cd services && docker compose -f docker-compose.yml up -d --build
cd ../keycloak && docker compose up -d
cd .. && LICENSING_BACKEND=services .venv/bin/uvicorn agent.app:app --port 8100
```

Then, in the browser, open **http://127.0.0.1:8100** and confirm you can log in.

**Logins for the demo** (password `password123` for all):
- `rep.sarah@mathworks.com` — **CS-L1** (does the revoke; gets denied the L3 action)
- `amy.james@mathworks.com` — **CS-L3** (can do everything, for the role-gate contrast)

**Re-arm the demo before *each* Story-2 take** (revoke flips the activation to
inactive; this resets it so the flip is visible again):

```bash
docker exec licensing-postgres psql -U licensing -d licensing \
  -c "UPDATE activation SET status='active' WHERE machine_id='MAC-OLD-7291'"
```

---

## 2. Capture the two screen recordings

Use **Descript → Screen Recording** (or QuickTime), 1080p, browser window only.
Click **slowly and deliberately**, and **pause ~2 seconds** between actions —
that gives you clean cut points when editing. Do a couple of takes of each.

### Recording A — the read flow (~40s raw)  → used in Scenes 2 & 4
1. Log in as **rep.sarah**; land on the welcome screen (the four example prompts
   + the "What can this assistant do?" panel — expand it briefly, it's a great visual).
2. Ask: **"What licenses does Acme Corp have?"** — let the answer render.
3. Follow up: **"What's the status of L-DEMOACME, and what products does it cover?"**
4. (Optional) **"Who administers it?"**

### Recording B — Story 2: diagnose → act → audit → role gate (~75s raw)  → Scene 5
1. As **rep.sarah**, ask: **"jane.doe@acmecorp.com can't activate Simulink on a
   new machine. Diagnose why and free up her seat."**
2. Let the agent find the **stale MAC-OLD-7291 activation** and **propose the revoke**.
3. Confirm the revoke; capture the **"activation revoked · audit AUD-… recorded"** result.
4. Ask: **"Show me the audit trail for L-DEMOACME."** — capture the logged entry.
5. **Role gate:** still as sarah (CS-L1), ask **"Extend L-DEMOACME by 30 days."** →
   capture the **"permission denied — logged"** response.
6. (Optional contrast) log out, log in as **amy.james (CS-L3)**, run the same
   extend request → it **succeeds**. Powerful side-by-side.

> After this recording, **re-arm** (Section 1) before the next take.

---

## 3. Make the two diagrams (Scenes 3 & 4)

- **Scene 3 — the comparison:** a 4-column card — *Trained data · Skills · Plugins ·
  **MCP*** — with ✅/❌/⚠️ for "live data", "can act", "standard", "governed".
- **Scene 4 — the 3-tier flow:** `AI agent → MCP tools → domain services → database`,
  with a callout "database = one env var → local or cloud, data never leaves."

Build them in Canva/Keynote (a few minutes each), **or ask Claude to generate them
as drop-in SVG/PNG** — theme-neutral, sized for 1080p.

---

## 4. Set up the Descript project

1. **New Project** → name it "Licensing MCP — Explainer".
2. **Script-first workflow:** create a **Scene** for each of the 7 script scenes.
   Paste that scene's **Voiceover** text into the scene's script block.
3. **Voice:** either
   - **Record your own** (Descript transcribes it so you can edit video by editing
     text), or
   - **AI voice** — pick a Descript stock voice (or your own voice clone) and let
     it read each scene's script. Keep one voice for the whole video.
4. Descript generates a timeline from the script blocks — now you drop visuals on top.

---

## 5. Assemble — map assets to scenes

| Scene | Voiceover | Show on screen |
|---|---|---|
| 1 — Hook | "Your AI knows everything except your business…" | Generic chatbot giving a wrong answer → title card |
| 2 — What it is | "This is the Licensing Intelligence MCP…" | **Recording A**, step 1–2 (welcome + first answer) |
| 3 — Why MCP ⭐ | "So why MCP, not the alternatives…" | **Diagram 1** (comparison), columns building in |
| 4 — How it works | "The agent never touches a database directly…" | **Diagram 2** (3-tier) + a beat of Recording A |
| 5 — Governed writes ⭐ | "The real leap is letting AI act, safely…" | **Recording B** (revoke → audit → denial) |
| 6 — Bigger picture | "And this is just the first rung…" | Spectrum-of-autonomy bar (a simple 3-step graphic) |
| 7 — Close | "Static models can only talk about the past…" | Title card + tagline |

Tip: let the demo footage *breathe* — don't narrate over every click; pause the
VO and let a key moment (the revoke succeeding, the denial) land on its own.

---

## 6. Polish

- **Captions:** Descript auto-generates them — turn on, they lift comprehension and accessibility.
- **Title cards:** add each scene's **On-screen** line as a title/lower-third.
- **Zoom/highlight:** in the demo clips, zoom to the answer text and the audit
  record so viewers can read them.
- **Music:** a subtle, low background track (Descript stock) at ~10–15% volume.
- **Transitions:** simple cuts/fades — nothing flashy.
- **Timing:** target **5:00**. If long, trim Scene 6 first, then tighten pauses.

---

## 7. Export & hand off

- **Export → Video**, **1080p MP4**, 30 fps.
- Name: `licensing-mcp-explainer-v1.mp4`.
- Share the Descript project link too, so edits are easy later.

---

## Gotchas

- **Re-arm before every Story-2 take** (Section 1) — otherwise the activation is
  already inactive and the revoke shows no change.
- **No secrets on screen** — browser only; never the terminal/`.env`.
- **Mute notifications / Do Not Disturb** during capture.
- **First query can lag** if the stack just started — run one throwaway query to
  warm it before the real take.
- **Consistency:** same login (rep.sarah) across Recording A and the first half of
  B, so the header identity doesn't jump around unexpectedly.
