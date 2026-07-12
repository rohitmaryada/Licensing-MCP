"""W1 — /licensing/v1/license-products/*"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from services.licensing.write_queries import update_seat_count
from services.shared.auth import require_service_auth
from services.shared.db import get_session
from services.shared.dto import LicensedProduct, UpdateSeatCountRequest
from services.shared.mappers import row_to_licensed_product
from services.shared.schemas import Change

router = APIRouter(
    prefix="/licensing/v1/license-products", dependencies=[Depends(require_service_auth)]
)


@router.patch("/{lp_id}", response_model=Change[LicensedProduct])
def update_seat_count_route(
    lp_id: int, body: UpdateSeatCountRequest, session: Session = Depends(get_session)
):
    before, after = update_seat_count(session, lp_id, body.seat_count)
    session.commit()
    return Change[LicensedProduct](
        before=row_to_licensed_product(before), after=row_to_licensed_product(after)
    )
