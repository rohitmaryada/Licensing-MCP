"""
License and entitlement query functions.

Each function is the POC stand-in for a microservice call:
  query_license_status()         → GET /licensing-service/v1/licenses/{id}
  query_license_products()       → GET /licensing-service/v1/licenses/{id}/products
  query_license_administrators() → GET /licensing-service/v1/licenses/{id}/admins
  query_check_user_entitlements() → GET /entitlement-service/v1/users/{email}/entitlements
  query_list_licenses_by_entity() → GET /licensing-service/v1/entities/search?name=...
  query_search_entitlements()    → GET /entitlement-service/v1/entitlements/search

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
    Activation,
    Entity,
    EntityType,
    Entitlement,
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


# ── Tool: get_license_status ─────────────────────────────────────────────────

def query_license_status(license_id: str, session: Session) -> dict:
    """
    Return the health snapshot for a license: status, seat utilization, expiry.

    Intentionally excludes the product catalog — use query_license_products for that.
    This function answers "is this license active and how full is it?" in one call.

    Raises ValueError if the license_id is not found.

    Production equivalent:
        GET /licensing-service/v1/licenses/{license_id}
        Headers: Authorization: Bearer {service_token}
    """
    if hasattr(session, "get_license_by_ref"):
        return _license_status_via_services(session, license_id)

    license = (
        session.query(License)
        .join(Entity, License.entity_id == Entity.id)
        .join(LicenseType, License.license_type_id == LicenseType.id)
        .filter(License.id == license_id)
        .first()
    )

    if not license:
        raise ValueError(f"License '{license_id}' not found.")

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
    }


# ── C1 adapters: real Licensing service (address-by-ref) → flat tool shapes ──
#
# Both get_license_status and get_license_products are served by ONE composite:
#   GET /licensing/v1/licenses?ref={ref}  (ref = business key; surrogate id stays
#   internal). Reconciliation decisions (flagged): license-level seat_count :=
#   SUM of per-product seatCount; seats_used := endUserCount; license_type := None
#   (no deep equivalent); product category/base_price := None (not on the service
#   DTO). These are the same flat/deep reconciliations documented in CONTRACTS §8.
def _flat_license_fields(comp: dict) -> dict:
    seat_count = sum(p.get("seatCount", 0) for p in comp.get("products", []))
    seats_used = comp.get("endUserCount", 0)
    return {
        "license_id": comp["licenseRef"],
        "entity_name": (comp.get("licensee") or {}).get("name"),
        "entity_type": (comp.get("licensee") or {}).get("entityType"),
        "license_type": None,
        "status": comp["status"],
        "seat_count": seat_count,
        "seats_used": seats_used,
        "seat_utilization": f"{seats_used}/{seat_count}",
        "utilization_pct": round((seats_used / seat_count * 100) if seat_count else 0),
        "start_date": comp.get("startDate"),
        "expiry_date": comp["expiryDate"],
        "days_until_expiry": comp["daysUntilExpiry"],
    }


def _license_status_via_services(client, license_ref: str) -> dict:
    return _flat_license_fields(client.get_license_by_ref(license_ref))


def _license_products_via_services(client, license_ref: str) -> dict:
    comp = client.get_license_by_ref(license_ref)
    result = _flat_license_fields(comp)
    products = comp.get("products", [])
    result["product_count"] = len(products)
    result["products"] = [
        {
            "name": p["productName"],
            "product_code": p["productCode"],
            "category": None,          # not carried on the service LicensedProduct DTO
            "base_price_usd": None,
        }
        for p in sorted(products, key=lambda p: p["productName"])
    ]
    return result


# ── Tool: check_user_entitlements ────────────────────────────────────────────

def query_check_user_entitlements(user_email: str, session: Session) -> dict:
    """
    Return all products a user is entitled to, grouped by license, with
    per-product activation state (active / inactive / never_activated).

    Key design decisions:
    - Grouped by license: a user can hold seats on multiple licenses
    - All activations returned, not just the latest: surfaces stale ones
    - activation_state summary at the entitlement level for quick scanning;
      full activation detail (machine_id, heartbeat, days) in activations list

    Raises ValueError if the email is not found.

    Production equivalent:
        GET /entitlement-service/v1/users/{email}/entitlements
        Headers: Authorization: Bearer {service_token}
    """
    # C1: services backend — map the real Entitlement service response to this shape.
    if hasattr(session, "get_user_entitlements"):
        return _check_user_entitlements_via_services(session, user_email)

    user = session.query(User).filter(User.email == user_email).first()
    if not user:
        raise ValueError(f"User '{user_email}' not found.")

    # All entitlements with their product and license info in one query
    rows = (
        session.query(Entitlement, Product, License, LicenseType)
        .join(Product, Entitlement.product_id == Product.id)
        .join(License, Entitlement.license_id == License.id)
        .join(LicenseType, License.license_type_id == LicenseType.id)
        .filter(Entitlement.user_id == user.id)
        .order_by(Entitlement.license_id, Product.name)
        .all()
    )

    if not rows:
        return {
            "user_email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "entity_name": user.entity.name,
            "total_entitlements": 0,
            "licenses": [],
        }

    # Pull all activations for this user up front — avoids N+1 per entitlement
    activations = (
        session.query(Activation)
        .filter(Activation.user_id == user.id)
        .all()
    )
    # Index by (product_id, license_id) → list[Activation]
    activation_map: dict[tuple[int, str], list] = {}
    for act in activations:
        activation_map.setdefault((act.product_id, act.license_id), []).append(act)

    # Group entitlements by license
    license_map: dict[str, dict] = {}
    for ent, product, license, license_type in rows:
        if ent.license_id not in license_map:
            license_map[ent.license_id] = {
                "license_id": license.id,
                "license_type": license_type.name,
                "license_status": license.status,
                "entitlements": [],
            }

        acts = activation_map.get((product.id, license.id), [])

        if not acts:
            activation_state = "never_activated"
        elif any(a.status == "active" for a in acts):
            activation_state = "active"
        else:
            activation_state = "inactive"

        activation_details = [
            {
                "machine_id": a.machine_id,
                "status": a.status,
                "last_heartbeat": a.last_heartbeat.isoformat(),
                "days_since_heartbeat": (datetime.utcnow() - a.last_heartbeat).days,
            }
            for a in sorted(acts, key=lambda a: a.last_heartbeat, reverse=True)
        ]

        license_map[ent.license_id]["entitlements"].append({
            "product_name": product.name,
            "product_code": product.product_code,
            "entitlement_status": ent.status,
            "activation_state": activation_state,
            "activations": activation_details,
        })

    return {
        "user_email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "entity_name": user.entity.name,
        "total_entitlements": len(rows),
        "licenses": list(license_map.values()),
    }


# ── C1 adapter: real Entitlement service → the flat check_user_entitlements shape
#
# Source: GET /entitlement/v1/users/{email}/entitlements?includeStaleActivations=true
# (services/ENDPOINTS.md). Reconciliation decisions (flagged for review):
#   * license_id  := licenseRef ("L-XXXXX", what the flat shape used)
#   * license_type / license_status := None — the user-entitlements endpoint
#     doesn't carry them (no deep equivalent for license_type; license status
#     isn't returned on this route)
#   * activation_state := "inactive" if the entitlement has stale activations,
#     else "active". NOTE: this endpoint returns only STALE activations (its
#     Story-2 purpose), so "never_activated" and non-stale "active" details
#     aren't distinguishable here without an Activation-service fan-out. The
#     stale ones — the ones that matter for diagnosis — are surfaced faithfully.
def _check_user_entitlements_via_services(client, user_email: str) -> dict:
    resp = client.get_user_entitlements(user_email, include_stale=True)
    user = resp["user"]

    license_map: dict[str, dict] = {}
    for item in resp.get("items", []):
        ref = item["licenseRef"]
        if ref not in license_map:
            license_map[ref] = {
                "license_id": ref,
                "license_type": None,
                "license_status": None,
                "entitlements": [],
            }
        stale = item.get("staleActivations") or []
        license_map[ref]["entitlements"].append({
            "product_name": item["productName"],
            "product_code": item["productCode"],
            "entitlement_status": item["status"],
            "activation_state": "inactive" if stale else "active",
            "activations": [
                {
                    "machine_id": a["machineId"],
                    "status": a["status"],
                    "last_heartbeat": a["lastHeartbeat"],
                    "days_since_heartbeat": a["daysSinceHeartbeat"],
                }
                for a in stale
            ],
        })

    return {
        "user_email": user["email"],
        "first_name": user["firstName"],
        "last_name": user["lastName"],
        "entity_name": user["entityName"],
        "total_entitlements": resp["pageInfo"]["totalElements"],
        "licenses": list(license_map.values()),
    }


# ── Tool: list_licenses_by_entity ────────────────────────────────────────────

_ENTITY_CAP = 20  # Max entities to return for a broad name match


def query_list_licenses_by_entity(entity_name: str, session: Session) -> dict:
    """
    Return all licenses belonging to entities whose name matches the query.

    Partial, case-insensitive match — "acme" finds "Acme Corp".
    Results are grouped by entity. Capped at 20 entities; if the query matches
    more the caller gets a truncation message and should narrow the name.

    Raises ValueError if no entity matches.

    Production equivalent:
        GET /licensing-service/v1/entities/search?name={entity_name}&include=licenses
        Headers: Authorization: Bearer {service_token}
    """
    entities = (
        session.query(Entity)
        .join(EntityType, Entity.entity_type_id == EntityType.id)
        .filter(func.lower(Entity.name).contains(entity_name.lower()))
        .order_by(Entity.name)
        .all()
    )

    if not entities:
        raise ValueError(f"No entities found matching '{entity_name}'.")

    truncated = len(entities) > _ENTITY_CAP
    entities_to_return = entities[:_ENTITY_CAP]

    result_entities = []
    for entity in entities_to_return:
        licenses = (
            session.query(License)
            .join(LicenseType, License.license_type_id == LicenseType.id)
            .filter(License.entity_id == entity.id)
            .order_by(License.expiry_date)
            .all()
        )

        license_list = []
        for lic in licenses:
            util = _seat_utilization(lic.id, lic.seat_count, session)
            product_count = (
                session.query(func.count(LicenseProduct.id))
                .filter(LicenseProduct.license_id == lic.id)
                .scalar()
                or 0
            )
            license_list.append({
                "license_id": lic.id,
                "license_type": lic.license_type.name,
                "status": lic.status,
                "seat_count": lic.seat_count,
                "seats_used": util["seats_used"],
                "seat_utilization": util["utilization_label"],
                "utilization_pct": util["utilization_pct"],
                "start_date": lic.start_date.isoformat(),
                "expiry_date": lic.expiry_date.isoformat(),
                "days_until_expiry": _days_until(lic.expiry_date),
                "product_count": product_count,
            })

        result_entities.append({
            "entity_name": entity.name,
            "entity_type": entity.entity_type.name,
            "industry": entity.industry,
            "country": entity.country,
            "license_count": len(licenses),
            "licenses": license_list,
        })

    result = {
        "query": entity_name,
        "entity_count": len(entities),
        "entities_returned": len(entities_to_return),
        "truncated": truncated,
        "entities": result_entities,
    }
    if truncated:
        result["message"] = (
            f"Query matched {len(entities)} entities — showing first {_ENTITY_CAP}. "
            "Use a more specific name to narrow results."
        )
    return result


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
    if hasattr(session, "get_license_by_ref"):
        return _license_products_via_services(session, license_id)

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
