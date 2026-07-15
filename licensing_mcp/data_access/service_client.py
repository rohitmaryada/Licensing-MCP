"""
HTTP client for the real domain services (C1 · C2 · C3 seams).

Replaces raw SQLAlchemy when LICENSING_BACKEND=services. Each method wraps one
endpoint from services/ENDPOINTS.md; the flat→deep shape reconciliation lives in
the query_* adapter functions, so MCP tool handlers stay identical.

  C3 — per-service base URLs are env-driven, defaulting to the local docker-compose
       ports (Licensing :8001, Entitlement :8002, Activation :8003).
  C2 — Boundary-2 auth headers on every call (stub values; real JWT is B5).
  C1 — the query_* functions dispatch to these methods and map the DTOs.

404 → ValueError so the tool layer's existing error handling is unchanged.
"""
from __future__ import annotations

import os

import httpx

# ── C3: env-driven service URLs (local docker-compose defaults) ──────────────
LICENSING_URL = os.environ.get("LICENSING_SERVICE_URL", "http://localhost:8001")
ENTITLEMENT_URL = os.environ.get("ENTITLEMENT_SERVICE_URL", "http://localhost:8002")
ACTIVATION_URL = os.environ.get("ACTIVATION_SERVICE_URL", "http://localhost:8003")


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
    Backend handle returned by get_session() in services mode. Named so the
    query_* functions detect it (duck-typed) and take the HTTP path. Exposes the
    same lifecycle the tool layer uses (`.close()`, context manager).
    """

    def __init__(self, timeout: float = 15.0):
        self._http = httpx.Client(timeout=timeout, headers=_auth_headers())

    def __getattr__(self, name: str):
        # A query_* function not yet repointed (C1 in progress) is using this
        # handle as if it were a SQLAlchemy Session (e.g. `.query`, `.execute`).
        # Raise a CLEAR ValueError — the tool layer turns it into a readable
        # {"error": ...} instead of the opaque "an unexpected error occurred".
        # (Only fires for genuinely-missing attributes; defined methods like
        # get_user_entitlements/close never reach here.)
        raise ValueError(
            f"This tool isn't wired to the services backend yet — C1 repoint in "
            f"progress (so far only check_user_entitlements is; the rest are "
            f"blocked on a Licensing-service by-ref lookup). Tried '.{name}'. "
            f"Use LICENSING_BACKEND=sqlite for this tool."
        )

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _get(self, url: str, not_found_msg: str, params: dict | None = None):
        try:
            resp = self._http.get(url, params=params)
        except httpx.HTTPError as e:
            raise ServiceError(str(e)) from e
        if resp.status_code == 404:
            raise ValueError(not_found_msg)
        if resp.status_code >= 400:
            raise ServiceError(f"{resp.status_code} from {url}: {resp.text[:200]}")
        return resp.json()

    # ── Licensing service ────────────────────────────────────────────────────
    def get_license_by_ref(self, license_ref: str) -> dict:
        """Address a license by its public ref (business key). Returns the full
        composite (status, dates, products[], master, licensee, endUserCount)."""
        return self._get(
            f"{LICENSING_URL}/licensing/v1/licenses",
            f"License '{license_ref}' not found.",
            params={"ref": license_ref},
        )

    # ── Entitlement service ──────────────────────────────────────────────────
    def get_user_entitlements(self, email: str, include_stale: bool = True) -> dict:
        return self._get(
            f"{ENTITLEMENT_URL}/entitlement/v1/users/{email}/entitlements",
            f"User '{email}' not found.",
            params={"includeStaleActivations": str(include_stale).lower(), "size": 100},
        )
