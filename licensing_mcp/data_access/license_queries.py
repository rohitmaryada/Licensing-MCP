"""
License and entitlement query functions.

Each function is the POC stand-in for a microservice call:
  query_license_products()      → GET /licensing-service/v1/licenses/{id}/products
  query_license_administrators() → GET /licensing-service/v1/licenses/{id}/admins
  query_search_entitlements()   → GET /entitlement-service/v1/entitlements/search

In production:
  - Replace SQLAlchemy queries with authenticated httpx calls
  - Function signatures stay identical — tool handlers above don't change
  - Move connection/auth config to database.py (already isolated there)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from licensing_mcp.models import (
    Entity,
    EntityType,
    License,
    LicenseAdmin,
    LicenseProduct,
    LicenseType,
    LicenseUser,
    Product,
    User,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _days_until(d: date) -> int:
    """Days from today until date d. Negative means already expired."""
    return (d - date.today()).days


def _seat_utilization(license_id: str, seat_count: int, session: Session) -> dict:
    """
    Return seat utilization as both a ratio string and raw numbers.

    We count active LicenseUser rows rather than activations because a user
    occupies a seat even if they haven't activated yet — matching how
    MathWorks license servers count seats.
    """
    active_users = (
        session.query(func.count(LicenseUser.id))
        .filter(
            LicenseUser.license_id == license_id,
            LicenseUser.status == "active",
        )
        .scalar()
        or 0
    )
    return {
        "seats_used": active_users,
        "seat_count": seat_count,
        "utilization_label": f"{active_users}/{seat_count}",
        "utilization_pct": round((active_users / seat_count * 100) if seat_count else 0),
    }


# ── Tool 1: get_license_products ─────────────────────────────────────────────

def query_license_products(license_id: str, session: Session) -> dict:
    """
    Return the full product catalog assigned to a license, plus key metadata.

    Raises ValueError if the license_id is not found — tool layer converts
    this into a structured error response (never a stack trace to Claude).

    Production equivalent:
        GET /licensing-service/v1/licenses/{license_id}/products
        Headers: Authorization: Bearer {service_token}
    """
    # Single query with eager joins — avoids N+1 queries
    license = (
        session.query(License)
        .join(Entity, License.entity_id == Entity.id)
        .join(LicenseType, License.license_type_id == LicenseType.id)
        .filter(License.id == license_id)
        .first()
    )

    if not license:
        raise ValueError(f"License '{license_id}' not found.")

    # Fetch products via the junction table
    products = (
        session.query(Product)
        .join(LicenseProduct, Product.id == LicenseProduct.product_id)
        .filter(LicenseProduct.license_id == license_id)
        .order_by(Product.name)
        .all()
    )

    util = _seat_utilization(license_id, license.seat_count, session)

    return {
        "license_id": license.id,
        "entity_name": license.entity.name,
        "entity_type": license.entity.entity_type.name,
        "license_type": license.license_type.name,
        "status": license.status,
        "seat_count": license.seat_count,
        "seats_used": util["seats_used"],
        "seat_utilization": util["utilization_label"],
        "utilization_pct": util["utilization_pct"],
        "start_date": license.start_date.isoformat(),
        "expiry_date": license.expiry_date.isoformat(),
        "days_until_expiry": _days_until(license.expiry_date),
        "product_count": len(products),
        "products": [
            {
                "name": p.name,
                "product_code": p.product_code,
                "category": p.category,
                "base_price_usd": p.base_price,
            }
            for p in products
        ],
    }


# ── Tool 2: get_license_administrators ───────────────────────────────────────

def query_license_administrators(license_id: str, session: Session) -> dict:
    """
    Return the administrators who manage a license.

    Raises ValueError if the license_id is not found.

    Production equivalent:
        GET /licensing-service/v1/licenses/{license_id}/admins
        Headers: Authorization: Bearer {service_token}
    """
    license = (
        session.query(License)
        .join(Entity, License.entity_id == Entity.id)
        .join(LicenseType, License.license_type_id == LicenseType.id)
        .filter(License.id == license_id)
        .first()
    )

    if not license:
        raise ValueError(f"License '{license_id}' not found.")

    # Join through the admin junction table to get user details
    admins = (
        session.query(User, LicenseAdmin.added_date)
        .join(LicenseAdmin, User.id == LicenseAdmin.user_id)
        .filter(LicenseAdmin.license_id == license_id)
        .order_by(User.last_name, User.first_name)
        .all()
    )

    return {
        "license_id": license.id,
        "entity_name": license.entity.name,
        "license_type": license.license_type.name,
        "status": license.status,
        "expiry_date": license.expiry_date.isoformat(),
        "administrator_count": len(admins),
        "administrators": [
            {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "admin_since": added_date.isoformat(),
            }
            for user, added_date in admins
        ],
    }


# ── Tool 3: search_entitlements ──────────────────────────────────────────────

def query_search_entitlements(
    session: Session,
    entity_name: Optional[str] = None,
    product_name: Optional[str] = None,
    license_status: Optional[str] = None,
    license_type: Optional[str] = None,
    expiring_within_days: Optional[int] = None,
    min_seat_utilization_pct: Optional[int] = None,
) -> tuple[list[dict], int]:
    """
    Filtered search across licenses and entitlements.

    All filters are optional — at least one should be provided.
    Returns (results, total_count). The caller uses total_count to decide
    whether to elicit further narrowing from the user before returning results.

    Production equivalent:
        GET /entitlement-service/v1/entitlements/search?entity_name=...&product=...
        Headers: Authorization: Bearer {service_token}

    SQLite note: true ILIKE isn't available, so we use func.lower() on both sides
    for case-insensitive matching. MS SQL Server LIKE is case-insensitive by default.
    """
    # Start with a base query joining all the tables we may need to filter on
    query = (
        session.query(License)
        .join(Entity, License.entity_id == Entity.id)
        .join(LicenseType, License.license_type_id == LicenseType.id)
    )

    # ── Apply filters ─────────────────────────────────────────────────────────

    if entity_name:
        query = query.filter(
            func.lower(Entity.name).contains(entity_name.lower())
        )

    if product_name:
        # Subquery: license IDs that include this product
        matching_licenses = (
            session.query(LicenseProduct.license_id)
            .join(Product, LicenseProduct.product_id == Product.id)
            .filter(func.lower(Product.name).contains(product_name.lower()))
            .subquery()
        )
        query = query.filter(License.id.in_(select(matching_licenses)))

    if license_status:
        query = query.filter(License.status == license_status)

    if license_type:
        query = query.filter(
            func.lower(LicenseType.name) == license_type.lower()
        )

    if expiring_within_days is not None:
        today = date.today()
        cutoff = date(today.year, today.month, today.day)
        from datetime import timedelta
        future = today + timedelta(days=expiring_within_days)
        query = query.filter(
            License.expiry_date >= cutoff,
            License.expiry_date <= future,
        )

    if min_seat_utilization_pct is not None:
        # Subquery: count active users per license
        user_counts = (
            session.query(
                LicenseUser.license_id,
                func.count(LicenseUser.id).label("user_count"),
            )
            .filter(LicenseUser.status == "active")
            .group_by(LicenseUser.license_id)
            .subquery()
        )
        query = query.outerjoin(
            user_counts, License.id == user_counts.c.license_id
        ).filter(
            # utilization % = (user_count / seat_count) * 100 >= threshold
            func.coalesce(user_counts.c.user_count, 0) * 100
            >= License.seat_count * min_seat_utilization_pct
        )

    # ── Fetch results ─────────────────────────────────────────────────────────

    licenses = query.order_by(License.expiry_date).all()
    total_count = len(licenses)

    results = []
    for lic in licenses:
        util = _seat_utilization(lic.id, lic.seat_count, session)

        # Count products without loading them all
        product_count = (
            session.query(func.count(LicenseProduct.id))
            .filter(LicenseProduct.license_id == lic.id)
            .scalar()
            or 0
        )

        results.append(
            {
                "license_id": lic.id,
                "entity_name": lic.entity.name,
                "entity_type": lic.entity.entity_type.name,
                "industry": lic.entity.industry,
                "license_type": lic.license_type.name,
                "status": lic.status,
                "seat_count": lic.seat_count,
                "seats_used": util["seats_used"],
                "seat_utilization": util["utilization_label"],
                "utilization_pct": util["utilization_pct"],
                "expiry_date": lic.expiry_date.isoformat(),
                "days_until_expiry": _days_until(lic.expiry_date),
                "product_count": product_count,
            }
        )

    return results, total_count
