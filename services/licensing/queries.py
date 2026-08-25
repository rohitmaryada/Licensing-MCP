"""Licensing service queries (B2-READS-PLAN.md §5).

L2, L3, L4, L5, L6, L6b, L7, L8. Each SELECT labels its columns to match a
DTO's field names 1:1 so services/shared/mappers.py can build DTOs directly.

`seatsActive` (L7/L8) is computed from license_end_user, per B2-READS-PLAN.md
§5's own wording — license_end_user is LICENSE-scoped, not per-product (the
schema has no per-product seat-usage table), so this is the same value on
every product row for a given license, not a true per-product figure. That's
a known simplification carried over from the plan, not something fixed here.
"""

import sqlalchemy as sa

from services.shared.tables import (
    app_user,
    entitlement,
    entity,
    license,
    license_end_user,
    license_product,
    master_license,
    master_license_admin,
    product,
)


def get_licensee(session, entity_id: int):
    stmt = sa.select(
        entity.c.id,
        entity.c.name,
        entity.c.entity_type,
        entity.c.industry,
        entity.c.country,
        entity.c.region,
        entity.c.external_ref,
        entity.c.created_at,
    ).where(entity.c.id == entity_id)
    return session.execute(stmt).mappings().first()


def search_entities(session, q: str, page):
    """Fuzzy search licensees/customers by name (pg_trgm GIN on entity.name),
    ordered by similarity. Backs list_licenses_by_entity / search_entitlements."""
    pattern = f"%{q}%"
    cond = entity.c.name.ilike(pattern)
    cols = [
        entity.c.id, entity.c.name, entity.c.entity_type, entity.c.industry,
        entity.c.country, entity.c.region, entity.c.external_ref, entity.c.created_at,
    ]
    stmt = (
        sa.select(*cols).where(cond)
        .order_by(sa.func.similarity(entity.c.name, q).desc(), entity.c.id)
    )
    total = session.execute(sa.select(sa.func.count()).select_from(entity).where(cond)).scalar_one()
    rows = session.execute(stmt.limit(page.size).offset(page.page * page.size)).mappings().all()
    return rows, total


def _license_summary_cols():
    return [
        license.c.id,
        license.c.license_ref,
        license.c.status,
        license.c.expiry_date,
        (license.c.expiry_date - sa.func.current_date()).label("days_until_expiry"),
        (
            sa.select(sa.func.count())
            .select_from(license_product)
            .where(license_product.c.license_id == license.c.id)
            .correlate(license)
            .scalar_subquery()
        ).label("product_count"),
    ]


def list_licenses_by_entity(session, entity_id: int, page):
    """L3 — flat license rows (+ owning master's id/ref/label), paginated at the
    license level. The router groups these by master_license_id afterward."""
    j = license.join(master_license, master_license.c.id == license.c.master_license_id)
    cols = _license_summary_cols() + [
        master_license.c.id.label("master_id"),
        master_license.c.master_license_ref,
        master_license.c.label,
    ]
    conds = (master_license.c.entity_id == entity_id,)
    stmt = sa.select(*cols).select_from(j).where(*conds).order_by(master_license.c.id, license.c.id)
    total = session.execute(sa.select(sa.func.count()).select_from(j).where(*conds)).scalar_one()
    rows = session.execute(stmt.limit(page.size).offset(page.page * page.size)).mappings().all()
    return rows, total


def get_master_license_summary(session, ml_id: int):
    stmt = sa.select(
        master_license.c.id,
        master_license.c.master_license_ref,
        master_license.c.label,
        master_license.c.entity_id,
        master_license.c.program,
        master_license.c.sponsor,
        master_license.c.created_at,
    ).where(master_license.c.id == ml_id)
    return session.execute(stmt).mappings().first()


def list_licenses_by_master(session, ml_id: int, page):
    """L5."""
    conds = (license.c.master_license_id == ml_id,)
    stmt = sa.select(*_license_summary_cols()).where(*conds).order_by(license.c.id)
    total = session.execute(sa.select(sa.func.count()).select_from(license).where(*conds)).scalar_one()
    rows = session.execute(stmt.limit(page.size).offset(page.page * page.size)).mappings().all()
    return rows, total


def list_unallocated_products(session, ml_id: int):
    """L4's unallocatedProducts — license_product rows held at master level,
    not yet assigned to a license (license_id IS NULL)."""
    stmt = (
        sa.select(
            license_product.c.id.label("license_product_id"),
            product.c.product_code,
            product.c.name.label("product_name"),
            license_product.c.seat_count,
            license_product.c.business_offering_id,
        )
        .select_from(license_product.join(product, product.c.id == license_product.c.product_id))
        .where(license_product.c.master_license_id == ml_id, license_product.c.license_id.is_(None))
        .order_by(license_product.c.id)
    )
    return session.execute(stmt).mappings().all()


def list_master_administrators(session, ml_id: int):
    """L6, and the target of L6b's license->master resolution."""
    stmt = (
        sa.select(
            master_license_admin.c.id,
            master_license_admin.c.master_license_id,
            master_license_admin.c.user_id,
            app_user.c.email.label("user_email"),
            master_license_admin.c.renewal_notifications,
            master_license_admin.c.added_date,
        )
        .select_from(master_license_admin.join(app_user, app_user.c.id == master_license_admin.c.user_id))
        .where(master_license_admin.c.master_license_id == ml_id)
        .order_by(master_license_admin.c.id)
    )
    return session.execute(stmt).mappings().all()


def get_master_license_id_for_license(session, license_id: int):
    """L6b — resolve license -> master_license_id server-side (one call for caller)."""
    stmt = sa.select(license.c.master_license_id).where(license.c.id == license_id)
    row = session.execute(stmt).first()
    return row[0] if row else None


def get_license_id_by_ref(session, license_ref: str):
    """Resolve a public license ref (business key, e.g. 'L-DEMOACME') to the
    internal surrogate id. The ref is the stable public identifier callers use;
    the integer id stays internal to joins and cross-service calls."""
    stmt = sa.select(license.c.id).where(license.c.license_ref == license_ref)
    row = session.execute(stmt).first()
    return row[0] if row else None


def get_license_core(session, license_id: int):
    """L7's own license fields (master/licensee/products assembled separately)."""
    stmt = sa.select(
        license.c.id,
        license.c.license_ref,
        license.c.status,
        license.c.start_date,
        license.c.expiry_date,
        (license.c.expiry_date - sa.func.current_date()).label("days_until_expiry"),
        license.c.master_license_id,
    ).where(license.c.id == license_id)
    return session.execute(stmt).mappings().first()


def _license_products_stmt(license_id: int):
    seats_active = (
        sa.select(sa.func.count(sa.func.distinct(license_end_user.c.user_id)))
        # cast: license_end_user.status is a Postgres-native enum; Postgres won't
        # implicitly compare enum = varchar against a plain string bind param.
        .where(
            license_end_user.c.license_id == license_id,
            sa.cast(license_end_user.c.status, sa.Text) == "active",
        )
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
    return sa.select(*cols).select_from(j).where(license_product.c.license_id == license_id).order_by(
        license_product.c.id
    )


def get_license_products_all(session, license_id: int):
    """L7's embedded products[] — a license's own product set, unpaginated (small: ~1-8)."""
    return session.execute(_license_products_stmt(license_id)).mappings().all()


def get_license_products_page(session, license_id: int, page):
    """L8 — same rows, paginated per convention."""
    stmt = _license_products_stmt(license_id)
    total = session.execute(
        sa.select(sa.func.count()).select_from(license_product).where(license_product.c.license_id == license_id)
    ).scalar_one()
    rows = session.execute(stmt.limit(page.size).offset(page.page * page.size)).mappings().all()
    return rows, total


def get_end_user_count(session, license_id: int):
    stmt = sa.select(sa.func.count(sa.func.distinct(license_end_user.c.user_id))).where(
        license_end_user.c.license_id == license_id
    )
    return session.execute(stmt).scalar_one()
