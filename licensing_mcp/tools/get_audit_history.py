"""
Tool: get_audit_history (any CS role)

A read tool, but identity-gated: the audit trail contains rep emails and
customer PII, so unlike the open query surface it requires a resolved CS
actor. Any tier may read it — reading history is how reps build context.
"""

from typing import Annotated

from pydantic import Field

from licensing_mcp.data_access.audit import query_audit_history
from licensing_mcp.database import get_session
from licensing_mcp.identity import IdentityError, resolve_actor
from licensing_mcp.server_instance import mcp


@mcp.tool()
def get_audit_history(
    license_id: Annotated[str, Field(description="License whose audit history to retrieve. Format: L-XXXXX.")],
    limit: Annotated[int, Field(description="Maximum entries to return, newest first. Default 10.")] = 10,
) -> dict:
    """
    [CS only] Returns the audit trail for a license: every CS write action
    (successful, failed, or rejected) with who performed it, their role,
    the business reason, and before/after state.

    Use after performing a write action to show the recorded audit entry,
    or when a rep asks "what has been done to this license?"

    Requires a CS actor identity — the audit trail is not customer-visible.
    """
    session = get_session()
    try:
        try:
            actor = resolve_actor(session)
        except IdentityError as e:
            return {"error": str(e)}
        history = query_audit_history(session, license_id, limit=max(1, min(limit, 50)))
        return {**history, "requested_by": f"{actor['email']} ({actor['role']})"}
    except Exception:
        return {"error": "An unexpected error occurred retrieving audit history."}
    finally:
        session.close()
