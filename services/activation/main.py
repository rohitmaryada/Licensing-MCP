from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy.orm import Session
from sqlalchemy import text

from services.activation.queries import get_activation, list_activations
from services.activation.write_queries import reset_activation, revoke_activation
from services.shared.auth import require_service_auth
from services.shared.db import check_db_ready, get_session
from services.shared.dto import ActivationActionRequest, ActivationState, StaleActivation
from services.shared.errors import BadRequestError, NotFoundError, register_error_handlers
from services.shared.mappers import row_to_activation_state, row_to_stale_activation
from services.shared.schemas import Change, Page, PageParams, build_page

app = FastAPI(title="Activation Service")
register_error_handlers(app)

router = APIRouter(prefix="/activation/v1", dependencies=[Depends(require_service_auth)])


@router.get("/activations", response_model=Page[StaleActivation])
def list_activations_route(
    entitlementId: int | None = None,
    userEmail: str | None = None,
    status: str | None = None,
    staleDays: int | None = None,
    page: PageParams = Depends(),
    session: Session = Depends(get_session),
):
    # General-purpose filtered list (CONTRACTS.md §5) — also the internal call
    # Entitlement's E1 makes (entitlementId + staleDays) via shared/clients.py.
    # >=1 of entitlementId/userEmail required: status/staleDays alone would be
    # an unindexed full scan (only entitlement_id and user_id are indexed).
    if entitlementId is None and userEmail is None:
        raise BadRequestError(
            detail="at least one filter is required",
            detail_messages=["one of entitlementId, userEmail"],
        )
    rows, total = list_activations(
        session,
        entitlement_id=entitlementId,
        user_email=userEmail,
        status=status,
        stale_days=staleDays,
        page=page,
    )
    items = [row_to_stale_activation(r) for r in rows]
    return build_page(items, total, page)


@router.get("/activations/{activation_id}", response_model=ActivationState)
def get_activation_route(activation_id: int, session: Session = Depends(get_session)):
    row = get_activation(session, activation_id)
    if row is None:
        raise NotFoundError(detail=f"activation {activation_id} not found")
    return row_to_activation_state(row)


@router.post("/activations/{activation_id}/revoke", response_model=Change[ActivationState])
def revoke_activation_route(
    activation_id: int, body: ActivationActionRequest, session: Session = Depends(get_session)
):
    # `body.reason` is accepted per contract but not persisted — audit is MCP-side.
    before, after = revoke_activation(session, activation_id)
    session.commit()
    return Change[ActivationState](
        before=row_to_activation_state(before), after=row_to_activation_state(after)
    )


@router.post("/activations/{activation_id}/reset", response_model=Change[ActivationState])
def reset_activation_route(
    activation_id: int, body: ActivationActionRequest, session: Session = Depends(get_session)
):
    before, after = reset_activation(session, activation_id)
    session.commit()
    return Change[ActivationState](
        before=row_to_activation_state(before), after=row_to_activation_state(after)
    )


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
    row = session.execute(text("SELECT id FROM activation LIMIT 1")).mappings().first()
    return {"row": dict(row) if row else None}
