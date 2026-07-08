# Mock domain services (C1 dev scaffolding)

**Not the real services.** This is a fixture-backed mock of the domain services
(per [../CONTRACTS.md](../CONTRACTS.md)) used to develop the **MCP repoint (C1)**
before the real DB-backed services exist. It returns canned, contract-shaped
responses — no business logic, no DB. Khokle's real services (Workstream B)
supersede it; C1 then just repoints its base URL (C3).

The fixtures bake in the **Story-1 demo record** (Acme / `L-99001`) so C1 is
testable before the golden records are planted into the real dataset (A3).

## Run

```bash
.venv/bin/uvicorn services.mock.app:app --port 8090
```

## Use it from the MCP

```bash
LICENSING_BACKEND=services LICENSING_SERVICE_URL=http://localhost:8090 \
  .venv/bin/python -c "from licensing_mcp.tools.get_license_products import get_license_products; \
print(get_license_products('L-99001'))"
```

Default backend is `sqlite` (the live POC path, untouched). Set
`LICENSING_BACKEND=services` to route `data_access` through HTTP instead.

## Implemented so far (vertical slice)
- `GET /licensing/v1/licenses/{ref}`
- `GET /licensing/v1/licenses/{ref}/products`
- `GET /licensing/v1/licenses/{ref}/end-users`

…which back the repointed `get_license_products` tool end-to-end. More endpoints
get added as each tool is repointed (see [../CONTRACTS.md](../CONTRACTS.md) §3–5).
