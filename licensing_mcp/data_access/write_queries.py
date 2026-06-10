"""
CS write operations — the mutation layer.

Contract shared by all six functions:
  - Signature: (session, ...domain args) → (before_state, after_state, result)
  - Domain failures raise ValueError with a message safe to show the agent
  - NO commits here — cs_executor.py commits mutation + audit atomically
  - before/after states are small dicts destined for the audit record

Production equivalents are authenticated POST/PATCH/DELETE calls to the
licensing/entitlement/activation microservices (see §5 of the security doc).
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from licensing_mcp.models import (
    Activation,
    Entitlement,
    Installation,
    License,
    LicenseAdmin,
    LicenseProduct,
    LicenseUser,
    Product,
    User,
)


def _license_or_raise(session: Session, license_id: str) -> License:
    lic = session.query(License).filter(License.id == license_id).first()
    if not lic:
        raise ValueError(f"License '{license_id}' not found.")
    return lic


def _user_or_raise(session: Session, email: str) -> User:
    user = session.query(User).filter(User.email == email).first()
    if not user:
        raise ValueError(f"User '{email}' not found.")
    return user


def _product_or_raise(session: Session, product_name: str) -> Product:
    product = (
        session.query(Product)
        .filter(func.lower(Product.name) == product_name.lower())
        .first()
    )
    if not product:
        raise ValueError(f"Product '{product_name}' not found.")
    return product


def _seats(session: Session, lic: License) -> dict:
    used = (
        session.query(func.count(LicenseUser.id))
        .filter(LicenseUser.license_id == lic.id, LicenseUser.status == "active")
        .scalar()
        or 0
    )
    return {"seat_utilization": f"{used}/{lic.seat_count}", "seats_used": used,
            "seat_count": lic.seat_count}


# ── CS-L1: add_user_to_license ───────────────────────────────────────────────

def apply_add_user_to_license(session: Session, license_id: str, user_email: str):
    lic = _license_or_raise(session, license_id)
    user = _user_or_raise(session, user_email)

    if lic.status not in ("active", "trial"):
        raise ValueError(f"License {license_id} is {lic.status} — cannot add users.")

    existing = (
        session.query(LicenseUser)
        .filter(LicenseUser.license_id == license_id, LicenseUser.user_id == user.id)
        .first()
    )
    if existing:
        raise ValueError(f"{user_email} is already on license {license_id}.")

    before = _seats(session, lic)
    if before["seats_used"] >= lic.seat_count:
        raise ValueError(
            f"License {license_id} is at capacity ({before['seat_utilization']}). "
            f"Free a seat first (revoke a stale activation or remove a user) "
            f"or increase the seat count."
        )

    session.add(LicenseUser(license_id=license_id, user_id=user.id,
                            added_date=date.today(), status="active"))
    # Membership grants entitlements to every product on the license —
    # same derivation rule the seed script uses.
    product_ids = [
        lp.product_id for lp in
        session.query(LicenseProduct).filter(LicenseProduct.license_id == license_id)
    ]
    for pid in product_ids:
        session.add(Entitlement(user_id=user.id, license_id=license_id,
                                product_id=pid, status="active",
                                granted_at=date.today()))
    session.flush()

    after = _seats(session, lic)
    result = {
        "message": f"Added {user_email} to {license_id} with {len(product_ids)} product entitlements.",
        "license_id": license_id,
        "user_email": user_email,
        "entitlements_granted": len(product_ids),
        "seat_utilization": after["seat_utilization"],
    }
    return before, after, result


# ── CS-L1: revoke_activation ─────────────────────────────────────────────────

def find_activation(session: Session, user_email: str, product_name: str,
                    machine_id: str) -> dict:
    """
    Read-only lookup used by the tool layer to build the elicitation
    confirmation BEFORE mutating anything.
    """
    user = _user_or_raise(session, user_email)
    product = _product_or_raise(session, product_name)
    act = (
        session.query(Activation)
        .filter(
            Activation.user_id == user.id,
            Activation.product_id == product.id,
            Activation.machine_id == machine_id,
        )
        .first()
    )
    if not act:
        raise ValueError(
            f"No activation of {product.name} by {user_email} on machine {machine_id}."
        )
    from datetime import datetime
    return {
        "user_email": user_email,
        "product_name": product.name,
        "machine_id": machine_id,
        "license_id": act.license_id,
        "activation_status": act.status,
        "activation_date": act.activation_date.isoformat(),
        "last_heartbeat": act.last_heartbeat.isoformat(),
        "days_since_heartbeat": (datetime.now() - act.last_heartbeat).days,
    }


def apply_revoke_activation(session: Session, user_email: str, product_name: str,
                             machine_id: str):
    user = _user_or_raise(session, user_email)
    product = _product_or_raise(session, product_name)
    act = (
        session.query(Activation)
        .filter(
            Activation.user_id == user.id,
            Activation.product_id == product.id,
            Activation.machine_id == machine_id,
        )
        .first()
    )
    if not act:
        raise ValueError(
            f"No activation of {product.name} by {user_email} on machine {machine_id}."
        )

    lic = _license_or_raise(session, act.license_id)
    from datetime import datetime
    before = {
        **_seats(session, lic),
        "activation_status": act.status,
        "machine_id": machine_id,
        "days_since_heartbeat": (datetime.now() - act.last_heartbeat).days,
    }

    # Revocation deletes the activation record — the activation slot is freed
    # and the user can activate on a new machine. (Reversible: the user simply
    # re-activates; no data is unrecoverable.)
    session.delete(act)
    session.flush()

    after = {**_seats(session, lic), "activation_status": "revoked",
             "machine_id": machine_id}
    result = {
        "message": (
            f"Revoked {product.name} activation for {user_email} on {machine_id}. "
            f"The activation slot is freed — the user can now activate on a new machine."
        ),
        "license_id": lic.id,
        "user_email": user_email,
        "product_name": product.name,
        "machine_id": machine_id,
    }
    return before, after, result


# ── CS-L2: reset_installation_slot ───────────────────────────────────────────

def apply_reset_installation_slot(session: Session, user_email: str,
                                   product_name: str, machine_id: str):
    user = _user_or_raise(session, user_email)
    product = _product_or_raise(session, product_name)
    inst = (
        session.query(Installation)
        .filter(
            Installation.user_id == user.id,
            Installation.product_id == product.id,
            Installation.machine_id == machine_id,
        )
        .first()
    )
    if not inst:
        raise ValueError(
            f"No installation record of {product.name} by {user_email} on {machine_id}."
        )

    before = {
        "machine_id": machine_id,
        "machine_name": inst.machine_name,
        "os": inst.os,
        "install_date": inst.install_date.isoformat(),
    }
    session.delete(inst)
    session.flush()
    after = {"machine_id": machine_id, "installation_record": "cleared"}

    result = {
        "message": (
            f"Cleared installation slot for {product.name} / {user_email} on "
            f"{machine_id}. The user can reinstall on a replacement machine."
        ),
        "user_email": user_email,
        "product_name": product.name,
        "machine_id": machine_id,
    }
    return before, after, result


# ── CS-L2: update_seat_count ─────────────────────────────────────────────────

def apply_update_seat_count(session: Session, license_id: str, new_seat_count: int):
    lic = _license_or_raise(session, license_id)

    if new_seat_count < 1:
        raise ValueError("Seat count must be at least 1.")

    seats = _seats(session, lic)
    if new_seat_count < seats["seats_used"]:
        raise ValueError(
            f"Cannot reduce {license_id} to {new_seat_count} seats — "
            f"{seats['seats_used']} seats are currently occupied. Remove users first."
        )

    before = {"seat_count": lic.seat_count, "seat_utilization": seats["seat_utilization"]}
    old_count = lic.seat_count
    lic.seat_count = new_seat_count
    session.flush()
    after = {"seat_count": new_seat_count,
             "seat_utilization": f"{seats['seats_used']}/{new_seat_count}"}

    delta = new_seat_count - old_count
    direction = "increased" if delta > 0 else "decreased"
    result = {
        "message": f"Seat count on {license_id} {direction} from {old_count} to {new_seat_count}.",
        "license_id": license_id,
        "old_seat_count": old_count,
        "new_seat_count": new_seat_count,
    }
    return before, after, result


# ── CS-L3: extend_license_expiry ─────────────────────────────────────────────

def apply_extend_license_expiry(session: Session, license_id: str, extension_days: int):
    lic = _license_or_raise(session, license_id)

    if not (1 <= extension_days <= 365):
        raise ValueError("Extension must be between 1 and 365 days.")

    before = {"expiry_date": lic.expiry_date.isoformat(), "status": lic.status}
    old_expiry = lic.expiry_date
    lic.expiry_date = old_expiry + timedelta(days=extension_days)
    # An expired license whose new expiry is in the future becomes active again.
    if lic.status == "expired" and lic.expiry_date >= date.today():
        lic.status = "active"
    session.flush()
    after = {"expiry_date": lic.expiry_date.isoformat(), "status": lic.status}

    result = {
        "message": (
            f"License {license_id} extended by {extension_days} days: "
            f"{old_expiry.isoformat()} → {lic.expiry_date.isoformat()}."
        ),
        "license_id": license_id,
        "extension_days": extension_days,
        "new_expiry_date": lic.expiry_date.isoformat(),
        "status": lic.status,
    }
    return before, after, result


# ── CS-L3: transfer_license_admin ────────────────────────────────────────────

def apply_transfer_license_admin(session: Session, license_id: str,
                                  from_email: str, to_email: str):
    lic = _license_or_raise(session, license_id)
    from_user = _user_or_raise(session, from_email)
    to_user = _user_or_raise(session, to_email)

    admin_row = (
        session.query(LicenseAdmin)
        .filter(LicenseAdmin.license_id == license_id,
                LicenseAdmin.user_id == from_user.id)
        .first()
    )
    if not admin_row:
        raise ValueError(f"{from_email} is not an administrator of {license_id}.")

    already_admin = (
        session.query(LicenseAdmin)
        .filter(LicenseAdmin.license_id == license_id,
                LicenseAdmin.user_id == to_user.id)
        .first()
    )
    if already_admin:
        raise ValueError(f"{to_email} is already an administrator of {license_id}.")

    # New admin must hold a seat on the license — admin rights without
    # membership would be unauditable access.
    membership = (
        session.query(LicenseUser)
        .filter(LicenseUser.license_id == license_id,
                LicenseUser.user_id == to_user.id,
                LicenseUser.status == "active")
        .first()
    )
    if not membership:
        raise ValueError(
            f"{to_email} is not an active user on {license_id}. "
            f"Add them to the license first (add_user_to_license)."
        )

    before = {"administrator": from_email}
    session.delete(admin_row)
    session.add(LicenseAdmin(license_id=license_id, user_id=to_user.id,
                             added_date=date.today()))
    session.flush()
    after = {"administrator": to_email}

    result = {
        "message": f"License {license_id} administration transferred: {from_email} → {to_email}.",
        "license_id": license_id,
        "previous_admin": from_email,
        "new_admin": to_email,
    }
    return before, after, result
