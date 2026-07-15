from fastapi import APIRouter, Depends, FastAPI, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.entitlement.queries import (
    get_entitlement_core,
    get_policy_for_entitlement,
    get_user_context,
    list_entitlement_people,
    list_entitlements,
    list_user_entitlements,
    search_users,
)
from services.shared.auth import require_service_auth
from services.shared.clients import activation_client
from services.shared.db import check_db_ready, get_session
from services.shared.dto import (
    Entitlement,
    EntitlementPerson,
    EntitlementSummary,
    Policy,
    UserContext,
    UserEntitlementsResponse,
)
from services.shared.errors import BadRequestError, NotFoundError, register_error_handlers
from services.shared.mappers import (
    build_entitlement,
    row_to_entitlement_person,
    row_to_entitlement_summary,
    row_to_user_context,
)
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


@router.get("/users", response_model=Page[UserContext])
def find_users_route(
    name: str = Query(..., min_length=2, description="name or email substring to search for"),
    company: str | None = Query(default=None, description="optional: narrow by the user's company"),
    page: PageParams = Depends(),
    session: Session = Depends(get_session),
):
    """find_user — resolve a person's name (or partial email) to matching users,
    with their company, so a caller who only has a name can disambiguate before
    looking up entitlements. Optional `company` narrows common names."""
    rows, total = search_users(session, name, page, company=company)
    items = [row_to_user_context(r) for r in rows]
    return build_page(items, total, page)


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


@router.get("/entitlements/{entitlement_id}", response_model=Entitlement)
def get_entitlement_route(
    entitlement_id: int,
    include: str | None = Query(default=None, description="comma-separated: policy,people"),
    session: Session = Depends(get_session),
):
    row = get_entitlement_core(session, entitlement_id)
    if row is None:
        raise NotFoundError(detail=f"entitlement {entitlement_id} not found")

    wanted = set((include or "").split(",")) if include else set()
    policy_row = get_policy_for_entitlement(session, entitlement_id) if "policy" in wanted else None
    people_rows = list_entitlement_people(session, entitlement_id, PageParams(page=0, size=100))[0] if "people" in wanted else None

    return build_entitlement(row, policy_row, stale_rows=[], people_rows=people_rows)


@router.get("/entitlements/{entitlement_id}/policy", response_model=Policy)
def get_entitlement_policy_route(entitlement_id: int, session: Session = Depends(get_session)):
    if get_entitlement_core(session, entitlement_id) is None:
        raise NotFoundError(detail=f"entitlement {entitlement_id} not found")
    policy_row = get_policy_for_entitlement(session, entitlement_id)
    if policy_row is None:
        raise NotFoundError(detail=f"no policy found for entitlement {entitlement_id}")
    return Policy(**policy_row)


@router.get("/entitlements/{entitlement_id}/people", response_model=Page[EntitlementPerson])
def list_entitlement_people_route(
    entitlement_id: int, page: PageParams = Depends(), session: Session = Depends(get_session)
):
    if get_entitlement_core(session, entitlement_id) is None:
        raise NotFoundError(detail=f"entitlement {entitlement_id} not found")
    rows, total = list_entitlement_people(session, entitlement_id, page)
    items = [row_to_entitlement_person(r) for r in rows]
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
