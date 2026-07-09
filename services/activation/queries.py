"""Activation service queries (B2-READS-PLAN.md §5 — internal-only this slice).

Only one query: activations for an entitlement, filtered to those past a
caller-supplied staleness window. `days_since_heartbeat` is computed in SQL
(not Python) so it isn't subject to app-server/DB clock skew.
"""

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from services.shared.tables import activation


def list_stale_activations(session, entitlement_id: int, stale_days: int, page):
    days_since = (
        sa.func.extract("day", sa.func.now() - activation.c.last_heartbeat)
        .cast(sa.Integer)
        .label("days_since_heartbeat")
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    conds = (activation.c.entitlement_id == entitlement_id, activation.c.last_heartbeat < cutoff)

    cols = [
        activation.c.id,
        activation.c.machine_id,
        activation.c.machine_name,
        activation.c.last_heartbeat,
        activation.c.status,
        days_since,
    ]
    stmt = sa.select(*cols).where(*conds).order_by(activation.c.id)
    total = session.execute(sa.select(sa.func.count()).select_from(activation).where(*conds)).scalar_one()
    rows = session.execute(stmt.limit(page.size).offset(page.page * page.size)).mappings().all()
    return rows, total
