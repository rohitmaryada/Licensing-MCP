from fastapi import Request

from services.shared.errors import UnauthorizedError

REQUIRED_HEADERS = (
    "mathworks-access-key",
    "X-MW-WS-Caller-Id",
    "mathworks-requestid",
)

OPTIONAL_TOKEN_HEADER = "X-MW-WS-Security-Token"


def require_service_auth(request: Request) -> None:
    # B5 will replace this body with real JWT verification.
    for header in REQUIRED_HEADERS:
        if not request.headers.get(header):
            raise UnauthorizedError(detail="Missing service auth headers")

    token = request.headers.get(OPTIONAL_TOKEN_HEADER)
    if token:
        request.state.user_token = token
