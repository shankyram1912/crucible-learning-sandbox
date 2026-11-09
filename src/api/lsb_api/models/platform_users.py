"""Platform users domain models (specs/tdd-apis/tdd-apis-platform-users.md)."""

from enum import StrEnum

from pydantic import BaseModel


class PlatformRole(StrEnum):
    IT_ADMIN = "IT_ADMIN"
    BU_ADMIN = "BU_ADMIN"
    OTHER = "OTHER"


class Relation(StrEnum):
    DIRECT = "DIRECT"
    INDIRECT = "INDIRECT"


class PlatformRoleResponse(BaseModel):
    email: str
    platform_role: PlatformRole
    matched_group: str | None = None
    relation: Relation | None = None
