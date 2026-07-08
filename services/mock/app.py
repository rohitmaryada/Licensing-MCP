"""
Mock domain services — contract-shaped fixtures for C1 development.

WHY THIS EXISTS (and what it is NOT):
  C1 repoints the MCP's data_access/ layer from SQLAlchemy to httpx calls against
  the domain services (services/CONTRACTS.md). To build that *before* the real
  services exist, we develop against this mock. It returns **contract-shaped
  fixtures** — NOT real business logic over the DB. That keeps this out of the
  Services workstream's lane (Khokle owns the real DB-backed services, B2–B4);
  when those are ready, C1 just repoints its base URL (C3) and this is retired.

  The fixtures bake in the Story-1 demo record (Acme / L-99001) so C1 is testable
  before the golden records are planted into the real dataset (A3).

Run:
  .venv/bin/uvicorn services.mock.app:app --port 8090
Then point the MCP at it:
  LICENSING_BACKEND=services LICENSING_SERVICE_URL=http://localhost:8090 \
    .venv/bin/python -m licensing_mcp
"""
from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock Licensing Service", version="0.1")


def _not_found(detail: str):
    # Mirrors the MasterLicenseWS error shape (CONTRACTS.md §2).
    return JSONResponse(status_code=404,
                        content={"detail": detail, "detailType": "NOT_FOUND", "detailMessages": []})


# ── Fixtures (contract-shaped) — the Story-1 demo record ─────────────────────
LICENSES = {
    "L-99001": {
        # GET /licensing/v1/licenses/{ref}
        "license": {
            "id": 99001, "licenseRef": "L-99001", "masterLicenseId": 9900,
            "entityId": 42, "entityName": "Acme Corp", "entityType": "enterprise",
            "status": "active", "startDate": "2025-03-01", "expiryDate": "2026-02-28",
        },
        # GET /licensing/v1/licenses/{ref}/products
        "products": [
            {"id": 9001, "licenseId": 99001, "masterLicenseId": 9900, "productCode": "ML",
             "productName": "MATLAB", "isSuite": False, "seatCount": 10,
             "category": "core", "basePrice": 860.0, "businessOfferingId": 4001},
            {"id": 9002, "licenseId": 99001, "masterLicenseId": 9900, "productCode": "SL",
             "productName": "Simulink", "isSuite": False, "seatCount": 10,
             "category": "core", "basePrice": 1200.0, "businessOfferingId": 4002},
        ],
        # GET /licensing/v1/licenses/{ref}/end-users  (10/10 occupied — at capacity)
        "endUsers": [
            {"id": 5000 + i, "licenseId": 99001, "userId": 7000 + i,
             "userEmail": f"user{i}@acmecorp.com", "addedDate": "2025-03-05", "status": "active"}
            for i in range(10)
        ],
    }
}


def _require_auth(access_key: str | None):
    # Boundary-2 stub: presence check only in the POC (real validation is B5).
    if not access_key:
        raise HTTPException(status_code=401, detail="missing mathworks-access-key")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "mock-licensing"}


@app.get("/licensing/v1/licenses/{ref}")
def get_license(ref: str, mathworks_access_key: str | None = Header(default=None)):
    _require_auth(mathworks_access_key)
    rec = LICENSES.get(ref)
    if not rec:
        return _not_found(f"License not found for ref: {ref}")
    return rec["license"]


@app.get("/licensing/v1/licenses/{ref}/products")
def get_license_products(ref: str, mathworks_access_key: str | None = Header(default=None)):
    _require_auth(mathworks_access_key)
    rec = LICENSES.get(ref)
    if not rec:
        return _not_found(f"License not found for ref: {ref}")
    return rec["products"]


@app.get("/licensing/v1/licenses/{ref}/end-users")
def get_license_end_users(ref: str, page: int = 0, size: int = 100,
                          mathworks_access_key: str | None = Header(default=None)):
    _require_auth(mathworks_access_key)
    rec = LICENSES.get(ref)
    if not rec:
        return _not_found(f"License not found for ref: {ref}")
    items = rec["endUsers"]
    return {"items": items[page * size:(page + 1) * size],
            "pageInfo": {"currentPage": page, "pageSize": size, "totalPages": 1,
                         "totalElements": len(items), "hasNextPage": False}}
