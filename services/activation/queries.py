"""Activation service queries (B2-READS-PLAN.md §5, extended to the
CONTRACTS.md general-purpose filter + single-lookup reads).

`days_since_heartbeat` is computed in SQL (not Python) so it isn't subject to
app-server/DB clock skew. It's always computed on the list endpoint, whether
or not a caller filters by `staleDays` — it's just informational otherwise.
"""

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from services.shared.tables import activation, app_user


def _days_since_heartbeat_col():
    return (
        sa.func.extract("day", sa.func.now() - activation.c.last_heartbeat)
        .cast(sa.Integer)
        .label("days_since_heartbeat")
    )


def _activation_list_cols():
    return [
        activation.c.id,
        activation.c.entitlement_id,
        activation.c.user_id,
        app_user.c.email.label("user_email"),
        activation.c.machine_id,
        activation.c.machine_name,
        activation.c.os,
        activation.c.activation_date,
        activation.c.last_heartbeat,
        activation.c.status,
        _days_since_heartbeat_col(),
    ]


def list_activations(
    session,
    *,
    entitlement_id: int | None,
    user_email: str | None,
    status: str | None,
    stale_days: int | None,
    page,
):
    """General-purpose filtered list — CONTRACTS.md's
    `GET /activations?userEmail=&entitlementId=&status=&staleDays=`. Also
    backs the internal E1 cross-service call (entitlementId + staleDays).
    Caller must supply >=1 of entitlement_id/user_email (enforced at the
    route) — status/staleDays alone would be an unindexed full scan.
    """
    j = activation.join(app_user, app_user.c.id == activation.c.user_id)
    conds = []
    if entitlement_id is not None:
        conds.append(activation.c.entitlement_id == entitlement_id)
    if user_email is not None:
        conds.append(app_user.c.email == user_email)
    if status is not None:
        # cast: activation.status is a Postgres-native enum; comparing it
        # directly to a plain string bind param fails (enum = varchar has no operator).
        conds.append(sa.cast(activation.c.status, sa.Text) == status)
    if stale_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
        conds.append(activation.c.last_heartbeat < cutoff)

    stmt = sa.select(*_activation_list_cols()).select_from(j).where(*conds).order_by(activation.c.id)
    total = session.execute(sa.select(sa.func.count()).select_from(j).where(*conds)).scalar_one()
    rows = session.execute(stmt.limit(page.size).offset(page.page * page.size)).mappings().all()
    return rows, total


def get_activation(session, activation_id: int):
    """Single-activation lookup — CONTRACTS.md's `GET /activations/{id}`."""
    stmt = (
        sa.select(
            activation.c.id,
            activation.c.entitlement_id,
            activation.c.user_id,
            app_user.c.email.label("user_email"),
            activation.c.machine_id,
            activation.c.machine_name,
            activation.c.os,
            activation.c.activation_date,
            activation.c.last_heartbeat,
            activation.c.status,
        )
        .select_from(activation.join(app_user, app_user.c.id == activation.c.user_id))
        .where(activation.c.id == activation_id)
    )
    return session.execute(stmt).mappings().first()
