"""
HTTP client for the domain services (C1 + C2 + C3 seams).

This is what replaces raw SQLAlchemy when LICENSING_BACKEND=services. Each method
is a thin wrapper over one contract endpoint (services/CONTRACTS.md); the mapping
from service DTOs to the tool-facing shapes lives in the query_* functions, so
tool handlers stay identical.

  C3 — base URLs are env-driven (per service), with local-dev defaults.
  C2 — Boundary-2 auth headers are attached to every call (stub values in the POC;
       real signed-token issuance/validation is B5).
  C1 — the query_* functions dispatch to these methods.

404s are raised as ValueError so the tool layer converts them to the same
structured error it already returns for the SQL path — no handler change.
"""
from __future__ import annotations

import os

import httpx

# ── C3: env-driven service URLs, local-dev defaults ──────────────────────────
LICENSING_URL = os.environ.get("LICENSING_SERVICE_URL", "http://localhost:8090")
ENTITLEMENT_URL = os.environ.get("ENTITLEMENT_SERVICE_URL", "http://localhost:8091")
ACTIVATION_URL = os.environ.get("ACTIVATION_SERVICE_URL", "http://localhost:8092")

# ── C2: Boundary-2 service-identity headers (stub values in the POC) ─────────
def _auth_headers() -> dict[str, str]:
    return {
        "mathworks-access-key": os.environ.get("MW_SERVICE_ACCESS_KEY", "poc-access-key"),
        "X-MW-WS-Caller-Id": "LICENSING-MCP",
        "mathworks-requestid": os.environ.get("MW_REQUEST_ID", "poc-request"),
    }


class ServiceError(Exception):
    """Non-404 transport/service failure — tool layer maps to a generic error."""


class ServiceClient:
    """
    Backend handle returned by get_session() in services mode. Named so query_*
    functions can detect it (isinstance) and take the HTTP path. Use/close like a
    session (the tool layer already does `session.close()`).
    """

    def __init__(self, timeout: float = 10.0):
        self._http = httpx.Client(timeout=timeout, headers=_auth_headers())

    def close(self):
        self._http.close()

    # allow `with get_session() as s:` and the tool's try/finally close()
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _get(self, url: str, not_found_msg: str):
        try:
            resp = self._http.get(url)
        except httpx.HTTPError as e:  # network/timeout
            raise ServiceError(str(e)) from e
        if resp.status_code == 404:
            raise ValueError(not_found_msg)
        if resp.status_code >= 400:
            raise ServiceError(f"{resp.status_code} from {url}: {resp.text[:200]}")
        return resp.json()

    # ── Licensing service ────────────────────────────────────────────────────
    def get_license(self, ref: str) -> dict:
        return self._get(f"{LICENSING_URL}/licensing/v1/licenses/{ref}",
                         f"License '{ref}' not found.")

    def get_license_products(self, ref: str) -> list[dict]:
        return self._get(f"{LICENSING_URL}/licensing/v1/licenses/{ref}/products",
                         f"License '{ref}' not found.")

    def get_license_end_users(self, ref: str, page: int = 0, size: int = 100) -> dict:
        return self._get(
            f"{LICENSING_URL}/licensing/v1/licenses/{ref}/end-users?page={page}&size={size}",
            f"License '{ref}' not found.")
