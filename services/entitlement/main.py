from fastapi import APIRouter, Depends, FastAPI, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.entitlement.queries import (
    get_policy_for_entitlement,
    get_user_context,
    list_entitlements,
    list_user_entitlements,
)
from services.shared.auth import require_service_auth
from services.shared.clients import activation_client
from services.shared.db import check_db_ready, get_session
from services.shared.dto import EntitlementSummary, UserEntitlementsResponse
from services.shared.errors import BadRequestError, NotFoundError, register_error_handlers
from services.shared.mappers import build_entitlement, row_to_entitlement_summary, row_to_user_context
from services.shared.schemas import Page, PageParams, build_page

app = FastAPI(title="Entitlement Service")
register_error_handlers(app)

router = APIRouter(prefix="/entitlement/v1", dependencies=[Depends(require_service_auth)])


@router.get("/users/{email}/entitlements", response_model=UserEntitlementsResponse)
def check_user_entitlements(
    email: str,
    request: Request,
    status: str | None = None,
    includeStaleActivations: bool = False,
    page: PageParams = Depends(),
    session: Session = Depends(get_session),
):
    user_row = get_user_context(session, email)
    if user_row is None:
        raise NotFoundError(detail=f"user {email} not found")

    rows, total = list_user_entitlements(session, user_row["id"], status, page)
    items = []
    for row in rows:
        policy_row = get_policy_for_entitlement(session, row["id"])
        stale_rows = []
        if includeStaleActivations and policy_row is not None:
            stale_rows = activation_client.stale_activations(
                row["id"], policy_row["activation_ttl_days"], request.headers
            )
        items.append(build_entitlement(row, policy_row, stale_rows))

    page_wrapper = build_page(items, total, page)
    return UserEntitlementsResponse(
        user=row_to_user_context(user_row), items=page_wrapper.items, page_info=page_wrapper.pageInfo
    )


@router.get("/entitlements", response_model=Page[EntitlementSummary])
def list_entitlements_route(
    licenseId: int | None = None,
    masterLicenseId: int | None = None,
    licenseProductId: int | None = None,
    status: str | None = None,
    page: PageParams = Depends(),
    session: Session = Depends(get_session),
):
    if licenseId is masterLicenseId is licenseProductId is status is None:
        raise BadRequestError(
            detail="at least one filter is required",
            detail_messages=["one of licenseId, masterLicenseId, licenseProductId, status"],
        )
    rows, total = list_entitlements(
        session,
        license_id=licenseId,
        master_license_id=masterLicenseId,
        license_product_id=licenseProductId,
        status=status,
        page=page,
    )
    items = [row_to_entitlement_summary(r) for r in rows]
    return build_page(items, total, page)


app.include_router(router)


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    if check_db_ready():
        return {"status": "ok"}
    from fastapi.responses import JSONResponse

    return JSONResponse({"status": "unready"}, status_code=503)


@app.get("/_demo", dependencies=[Depends(require_service_auth)])
def demo(session: Session = Depends(get_session)):
    row = session.execute(text("SELECT id FROM entitlement LIMIT 1")).mappings().first()
    return {"row": dict(row) if row else None}
