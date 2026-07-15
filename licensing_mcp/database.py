"""
Database session factory.

This is the ONLY place in the codebase that knows where the database lives.
All tool handlers call get_session() from here — nothing else knows the path.

POC: points at the local SQLite file.
Production: change _DB_URL to your MS SQL Server connection string.
The rest of the codebase does not change.

Example production swap:
    _DB_URL = (
        "mssql+pyodbc://user:pass@server/LicensingDB"
        "?driver=ODBC+Driver+18+for+SQL+Server"
    )
"""

import os
from pathlib import Path
from sqlalchemy.orm import Session
from licensing_mcp.models import get_engine

# LICENSING_BACKEND selects where data_access reads from:
#   "sqlite"   (default) — the flat SQLite POC model (unchanged; live demo path)
#   "services" — HTTP calls to the real domain services (C1). get_session()
#                returns a ServiceClient instead of a SQLAlchemy Session; the
#                query_* functions detect it and take the HTTP path. Tool handlers
#                are identical either way — the "only data_access changes" bet.
_BACKEND = os.environ.get("LICENSING_BACKEND", "sqlite").lower()

# Path(__file__) is always this file's location on disk, regardless of where
# the process was launched from. .parent.parent walks up to the project root.
_PROJECT_ROOT = Path(__file__).parent.parent

# LICENSING_DB_PATH override lets tests point at a throwaway copy of the
# database instead of mutating the demo dataset. This is 12-factor config:
# the same code runs against dev/test/prod purely via environment.
_DB_PATH = Path(os.environ.get(
    "LICENSING_DB_PATH",
    _PROJECT_ROOT / "data" / "licensing.db",
))

_engine = get_engine(str(_DB_PATH))


def get_session():
    """
    Return a backend handle for data_access.

    - sqlite backend (default): a SQLAlchemy Session bound to the engine.
    - services backend: a ServiceClient (httpx). It exposes the same lifecycle
      the tool layer uses (`.close()`, context manager), so tool handlers don't
      change. The query_* functions branch on the handle type.
    """
    if _BACKEND == "services":
        from licensing_mcp.data_access.service_client import ServiceClient
        return ServiceClient()
    return Session(_engine)
