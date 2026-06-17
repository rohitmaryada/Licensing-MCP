# Keycloak — one-command auth setup

This folder turns the manual Keycloak configuration (the ~20 UI steps in
`docs/keycloak-setup-guide.html`) into a single command. Docker Compose boots
Keycloak and imports a ready-made realm on first start.

## What gets created

`realm-export.json` pre-loads everything `agent/auth.py` expects:

| Item | Value |
|---|---|
| Realm | `licensing-mcp` |
| Client | `licensing-agent` (public, redirect `http://localhost:8100/callback`) |
| Email claim | mapped into the **access token** (so the agent can read it) |
| Admin console | `admin` / `admin` at http://localhost:8080 |

Three test users — **each matches a real `cs_users` row in the seeded database**,
one per CS tier so you can see role-gating change behavior:

| Username (type this at login) | Password | DB role |
|---|---|---|
| `rep.sarah@mathworks.com` | `password123` | CS-L1 |
| `amy.martin@mathworks.com` | `password123` | CS-L2 |
| `amy.james@mathworks.com` | `password123` | CS-L3 |

> ⚠️ **Log in with the FULL email as the username** — e.g. `rep.sarah@mathworks.com`,
> not `rep.sarah`. The imported users' username *is* their email (this guarantees
> the email claim matches `cs_users.email`, which the MCP server's `identity.py`
> requires). Typing the short name gives "Invalid username or password".

## Prerequisites

- Docker Desktop running

## Use it

```bash
cd keycloak
docker compose up -d        # first boot imports the realm (~30s)
```

Then in a second terminal, from the repo root, start the agent:

```bash
.venv/bin/uvicorn agent.app:app --port 8100
```

Open **http://localhost:8100** → Sign in → at the Keycloak prompt enter the
**full email** as the username (e.g. `rep.sarah@mathworks.com`) and `password123`.

Stop Keycloak when you're done:

```bash
cd keycloak && docker compose down        # keeps the imported realm in the volume
docker compose down -v                    # also wipes Keycloak's data (full reset)
```

## If you already set Keycloak up manually

You ran a `docker run --name licensing-keycloak ...` earlier, so that container
name is taken. Remove it first, then bring up Compose:

```bash
docker rm -f licensing-keycloak
cd keycloak && docker compose up -d
```

Your manual realm is discarded; this imported one replaces it (same realm name,
client, and the three DB-matched users).

## Verifying it works

1. Log in as **rep.sarah@mathworks.com** (CS-L1) → run Story 2
   ("jane.doe@acmecorp.com can't activate Simulink…") → it resolves, and the
   audit record shows rep.sarah as the actor.
2. Still as rep.sarah, ask **"Extend license L-99001 by 30 days"** (needs CS-L3)
   → permission denied by the MCP server. Keycloak proved *who* she is; the
   database decided *what she can't do*. That's the auth/authz split.
3. Sign out, log back in as **amy.james@mathworks.com** (CS-L3) → the same
   extend request now succeeds.

## How it works

`docker compose up` mounts `realm-export.json` into the container at
`/opt/keycloak/data/import/`, and the `--import-realm` flag tells Keycloak to
load any realm files there on startup. Subsequent starts skip the import if the
realm already exists (you'll see *"Realm 'licensing-mcp' already exists"* in the
logs — that's fine).

To re-import after editing `realm-export.json`, wipe the volume first:
`docker compose down -v && docker compose up -d`.

## Notes & gotchas

- **Image is pinned** to `quay.io/keycloak/keycloak:26.0` for reproducibility.
  Bump the tag in `docker-compose.yml` if you need a newer Keycloak.
- **Dev mode, not production.** `start-dev` uses an in-memory H2 database and
  disables TLS — fine for a local POC, never for production. The passwords here
  are throwaway demo credentials.
- **Bound to localhost** (`127.0.0.1:8080`) so Keycloak isn't exposed on your
  network.
- If token validation fails with *"Invalid signature"* after a Keycloak
  restart, restart the agent too — it caches Keycloak's signing keys (JWKS) at
  startup.
