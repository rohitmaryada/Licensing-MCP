from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.shared.auth import require_service_auth
from services.shared.db import check_db_ready, get_session
from services.shared.errors import register_error_handlers

app = FastAPI(title="Activation Service", root_path="/activation/v1")
register_error_handlers(app)


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
