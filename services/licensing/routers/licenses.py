"""L6b, L7, L8, W2, W3 — /licensing/v1/licenses/*"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from services.licensing.queries import (
    get_end_user_count,
    get_license_core,
    get_license_id_by_ref,
    get_license_products_all,
    get_license_products_page,
    get_licensee,
    get_master_license_id_for_license,
    get_master_license_summary,
    list_master_administrators,
)
from services.licensing.write_queries import add_user_to_license, extend_license_expiry
from services.shared.auth import require_service_auth
from services.shared.db import get_session
from services.shared.dto import (
    Administrator,
    AddEndUserRequest,
    EndUser,
    ExtendExpiryRequest,
    License,
    LicenseSummary,
    LicensedProduct,
)
from services.shared.errors import NotFoundError
from services.shared.mappers import (
    build_license,
    row_to_administrator,
    row_to_end_user,
    row_to_license_summary,
    row_to_licensed_product,
    row_to_licensee_summary,
    row_to_master_license_summary,
)
from services.shared.schemas import Change, Page, PageParams, build_page

router = APIRouter(prefix="/licensing/v1/licenses", dependencies=[Depends(require_service_auth)])


@router.get("/{license_id}/administrators", response_model=list[Administrator])
def get_license_administrators_route(license_id: int, session: Session = Depends(get_session)):
    # Server resolves license -> master_license_id -> admins: one call for the caller.
    ml_id = get_master_license_id_for_license(session, license_id)
    if ml_id is None:
        raise NotFoundError(detail=f"license {license_id} not found")
    return [row_to_administrator(r) for r in list_master_administrators(session, ml_id)]


def _license_composite(session, license_id: int) -> License:
    """Assemble the full License snapshot (master + licensee + products + end-user
    count). Shared by the id route and the ref-addressable route below."""
    lic_row = get_license_core(session, license_id)
    if lic_row is None:
        raise NotFoundError(detail=f"license {license_id} not found")

    master_row = get_master_license_summary(session, lic_row["master_license_id"])
    licensee_row = get_licensee(session, master_row["entity_id"])
    products_rows = get_license_products_all(session, license_id)
    end_user_count = get_end_user_count(session, license_id)

    return build_license(
        lic_row,
        master=row_to_master_license_summary(master_row),
        licensee=row_to_licensee_summary(licensee_row),
        products=[row_to_licensed_product(r) for r in products_rows],
        end_user_count=end_user_count,
    )


@router.get("", response_model=License)
def get_license_by_ref_route(ref: str, session: Session = Depends(get_session)):
    """Address a license by its public business key (license_ref, e.g. 'L-DEMOACME')
    rather than the internal surrogate id — so ref-based callers (the MCP tools)
    never handle surrogate keys. Returns the same composite as GET /licenses/{id}."""
    license_id = get_license_id_by_ref(session, ref)
    if license_id is None:
        raise NotFoundError(detail=f"license ref '{ref}' not found")
    return _license_composite(session, license_id)


@router.get("/{license_id}", response_model=License)
def get_license_status_route(license_id: int, session: Session = Depends(get_session)):
    return _license_composite(session, license_id)


@router.get("/{license_id}/products", response_model=Page[LicensedProduct])
def get_license_products_route(
    license_id: int, page: PageParams = Depends(), session: Session = Depends(get_session)
):
    rows, total = get_license_products_page(session, license_id, page)
    items = [row_to_licensed_product(r) for r in rows]
    return build_page(items, total, page)


@router.patch("/{license_id}", response_model=Change[LicenseSummary])
def extend_license_expiry_route(
    license_id: int, body: ExtendExpiryRequest, session: Session = Depends(get_session)
):
    before, after = extend_license_expiry(session, license_id, body.expiry_date)
    session.commit()
    return Change[LicenseSummary](
        before=row_to_license_summary(before), after=row_to_license_summary(after)
    )


@router.post("/{license_id}/end-users", response_model=EndUser)
def add_end_user_route(
    license_id: int, body: AddEndUserRequest, session: Session = Depends(get_session)
):
    row, _entitlement_count = add_user_to_license(session, license_id, body.user_email)
    session.commit()
    return row_to_end_user(row)
