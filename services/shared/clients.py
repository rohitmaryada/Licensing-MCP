"""Sync HTTP client for the one sanctioned cross-service call (E1 -> Activation).

Sync, not async — E1 stays a `def` route (FastAPI thread-pools it automatically,
same as every other route in this codebase). Mixing a sync DB session into an
`async def` route would block the event loop for every other concurrent
request; there's no fan-out here that would justify async plumbing for one
downstream call (B2-READS-PLAN.md §7).

Unhandled failures (timeout, connection refused, non-2xx) propagate as
exceptions and are caught by shared.errors' catch-all handler, which already
returns a clean 500 — no extra resilience layer needed for this slice.
"""

import httpx

from services.shared.config import settings

_PASSTHROUGH_HEADERS = (
    "mathworks-access-key",
    "X-MW-WS-Caller-Id",
    "mathworks-requestid",
    "X-MW-WS-Security-Token",
)


def _forward_headers(request_headers) -> dict[str, str]:
    return {h: request_headers[h] for h in _PASSTHROUGH_HEADERS if h in request_headers}


class ActivationClient:
    def __init__(self, base_url: str | None = None, timeout: float = 3.0):
        self._client = httpx.Client(base_url=base_url or settings.ACTIVATION_SERVICE_URL, timeout=timeout)

    def stale_activations(self, entitlement_id: int, stale_days: int, request_headers) -> list[dict]:
        resp = self._client.get(
            "/activation/v1/activations",
            params={"entitlementId": entitlement_id, "staleDays": stale_days, "size": 100},
            headers=_forward_headers(request_headers),
        )
        resp.raise_for_status()
        return resp.json()["items"]


activation_client = ActivationClient()
