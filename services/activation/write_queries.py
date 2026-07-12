"""Activation service write queries (B2-WRITES-PLAN.md §4, W6/W7).

Both mutate the `activation` row only. Contract: `(session, ...) -> (before, after)`
mappings, ready for `row_to_activation_state`. Callers `session.commit()`
after — these functions only `flush()`.
"""

import sqlalchemy as sa

from services.activation.queries import get_activation
from services.shared.errors import ConflictError, NotFoundError
from services.shared.tables import activation, activation_status_enum, policy


def revoke_activation(session, activation_id: int):
    before = get_activation(session, activation_id)
    if before is None:
        raise NotFoundError(detail=f"activation {activation_id} not found")

    session.execute(
        sa.update(activation)
        .where(activation.c.id == activation_id)
        .values(status=sa.cast("inactive", activation_status_enum))
    )
    session.flush()
    after = get_activation(session, activation_id)
    return before, after


def reset_activation(session, activation_id: int):
    before = get_activation(session, activation_id)
    if before is None:
        raise NotFoundError(detail=f"activation {activation_id} not found")

    limit_row = session.execute(
        sa.select(policy.c.reactivation_limit).where(policy.c.entitlement_id == before["entitlement_id"])
    ).first()
    reactivation_limit = limit_row[0] if limit_row else 0
    if reactivation_limit <= 0:
        raise ConflictError(detail="reactivation limit exhausted for this entitlement's policy")

    session.execute(
        sa.update(activation)
        .where(activation.c.id == activation_id)
        .values(status=sa.cast("active", activation_status_enum), last_heartbeat=sa.func.now())
    )
    session.flush()
    after = get_activation(session, activation_id)
    return before, after
