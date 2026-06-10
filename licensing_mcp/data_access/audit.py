"""
Audit log writer and reader.

The audit writer is called inside the SAME session/transaction as the
mutation it records (see cs_executor.py). It deliberately does NOT commit:
the executor commits mutation + audit atomically. If either fails, both
roll back — an unaudited write is structurally impossible.

Production equivalent: an append-only, compliance-grade store (separate
from application data, not writable by the actor). POC keeps it in the
same SQLite file for queryability during demos.
"""

import json
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from licensing_mcp.models import CSAuditLog, CSUser


def _next_audit_id(session: Session) -> str:
    """AUD-NNNNN, continuing after the seeded records (AUD-02000)."""
    max_pk = session.query(func.max(CSAuditLog.id)).scalar() or 0
    return f"AUD-{max_pk + 1:05d}"


def write_audit(
    session: Session,
    actor: dict,
    tool_name: str,
    reason: str,
    outcome: str,  # "success" | "failure" | "rejected"
    target_license_id: str | None = None,
    target_user_email: str | None = None,
    target_product_name: str | None = None,
    args: dict | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
) -> str:
    """Append one audit record. Returns the audit_id. Does NOT commit."""
    audit_id = _next_audit_id(session)
    session.add(CSAuditLog(
        audit_id=audit_id,
        timestamp=datetime.now(),
        cs_actor_id=actor["id"],
        cs_role=actor["role"],
        action=tool_name,
        tool_name=tool_name,
        target_user_email=target_user_email,
        target_license_id=target_license_id,
        target_product_name=target_product_name,
        args_json=json.dumps(args) if args else None,
        reason=reason,
        outcome=outcome,
        before_state_json=json.dumps(before_state) if before_state else None,
        after_state_json=json.dumps(after_state) if after_state else None,
    ))
    return audit_id


def query_audit_history(session: Session, license_id: str, limit: int = 10) -> dict:
    """
    Most recent audit entries for a license, newest first.

    Production equivalent:
        GET /audit-service/v1/licenses/{license_id}/history?limit=N
    """
    rows = (
        session.query(CSAuditLog, CSUser)
        .join(CSUser, CSAuditLog.cs_actor_id == CSUser.id)
        .filter(CSAuditLog.target_license_id == license_id)
        .order_by(CSAuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )

    entries = []
    for log, actor in rows:
        entries.append({
            "audit_id": log.audit_id,
            "timestamp": log.timestamp.isoformat(),
            "actor_email": actor.email,
            "actor_role": log.cs_role,
            "action": log.action,
            "target_user_email": log.target_user_email,
            "target_product": log.target_product_name,
            "reason": log.reason,
            "outcome": log.outcome,
            "before_state": json.loads(log.before_state_json) if log.before_state_json else None,
            "after_state": json.loads(log.after_state_json) if log.after_state_json else None,
        })

    return {
        "license_id": license_id,
        "entries_returned": len(entries),
        "entries": entries,
    }
