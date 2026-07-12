"""Licensing service write queries (B2-WRITES-PLAN.md §4, W1-W5).

Contract: `(session, ...args) -> (before, after)` mappings/DTOs for updates, or
a single row for creates. Each function only `flush()`es — callers commit.
Reuses the reads-slice query helpers (`_license_summary_cols`, active-end-user
counting) so before/after states are built the same way GETs already are.
"""

from datetime import date

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from services.licensing.queries import _license_summary_cols
from services.shared.errors import BadRequestError, ConflictError, NotFoundError
from services.shared.tables import (
    app_user,
    entitlement,
    entitlement_person,
    license,
    license_end_user,
    license_product,
    license_status_enum,
    master_license,
    master_license_admin,
    membership_status_enum,
    product,
)


def _active_end_user_count(session, license_id: int | None) -> int:
    if license_id is None:
        return 0
    stmt = sa.select(sa.func.count(sa.func.distinct(license_end_user.c.user_id))).where(
        license_end_user.c.license_id == license_id,
        sa.cast(license_end_user.c.status, sa.Text) == "active",
    )
    return session.execute(stmt).scalar_one()


# ── W1: update_seat_count ────────────────────────────────────────────────────


def _licensed_product_by_id_stmt(lp_id: int):
    seats_active = (
        sa.select(sa.func.count(sa.func.distinct(license_end_user.c.user_id)))
        .select_from(license_end_user)
        .where(
            license_end_user.c.license_id == license_product.c.license_id,
            sa.cast(license_end_user.c.status, sa.Text) == "active",
        )
        .correlate(license_product)
        .scalar_subquery()
    )
    entitlement_count = (
        sa.select(sa.func.count())
        .select_from(entitlement)
        .where(entitlement.c.license_product_id == license_product.c.id)
        .correlate(license_product)
        .scalar_subquery()
    )
    cols = [
        license_product.c.id.label("license_product_id"),
        product.c.product_code,
        product.c.name.label("product_name"),
        product.c.is_suite,
        license_product.c.seat_count,
        seats_active.label("seats_active"),
        license_product.c.business_offering_id,
        entitlement_count.label("entitlement_count"),
    ]
    j = license_product.join(product, product.c.id == license_product.c.product_id)
    return sa.select(*cols).select_from(j).where(license_product.c.id == lp_id)


def update_seat_count(session, lp_id: int, seat_count: int):
    if seat_count < 0:
        raise BadRequestError(detail="seatCount must be >= 0")

    lp_row = session.execute(
        sa.select(license_product.c.id, license_product.c.license_id).where(
            license_product.c.id == lp_id
        )
    ).mappings().first()
    if lp_row is None:
        raise NotFoundError(detail=f"license_product {lp_id} not found")

    before = session.execute(_licensed_product_by_id_stmt(lp_id)).mappings().first()

    active_count = _active_end_user_count(session, lp_row["license_id"])
    if seat_count < active_count:
        raise ConflictError(
            detail=f"seatCount {seat_count} is below active end-user count {active_count}"
        )

    session.execute(
        sa.update(license_product).where(license_product.c.id == lp_id).values(seat_count=seat_count)
    )
    session.flush()
    after = session.execute(_licensed_product_by_id_stmt(lp_id)).mappings().first()
    return before, after


# ── W2: extend_license_expiry ────────────────────────────────────────────────


def _license_summary_by_id_stmt(license_id: int):
    return sa.select(*_license_summary_cols()).where(license.c.id == license_id)


def extend_license_expiry(session, license_id: int, expiry_date: date):
    server_today = session.execute(sa.select(sa.func.current_date())).scalar_one()
    if expiry_date < server_today:
        raise BadRequestError(detail="expiryDate must not be in the past")

    before = session.execute(_license_summary_by_id_stmt(license_id)).mappings().first()
    if before is None:
        raise NotFoundError(detail=f"license {license_id} not found")

    new_status = "active" if before["status"] == "expired" else before["status"]
    session.execute(
        sa.update(license)
        .where(license.c.id == license_id)
        .values(expiry_date=expiry_date, status=sa.cast(new_status, license_status_enum))
    )
    session.flush()
    after = session.execute(_license_summary_by_id_stmt(license_id)).mappings().first()
    return before, after


# ── W3: add_user_to_license (Decision W-B — two tables, one txn) ────────────


def add_user_to_license(session, license_id: int, user_email: str):
    lic_row = session.execute(
        sa.select(license.c.id, license.c.status).where(license.c.id == license_id)
    ).mappings().first()
    if lic_row is None:
        raise NotFoundError(detail=f"license {license_id} not found")
    if lic_row["status"] not in ("active", "trial"):
        raise ConflictError(detail=f"license {license_id} is not active or trial (status={lic_row['status']})")

    user_row = session.execute(
        sa.select(app_user.c.id, app_user.c.email).where(app_user.c.email == user_email)
    ).mappings().first()
    if user_row is None:
        raise NotFoundError(detail=f"user {user_email} not found")
    user_id = user_row["id"]

    existing = session.execute(
        sa.select(license_end_user.c.id).where(
            license_end_user.c.license_id == license_id,
            license_end_user.c.user_id == user_id,
            sa.cast(license_end_user.c.status, sa.Text) == "active",
        )
    ).first()
    if existing is not None:
        raise ConflictError(detail=f"user {user_email} is already an active end-user of license {license_id}")

    seat_total = session.execute(
        sa.select(sa.func.coalesce(sa.func.sum(license_product.c.seat_count), 0)).where(
            license_product.c.license_id == license_id
        )
    ).scalar_one()
    active_count = _active_end_user_count(session, license_id)
    if active_count >= seat_total:
        raise ConflictError(detail=f"license {license_id} is at capacity ({active_count}/{seat_total})")

    result = session.execute(
        sa.insert(license_end_user)
        .values(
            license_id=license_id,
            user_id=user_id,
            added_date=sa.func.current_date(),
            status=sa.cast("active", membership_status_enum),
        )
        .returning(license_end_user.c.id)
    )
    new_id = result.scalar_one()

    entitlement_ids = session.execute(
        sa.select(entitlement.c.id).where(entitlement.c.license_id == license_id)
    ).scalars().all()
    for ent_id in entitlement_ids:
        session.execute(
            pg_insert(entitlement_person)
            .values(
                entitlement_id=ent_id,
                user_id=user_id,
                added_date=sa.func.current_date(),
                status=sa.cast("active", membership_status_enum),
            )
            .on_conflict_do_nothing(index_elements=["entitlement_id", "user_id"])
        )

    session.flush()
    row = session.execute(
        sa.select(
            license_end_user.c.id,
            license_end_user.c.license_id,
            license_end_user.c.user_id,
            app_user.c.email.label("user_email"),
            license_end_user.c.added_date,
            license_end_user.c.status,
        )
        .select_from(license_end_user.join(app_user, app_user.c.id == license_end_user.c.user_id))
        .where(license_end_user.c.id == new_id)
    ).mappings().first()
    return row, len(entitlement_ids)


# ── W4/W5: master license administrators ────────────────────────────────────


def _administrator_row(session, admin_id: int):
    stmt = (
        sa.select(
            master_license_admin.c.id,
            master_license_admin.c.master_license_id,
            master_license_admin.c.user_id,
            app_user.c.email.label("user_email"),
            master_license_admin.c.renewal_notifications,
            master_license_admin.c.added_date,
        )
        .select_from(
            master_license_admin.join(app_user, app_user.c.id == master_license_admin.c.user_id)
        )
        .where(master_license_admin.c.id == admin_id)
    )
    return session.execute(stmt).mappings().first()


def add_administrator(session, ml_id: int, user_email: str, renewal_notifications: bool):
    ml_row = session.execute(
        sa.select(master_license.c.id).where(master_license.c.id == ml_id)
    ).first()
    if ml_row is None:
        raise NotFoundError(detail=f"master license {ml_id} not found")

    user_row = session.execute(
        sa.select(app_user.c.id).where(app_user.c.email == user_email)
    ).first()
    if user_row is None:
        raise NotFoundError(detail=f"user {user_email} not found")
    user_id = user_row[0]

    existing = session.execute(
        sa.select(master_license_admin.c.id).where(
            master_license_admin.c.master_license_id == ml_id,
            master_license_admin.c.user_id == user_id,
        )
    ).first()
    if existing is not None:
        raise ConflictError(detail=f"user {user_email} is already an administrator of master license {ml_id}")

    result = session.execute(
        sa.insert(master_license_admin)
        .values(
            master_license_id=ml_id,
            user_id=user_id,
            renewal_notifications=renewal_notifications,
            added_date=sa.func.current_date(),
        )
        .returning(master_license_admin.c.id)
    )
    new_id = result.scalar_one()
    session.flush()
    return _administrator_row(session, new_id)


def remove_administrator(session, ml_id: int, user_id: int):
    existing = session.execute(
        sa.select(master_license_admin.c.id).where(
            master_license_admin.c.master_license_id == ml_id,
            master_license_admin.c.user_id == user_id,
        )
    ).first()
    if existing is None:
        raise NotFoundError(detail=f"user {user_id} is not an administrator of master license {ml_id}")

    session.execute(
        sa.delete(master_license_admin).where(
            master_license_admin.c.master_license_id == ml_id,
            master_license_admin.c.user_id == user_id,
        )
    )
    session.flush()
