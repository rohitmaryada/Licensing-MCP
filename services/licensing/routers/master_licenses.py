"""L4, L5, L6, W4, W5 — /licensing/v1/master-licenses/*"""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from services.licensing.queries import (
    get_licensee,
    get_master_license_summary,
    list_licenses_by_master,
    list_master_administrators,
    list_unallocated_products,
)
from services.licensing.write_queries import add_administrator, remove_administrator
from services.shared.auth import require_service_auth
from services.shared.db import get_session
from services.shared.dto import AddAdministratorRequest, Administrator, LicenseSummary, MasterLicense
from services.shared.errors import NotFoundError
from services.shared.mappers import (
    row_to_administrator,
    row_to_license_summary,
    row_to_licensee_summary,
    row_to_unallocated_product,
)
from services.shared.schemas import Page, PageParams, build_page

router = APIRouter(prefix="/licensing/v1/master-licenses", dependencies=[Depends(require_service_auth)])


@router.get("/{ml_id}", response_model=MasterLicense)
def get_master_license_route(
    ml_id: int,
    include: str | None = Query(
        default=None, description="comma-separated: licenses,administrators,licensee,unallocatedProducts"
    ),
    session: Session = Depends(get_session),
):
    row = get_master_license_summary(session, ml_id)
    if row is None:
        raise NotFoundError(detail=f"master license {ml_id} not found")

    wanted = set((include or "").split(",")) if include else set()
    licenses = administrators = licensee = unallocated_products = None

    if "licenses" in wanted:
        all_page = PageParams(page=0, size=100)
        lic_rows, _ = list_licenses_by_master(session, ml_id, all_page)
        licenses = [row_to_license_summary(r) for r in lic_rows]
    if "administrators" in wanted:
        administrators = [row_to_administrator(r) for r in list_master_administrators(session, ml_id)]
    if "licensee" in wanted:
        licensee_row = get_licensee(session, row["entity_id"])
        licensee = row_to_licensee_summary(licensee_row) if licensee_row else None
    if "unallocatedProducts" in wanted:
        unallocated_products = [
            row_to_unallocated_product(r) for r in list_unallocated_products(session, ml_id)
        ]

    return MasterLicense(
        **row,
        licenses=licenses,
        administrators=administrators,
        licensee=licensee,
        unallocated_products=unallocated_products,
    )


@router.get("/{ml_id}/licenses", response_model=Page[LicenseSummary])
def list_licenses_by_master_route(
    ml_id: int, page: PageParams = Depends(), session: Session = Depends(get_session)
):
    rows, total = list_licenses_by_master(session, ml_id, page)
    items = [row_to_license_summary(r) for r in rows]
    return build_page(items, total, page)


@router.get("/{ml_id}/administrators", response_model=list[Administrator])
def list_master_administrators_route(ml_id: int, session: Session = Depends(get_session)):
    return [row_to_administrator(r) for r in list_master_administrators(session, ml_id)]


@router.post("/{ml_id}/administrators", response_model=Administrator)
def add_administrator_route(
    ml_id: int, body: AddAdministratorRequest, session: Session = Depends(get_session)
):
    row = add_administrator(session, ml_id, body.user_email, body.renewal_notifications)
    session.commit()
    return row_to_administrator(row)


@router.delete("/{ml_id}/administrators/{user_id}", status_code=204)
def remove_administrator_route(
    ml_id: int, user_id: int, session: Session = Depends(get_session)
):
    remove_administrator(session, ml_id, user_id)
    session.commit()
    return Response(status_code=204)
