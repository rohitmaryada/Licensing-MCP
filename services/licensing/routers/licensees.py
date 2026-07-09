"""L2, L3 — /licensing/v1/licensees/*"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from services.licensing.queries import get_licensee, list_licenses_by_entity
from services.shared.auth import require_service_auth
from services.shared.db import get_session
from services.shared.dto import Licensee, LicensesByEntityResponse, MasterLicenseGroup
from services.shared.errors import NotFoundError
from services.shared.mappers import row_to_license_summary, row_to_licensee
from services.shared.schemas import PageParams

router = APIRouter(prefix="/licensing/v1/licensees", dependencies=[Depends(require_service_auth)])


@router.get("/{entity_id}", response_model=Licensee)
def get_licensee_route(entity_id: int, session: Session = Depends(get_session)):
    row = get_licensee(session, entity_id)
    if row is None:
        raise NotFoundError(detail=f"licensee {entity_id} not found")
    return row_to_licensee(row)


@router.get("/{entity_id}/licenses", response_model=LicensesByEntityResponse)
def list_licenses_by_entity_route(
    entity_id: int, page: PageParams = Depends(), session: Session = Depends(get_session)
):
    licensee_row = get_licensee(session, entity_id)
    if licensee_row is None:
        raise NotFoundError(detail=f"licensee {entity_id} not found")

    rows, total = list_licenses_by_entity(session, entity_id, page)

    order: list[int] = []
    group_header: dict[int, dict] = {}
    group_licenses: dict[int, list] = {}
    for row in rows:
        mid = row["master_id"]
        if mid not in group_header:
            group_header[mid] = {"id": mid, "master_license_ref": row["master_license_ref"], "label": row["label"]}
            group_licenses[mid] = []
            order.append(mid)
        group_licenses[mid].append(row_to_license_summary(row))

    master_licenses = [
        MasterLicenseGroup(**group_header[mid], licenses=group_licenses[mid]) for mid in order
    ]

    return LicensesByEntityResponse(
        licensee_id=entity_id,
        licensee_name=licensee_row["name"],
        master_licenses=master_licenses,
        total_licenses=total,
    )
