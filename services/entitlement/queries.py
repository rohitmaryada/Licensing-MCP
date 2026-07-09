"""Entitlement service queries (B2-READS-PLAN.md §5).

E1 (check_user_entitlements, enriched) and E2 (natural graph query, Gap 1).
Each SELECT labels its columns to match the corresponding DTO's field names
1:1 so services/shared/mappers.py can build DTOs with `DTO(**row)`.
"""

import sqlalchemy as sa

from services.shared.tables import app_user, entity, entitlement, entitlement_person, license, master_license, policy, product


def get_user_context(session, email: str):
    """app_user joined to entity, for E1's `user` block (entityName)."""
    stmt = (
        sa.select(
            app_user.c.id,
            app_user.c.email,
            app_user.c.first_name,
            app_user.c.last_name,
            app_user.c.entity_id,
            entity.c.name.label("entity_name"),
        )
        .select_from(app_user.join(entity, entity.c.id == app_user.c.entity_id))
        .where(app_user.c.email == email)
    )
    return session.execute(stmt).mappings().first()


def _entitlement_cols():
    return [
        entitlement.c.id,
        entitlement.c.license_id,
        license.c.license_ref,
        entitlement.c.master_license_id,
        master_license.c.master_license_ref,
        entitlement.c.license_product_id,
        product.c.product_code,
        product.c.name.label("product_name"),
        entitlement.c.entitlement_type,
        entitlement.c.activation_type,
        entitlement.c.status,
    ]


def _entitlement_join():
    return (
        entitlement.join(license, license.c.id == entitlement.c.license_id)
        .join(master_license, master_license.c.id == entitlement.c.master_license_id)
        .join(product, product.c.id == entitlement.c.product_id)
    )


def list_user_entitlements(session, user_id: int, status: str | None, page):
    """E1's item rows — entitlement_person -> entitlement (+ assignment fields)."""
    j = entitlement_person.join(_entitlement_join(), entitlement_person.c.entitlement_id == entitlement.c.id)
    cols = _entitlement_cols() + [
        entitlement_person.c.role.label("assignment_role"),
        entitlement_person.c.added_date.label("assigned_date"),
    ]
    conds = [entitlement_person.c.user_id == user_id]
    if status is not None:
        # cast: entitlement.status is a Postgres-native enum; comparing it
        # directly to a plain string bind param fails (enum = varchar has no operator).
        conds.append(sa.cast(entitlement.c.status, sa.Text) == status)

    stmt = sa.select(*cols).select_from(j).where(*conds).order_by(entitlement.c.id)
    count_stmt = sa.select(sa.func.count()).select_from(j).where(*conds)
    total = session.execute(count_stmt).scalar_one()
    rows = session.execute(stmt.limit(page.size).offset(page.page * page.size)).mappings().all()
    return rows, total


def get_policy_for_entitlement(session, entitlement_id: int):
    stmt = sa.select(
        policy.c.id,
        policy.c.entitlement_id,
        policy.c.policy_name,
        policy.c.quantity,
        policy.c.max_activations,
        policy.c.activation_ttl_days,
        policy.c.allow_offline,
        policy.c.reactivation_limit,
    ).where(policy.c.entitlement_id == entitlement_id)
    return session.execute(stmt).mappings().first()


def list_entitlements(
    session,
    *,
    license_id: int | None,
    master_license_id: int | None,
    license_product_id: int | None,
    status: str | None,
    page,
):
    """E2 — natural graph query. Caller must supply >=1 filter (enforced at the route)."""
    j = _entitlement_join()
    conds = []
    if license_id is not None:
        conds.append(entitlement.c.license_id == license_id)
    if master_license_id is not None:
        conds.append(entitlement.c.master_license_id == master_license_id)
    if license_product_id is not None:
        conds.append(entitlement.c.license_product_id == license_product_id)
    if status is not None:
        # cast: entitlement.status is a Postgres-native enum; comparing it
        # directly to a plain string bind param fails (enum = varchar has no operator).
        conds.append(sa.cast(entitlement.c.status, sa.Text) == status)

    stmt = sa.select(*_entitlement_cols()).select_from(j).where(*conds).order_by(entitlement.c.id)
    count_stmt = sa.select(sa.func.count()).select_from(j).where(*conds)
    total = session.execute(count_stmt).scalar_one()
    rows = session.execute(stmt.limit(page.size).offset(page.page * page.size)).mappings().all()
    return rows, total
