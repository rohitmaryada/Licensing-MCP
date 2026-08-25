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


def _detail(resp) -> str:
    """Pull the human 'detail' out of a service error body (falls back to text)."""
    try:
        return resp.json().get("detail") or resp.text[:200]
    except Exception:
        return resp.text[:200] or f"HTTP {resp.status_code}"


class ServiceClient:
    """
    Backend handle returned by get_session() in services mode. Named so the
    query_* functions detect it (duck-typed) and take the HTTP path. Exposes the
    same lifecycle the tool layer uses (`.close()`, context manager).
    """

    # Defined class attribute → lets callers detect the services backend via
    # getattr(handle, "backend", "sqlite") WITHOUT tripping __getattr__ below
    # (which only fires for *missing* attributes).
    backend = "services"

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
            "This tool isn't wired to the services backend yet — C1 repoint is "
            "in progress. Wired so far: find_user, check_user_entitlements, "
            "get_license_status, get_license_products. The rest still use the "
            "sqlite backend (set LICENSING_BACKEND=sqlite to use them now)."
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
    def search_users(self, name: str, company: str | None = None, size: int = 20) -> dict:
        """find_user — fuzzy user search by name or email, optionally narrowed by
        company. Empty result is a normal 200 with items=[], not a 404."""
        params = {"name": name, "size": size}
        if company:
            params["company"] = company
        return self._get(
            f"{ENTITLEMENT_URL}/entitlement/v1/users",
            f"User search '{name}' failed.",
            params=params,
        )

    def get_user_entitlements(self, email: str, include_stale: bool = True) -> dict:
        return self._get(
            f"{ENTITLEMENT_URL}/entitlement/v1/users/{email}/entitlements",
            f"User '{email}' not found.",
            params={"includeStaleActivations": str(include_stale).lower(), "size": 100},
        )

    def get_entitlement(self, entitlement_id: int) -> dict:
        return self._get(
            f"{ENTITLEMENT_URL}/entitlement/v1/entitlements/{entitlement_id}",
            f"Entitlement {entitlement_id} not found.",
        )

    # ── Activation service ───────────────────────────────────────────────────
    def get_user_activations(self, email: str) -> dict:
        return self._get(
            f"{ACTIVATION_URL}/activation/v1/activations",
            f"No activations found for '{email}'.",
            params={"userEmail": email, "size": 100},
        )

    def _post(self, url: str, body: dict, not_found_msg: str):
        try:
            resp = self._http.post(url, json=body)
        except httpx.HTTPError as e:
            raise ServiceError(str(e)) from e
        if resp.status_code == 404:
            raise ValueError(not_found_msg)
        if resp.status_code in (400, 409):
            raise ValueError(_detail(resp))  # business-rule violation → tool layer
        if resp.status_code >= 400:
            raise ServiceError(f"{resp.status_code} from {url}: {resp.text[:200]}")
        return resp.json()

    def revoke_activation(self, activation_id: int, reason: str) -> dict:
        """POST /activations/{id}/revoke → Change<ActivationState> {before, after}."""
        return self._post(
            f"{ACTIVATION_URL}/activation/v1/activations/{activation_id}/revoke",
            {"reason": reason},
            f"Activation {activation_id} not found.",
        )

    def reset_activation(self, activation_id: int, reason: str) -> dict:
        """POST /activations/{id}/reset → Change<ActivationState> {before, after}."""
        return self._post(
            f"{ACTIVATION_URL}/activation/v1/activations/{activation_id}/reset",
            {"reason": reason},
            f"Activation {activation_id} not found.",
        )

    def _patch(self, url: str, body: dict, not_found_msg: str):
        try:
            resp = self._http.patch(url, json=body)
        except httpx.HTTPError as e:
            raise ServiceError(str(e)) from e
        if resp.status_code == 404:
            raise ValueError(not_found_msg)
        if resp.status_code in (400, 409):
            raise ValueError(_detail(resp))
        if resp.status_code >= 400:
            raise ServiceError(f"{resp.status_code} from {url}: {resp.text[:200]}")
        return resp.json()

    def _delete(self, url: str, not_found_msg: str):
        try:
            resp = self._http.delete(url)
        except httpx.HTTPError as e:
            raise ServiceError(str(e)) from e
        if resp.status_code == 404:
            raise ValueError(not_found_msg)
        if resp.status_code >= 400:
            raise ServiceError(f"{resp.status_code} from {url}: {resp.text[:200]}")
        return None

    # ── Licensing writes ─────────────────────────────────────────────────────
    def patch_license_product_seats(self, license_product_id: int, seat_count: int) -> dict:
        return self._patch(
            f"{LICENSING_URL}/licensing/v1/license-products/{license_product_id}",
            {"seatCount": seat_count},
            f"License product {license_product_id} not found.",
        )

    def patch_license_expiry(self, license_id: int, expiry_date: str) -> dict:
        return self._patch(
            f"{LICENSING_URL}/licensing/v1/licenses/{license_id}",
            {"expiryDate": expiry_date},
            f"License {license_id} not found.",
        )

    def add_license_end_user(self, license_id: int, user_email: str) -> dict:
        return self._post(
            f"{LICENSING_URL}/licensing/v1/licenses/{license_id}/end-users",
            {"userEmail": user_email},
            f"License {license_id} not found.",
        )

    def get_master_administrators(self, master_license_id: int) -> list[dict]:
        return self._get(
            f"{LICENSING_URL}/licensing/v1/master-licenses/{master_license_id}/administrators",
            f"Master license {master_license_id} not found.",
        )

    def add_master_administrator(self, master_license_id: int, user_email: str) -> dict:
        return self._post(
            f"{LICENSING_URL}/licensing/v1/master-licenses/{master_license_id}/administrators",
            {"userEmail": user_email, "renewalNotifications": True},
            f"Master license {master_license_id} not found.",
        )

    def delete_master_administrator(self, master_license_id: int, user_id: int) -> None:
        return self._delete(
            f"{LICENSING_URL}/licensing/v1/master-licenses/{master_license_id}/administrators/{user_id}",
            f"{user_id} is not an administrator of master license {master_license_id}.",
        )

    def search_entities(self, name: str, size: int = 20) -> dict:
        """Fuzzy search customers/licensees by name (pg_trgm)."""
        return self._get(
            f"{LICENSING_URL}/licensing/v1/licensees",
            f"Entity search '{name}' failed.",
            params={"name": name, "size": size},
        )

    def get_entity_licenses(self, entity_id: int) -> dict:
        return self._get(
            f"{LICENSING_URL}/licensing/v1/licensees/{entity_id}/licenses",
            f"Licensee {entity_id} not found.",
        )
