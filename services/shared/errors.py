import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from services.shared.schemas import ErrorResponse

logger = logging.getLogger("services")


class ServiceError(Exception):
    status_code: int = 500
    detail_type: str = "INTERNAL_ERROR"

    def __init__(self, detail: str, detail_messages: list[str] | None = None):
        self.detail = detail
        self.detail_messages = detail_messages or []
        super().__init__(detail)


class BadRequestError(ServiceError):
    status_code = 400
    detail_type = "BAD_REQUEST"


class UnauthorizedError(ServiceError):
    status_code = 401
    detail_type = "UNAUTHORIZED"


class ForbiddenError(ServiceError):
    status_code = 403
    detail_type = "FORBIDDEN"


class NotFoundError(ServiceError):
    status_code = 404
    detail_type = "NOT_FOUND"


class ConflictError(ServiceError):
    status_code = 409
    detail_type = "CONFLICT"


class InternalError(ServiceError):
    status_code = 500
    detail_type = "INTERNAL_ERROR"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def _service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
        body = ErrorResponse(
            detail=exc.detail,
            detailType=exc.detail_type,
            detailMessages=exc.detail_messages,
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        body = ErrorResponse(
            detail="Invalid request parameters",
            detailType="BAD_REQUEST",
            detailMessages=[str(e) for e in exc.errors()],
        )
        return JSONResponse(status_code=400, content=body.model_dump())

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        body = ErrorResponse(detail="Internal server error", detailType="INTERNAL_ERROR")
        return JSONResponse(status_code=500, content=body.model_dump())
