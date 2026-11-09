"""Health domain models (specs/02-tdd/tdd-apis/tdd-apis-health.md)."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ApiStatus(StrEnum):
    OK = "OK"


class CheckStatus(StrEnum):
    OK = "OK"
    FAIL = "FAIL"


class ServiceStatus(StrEnum):
    OK = "OK"
    NOT_OK = "NOT_OK"


class DatabaseRole(StrEnum):
    CONFIG = "CONFIG"
    RUNTIME_JOBS = "RUNTIME_JOBS"


class DatabaseError(StrEnum):
    PERMISSION_DENIED = "PERMISSION_DENIED"
    DATABASE_NOT_FOUND = "DATABASE_NOT_FOUND"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class HealthApiResponse(BaseModel):
    status: ApiStatus = ApiStatus.OK
    service: str = "lsb-api"
    version: str
    time: datetime
    caller: str


class DatabaseCheck(BaseModel):
    database: str
    role: DatabaseRole
    status: CheckStatus
    latency_ms: int
    error: DatabaseError | None = None


class HealthDbResponse(BaseModel):
    status: CheckStatus
    databases: list[DatabaseCheck]


class HealthServiceResponse(BaseModel):
    status: ServiceStatus
    config: ServiceStatus
    runtime_jobs: ServiceStatus
