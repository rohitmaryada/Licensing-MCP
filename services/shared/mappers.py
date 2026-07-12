"""Row -> DTO mappers.

Each service's queries.py labels its SELECT columns to match a DTO's field
names 1:1 (including computed columns like days_until_expiry — computed in
SQL, not Python, to avoid clock-skew between the DB and app server). That
makes most mappers here thin `DTO(**row)` wrappers; the ones with real logic
assemble a composite DTO from several already-mapped pieces.
"""

from services.shared.dto import (
    Administrator,
    ActivationState,
    EndUser,
    Entitlement,
    EntitlementPerson,
    EntitlementSummary,
    License,
    LicenseSummary,
    LicensedProduct,
    Licensee,
    LicenseeSummary,
    MasterLicense,
    MasterLicenseSummary,
    Policy,
    StaleActivation,
    UnallocatedProduct,
    UserContext,
)


def row_to_licensee_summary(row) -> LicenseeSummary:
    return LicenseeSummary(**row)


def row_to_licensee(row) -> Licensee:
    return Licensee(**row)


def row_to_master_license_summary(row) -> MasterLicenseSummary:
    return MasterLicenseSummary(**row)


def row_to_license_summary(row) -> LicenseSummary:
    return LicenseSummary(**row)


def row_to_administrator(row) -> Administrator:
    return Administrator(**row)


def row_to_unallocated_product(row) -> UnallocatedProduct:
    return UnallocatedProduct(**row)


def row_to_licensed_product(row) -> LicensedProduct:
    return LicensedProduct(**row)


def row_to_stale_activation(row) -> StaleActivation:
    return StaleActivation(**row)


def row_to_user_context(row) -> UserContext:
    return UserContext(**row)


def row_to_entitlement_summary(row) -> EntitlementSummary:
    return EntitlementSummary(**row)


def row_to_entitlement_person(row) -> EntitlementPerson:
    return EntitlementPerson(**row)


def build_entitlement(row, policy_row, stale_rows, people_rows=None) -> Entitlement:
    """row: entitlement+license+master+product columns, aliased to Entitlement's
    flat fields. policy_row: one policy row or None. stale_rows: activation rows
    (only passed when includeStaleActivations=true). people_rows: entitlement_person
    rows, only passed when include=people on the single-entitlement GET."""
    policy = Policy(**policy_row) if policy_row is not None else None
    stale = [row_to_stale_activation(r) for r in stale_rows]
    people = [row_to_entitlement_person(r) for r in people_rows] if people_rows is not None else None
    return Entitlement(**row, policy=policy, stale_activations=stale, people=people)


def build_master_license(row, *, licenses=None, administrators=None, licensee=None, unallocated_products=None) -> MasterLicense:
    return MasterLicense(
        **row,
        licenses=licenses,
        administrators=administrators,
        licensee=licensee,
        unallocated_products=unallocated_products,
    )


def row_to_end_user(row) -> EndUser:
    return EndUser(**row)


def row_to_activation_state(row) -> ActivationState:
    return ActivationState(**row)


def build_license(row, *, master, licensee, products, end_user_count) -> License:
    # L7 always loads the license's full (unpaginated) product set, so
    # len(products) *is* productCount here — no separate count query needed.
    return License(
        **row, master=master, licensee=licensee, products=products,
        end_user_count=end_user_count, product_count=len(products),
    )
