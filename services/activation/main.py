from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.activation.queries import list_stale_activations
from services.shared.auth import require_service_auth
from services.shared.db import check_db_ready, get_session
from services.shared.dto import StaleActivation
from services.shared.errors import register_error_handlers
from services.shared.mappers import row_to_stale_activation
from services.shared.schemas import Page, PageParams, build_page

app = FastAPI(title="Activation Service")
register_error_handlers(app)

router = APIRouter(prefix="/activation/v1", dependencies=[Depends(require_service_auth)])


@router.get("/activations", response_model=Page[StaleActivation])
def list_activations(
    entitlementId: int,
    staleDays: int,
    page: PageParams = Depends(),
    session: Session = Depends(get_session),
):
    # Internal only this slice — no MCP tool calls Activation directly.
    # Consumed by Entitlement's E1 (includeStaleActivations=true) via
    # services/shared/clients.py.
    rows, total = list_stale_activations(session, entitlementId, staleDays, page)
    items = [row_to_stale_activation(r) for r in rows]
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
    row = session.execute(text("SELECT id FROM activation LIMIT 1")).mappings().first()
    return {"row": dict(row) if row else None}
