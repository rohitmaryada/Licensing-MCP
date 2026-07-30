"""
The CS write executor — every write tool funnels through execute_cs_write().

This module is the proposal's "Tool Router" box made concrete:

    resolve identity → permission gate → mutate → audit → commit (atomic)

Why one shared executor instead of repeating the steps in each tool?
  1. The security-critical sequence lives in ONE reviewed place. A new write
     tool cannot forget the role check or the audit write.
  2. Atomicity: mutation and audit share a session; one commit covers both.
     A failed audit write rolls the mutation back — an unaudited write is
     structurally impossible.
  3. Rejections and failures are audited too. A CS-L1 probing an L3 tool is
     a security signal, not just an error.

The tool layer passes a `mutate` closure: (session) → (before, after, result).
Everything else — identity, gating, audit, commit, error shaping — is here.
"""

from typing import Callable

from sqlalchemy.orm import Session

from licensing_mcp.data_access.audit import write_audit
from licensing_mcp.database import get_cs_session, get_session
from licensing_mcp.identity import (
    IdentityError,
    has_permission,
    minimum_role_for,
    resolve_actor,
)


def execute_cs_write(
    tool_name: str,
    reason: str,
    mutate: Callable[[Session], tuple[dict, dict, dict]],
    target_license_id: str | None = None,
    target_user_email: str | None = None,
    target_product_name: str | None = None,
    args: dict | None = None,
) -> dict:
    """
    Run one CS write operation under the full identity → gate → audit pipeline.

    Returns a structured dict in every case (success, rejection, failure) —
    never raises to the tool layer, never leaks a stack trace to the agent.
    """
    if not reason or not reason.strip():
        # No identity needed to reject this — but nothing to audit either,
        # since an empty reason means the protocol contract wasn't met.
        return {
            "error": (
                "A non-empty 'reason' is required for every write action. "
                "State the business justification — it becomes the audit record."
            )
        }

    # The DATA mutation runs against whatever backend is configured (a SQLite
    # Session, or a ServiceClient making HTTP calls). Identity/gate/audit ALWAYS
    # run on the SQLite CS store (cs_* tables are MCP-owned, not in the services).
    data_backend = get_session()
    services_mode = getattr(data_backend, "backend", "sqlite") == "services"
    # sqlite mode: reuse the single session for mutation + audit (one atomic txn,
    # as before). services mode: a separate SQLite session for gate/audit while
    # the mutation is an HTTP call — mutate-then-audit (NOT one transaction; a POC
    # relaxation, prod would use a dedicated audit service / outbox).
    cs_session = get_cs_session() if services_mode else data_backend

    try:
        # ── 1. Identity ───────────────────────────────────────────────────
        try:
            actor = resolve_actor(cs_session)
        except IdentityError as e:
            return {"error": str(e)}

        # ── 2. Permission gate ────────────────────────────────────────────
        if not has_permission(cs_session, actor, tool_name):
            required = minimum_role_for(cs_session, tool_name)
            audit_id = write_audit(
                cs_session, actor, tool_name, reason, outcome="rejected",
                target_license_id=target_license_id,
                target_user_email=target_user_email,
                target_product_name=target_product_name,
                args=args,
            )
            cs_session.commit()  # the rejection record IS the transaction (no mutation ran)
            return {
                "error": (
                    f"Permission denied: {actor['email']} holds role "
                    f"{actor['role']}, but {tool_name} requires {required or 'a higher role'}. "
                    f"This attempt has been logged ({audit_id}). "
                    f"Escalate to a {required} representative."
                ),
                "audit_id": audit_id,
            }

        # ── 3. Mutation (backend-dependent: SQL or HTTP) ──────────────────
        try:
            before, after, result = mutate(data_backend)
        except ValueError as e:
            audit_id = write_audit(
                cs_session, actor, tool_name, reason, outcome="failure",
                target_license_id=target_license_id,
                target_user_email=target_user_email,
                target_product_name=target_product_name,
                args=args,
            )
            cs_session.commit()
            return {"error": str(e), "audit_id": audit_id}

        # ── 4. Audit + 5. Commit ──────────────────────────────────────────
        # sqlite mode: this commit covers mutation + audit atomically.
        # services mode: the mutation already committed service-side; this commits
        # the audit record (mutate-then-audit).
        audit_id = write_audit(
            cs_session, actor, tool_name, reason, outcome="success",
            target_license_id=result.get("license_id", target_license_id),
            target_user_email=target_user_email,
            target_product_name=target_product_name,
            args=args,
            before_state=before,
            after_state=after,
        )
        cs_session.commit()

        return {
            **result,
            "audit_id": audit_id,
            "performed_by": f"{actor['email']} ({actor['role']})",
            "before_state": before,
            "after_state": after,
        }

    except Exception:
        cs_session.rollback()  # rolls back audit (SQLite); an HTTP mutation cannot be undone
        return {"error": f"An unexpected error occurred executing {tool_name}."}
    finally:
        cs_session.close()
        if data_backend is not cs_session:
            data_backend.close()
