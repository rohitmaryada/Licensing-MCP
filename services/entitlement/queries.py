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


def search_users(session, q: str, page, company: str | None = None):
    """find_user — fuzzy search users by name OR email, joined to entity for
    disambiguation (email + company). Substring ILIKE is served by the pg_trgm
    GIN indexes on app_user; results ordered by name similarity to the query.
    Optional `company` narrows by the user's entity name — the standard way to
    disambiguate common names."""
    full_name = app_user.c.first_name + " " + app_user.c.last_name
    pattern = f"%{q}%"
    conds = sa.or_(full_name.ilike(pattern), app_user.c.email.ilike(pattern))
    if company:
        conds = sa.and_(conds, entity.c.name.ilike(f"%{company}%"))
    j = app_user.join(entity, entity.c.id == app_user.c.entity_id)
    cols = [
        app_user.c.id,
        app_user.c.email,
        app_user.c.first_name,
        app_user.c.last_name,
        app_user.c.entity_id,
        entity.c.name.label("entity_name"),
    ]
    stmt = (
        sa.select(*cols)
        .select_from(j)
        .where(conds)
        .order_by(sa.func.similarity(full_name, q).desc(), app_user.c.id)
    )
    total = session.execute(sa.select(sa.func.count()).select_from(j).where(conds)).scalar_one()
    rows = session.execute(stmt.limit(page.size).offset(page.page * page.size)).mappings().all()
    return rows, total


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


def get_entitlement_core(session, entitlement_id: int):
    """Backs the single-entitlement GET. assignment_role/assigned_date are
    per-user (entitlement_person) fields with no meaning outside a user
    context, so they're left absent here — the route fills them as None."""
    stmt = sa.select(*_entitlement_cols()).select_from(_entitlement_join()).where(
        entitlement.c.id == entitlement_id
    )
    return session.execute(stmt).mappings().first()


def list_entitlement_people(session, entitlement_id: int, page):
    j = entitlement_person.join(app_user, app_user.c.id == entitlement_person.c.user_id)
    conds = (entitlement_person.c.entitlement_id == entitlement_id,)
    cols = [
        entitlement_person.c.id,
        entitlement_person.c.entitlement_id,
        entitlement_person.c.user_id,
        app_user.c.email.label("user_email"),
        entitlement_person.c.role,
        entitlement_person.c.added_date,
        entitlement_person.c.status,
    ]
    stmt = sa.select(*cols).select_from(j).where(*conds).order_by(entitlement_person.c.id)
    total = session.execute(sa.select(sa.func.count()).select_from(j).where(*conds)).scalar_one()
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
