"""Common models (specs/tdd-apis/tdd-apis-common-models.md)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class StrictRequest(BaseModel):
    """Base for request bodies: unknown fields are rejected (400 INVALID_REQUEST)."""

    model_config = ConfigDict(extra="forbid")


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_FOUND = "NOT_FOUND"
    JOB_IN_PROGRESS = "JOB_IN_PROGRESS"
    PRECHECK_FAILED = "PRECHECK_FAILED"
    INTERNAL = "INTERNAL"


ERROR_HTTP_STATUS = {
    ErrorCode.INVALID_REQUEST: 400,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.PERMISSION_DENIED: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.JOB_IN_PROGRESS: 409,
    ErrorCode.PRECHECK_FAILED: 422,
    ErrorCode.INTERNAL: 500,
}


class ErrorDetail(BaseModel):
    field: str | None = None
    problem: str


class ErrorInfo(BaseModel):
    code: ErrorCode
    message: str
    request_id: str
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    error: ErrorInfo


class Persona(StrEnum):
    IT_ADMIN = "IT_ADMIN"
    BU_ADMIN = "BU_ADMIN"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"


class TokenType(StrEnum):
    GOOGLE = "GOOGLE"
    FIREBASE = "FIREBASE"
