"""Platform users domain models (specs/02-tdd/tdd-apis/tdd-apis-platform-users.md)."""

from enum import StrEnum

from pydantic import BaseModel

from lsb_api.models.common import Persona


class Relation(StrEnum):
    DIRECT = "DIRECT"
    INDIRECT = "INDIRECT"


class AdminGroupMembership(BaseModel):
    group: str
    relation: Relation


class PlatformRolesResponse(BaseModel):
    email: str
    roles: list[Persona]                  # every role the user holds, in the ACL vocabulary
    groups: list[AdminGroupMembership]    # admin groups from settings that give those roles
