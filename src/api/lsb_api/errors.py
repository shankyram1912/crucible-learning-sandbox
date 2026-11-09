"""Errors: one shape for every 4xx/5xx (specs/tdd-apis/tdd-apis-common-models.md section 5)."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from lsb_api.models.common import ERROR_HTTP_STATUS, ErrorCode, ErrorDetail, ErrorInfo, ErrorResponse

log = logging.getLogger("lsb_api")


class ApiError(Exception):
    def __init__(self, code: ErrorCode, message: str, details: list[ErrorDetail] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def error_response(request: Request, code: ErrorCode, message: str,
                   details: list[ErrorDetail] | None = None) -> JSONResponse:
    body = ErrorResponse(error=ErrorInfo(code=code, message=message,
                                         request_id=_request_id(request), details=details))
    headers = {"WWW-Authenticate": "Bearer"} if code == ErrorCode.UNAUTHENTICATED else None
    return JSONResponse(status_code=ERROR_HTTP_STATUS[code],
                        content=body.model_dump(mode="json", exclude_none=True), headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return error_response(request, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        details = [ErrorDetail(field=".".join(str(p) for p in e.get("loc", ())[1:]) or None,
                               problem=e.get("msg", "invalid")) for e in exc.errors()]
        return error_response(request, ErrorCode.INVALID_REQUEST,
                              f"{len(details)} problem(s) found", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {404: ErrorCode.NOT_FOUND, 401: ErrorCode.UNAUTHENTICATED,
                403: ErrorCode.PERMISSION_DENIED, 405: ErrorCode.INVALID_REQUEST}.get(
                    exc.status_code, ErrorCode.INTERNAL)
        return error_response(request, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        log.exception("unexpected error request_id=%s", _request_id(request))
        return error_response(request, ErrorCode.INTERNAL, "Unexpected failure")
