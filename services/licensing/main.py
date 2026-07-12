from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.licensing.routers import license_products, licensees, licenses, master_licenses
from services.shared.auth import require_service_auth
from services.shared.db import check_db_ready, get_session
from services.shared.errors import register_error_handlers

app = FastAPI(title="Licensing Service")
register_error_handlers(app)
app.include_router(licensees.router)
app.include_router(master_licenses.router)
app.include_router(licenses.router)
app.include_router(license_products.router)


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
    row = session.execute(text("SELECT id, name FROM entity LIMIT 1")).mappings().first()
    return {"row": dict(row) if row else None}
