"""Platform users domain (specs/02-tdd/tdd-apis/tdd-apis-platform-users.md): platform roles."""

import re

from fastapi import APIRouter, Depends, Path, Request

from lsb_api import acl
from lsb_api.context import RequestContext, UserRoles, caller_roles, roles_of
from lsb_api.errors import ApiError
from lsb_api.models.common import ErrorCode, ErrorResponse
from lsb_api.models.platform_users import AdminGroupMembership, PlatformRolesResponse, Relation

router = APIRouter(prefix="/v1/platform-users", tags=["platform-users"])
ERRORS = {400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
          500: {"model": ErrorResponse}}
EMAIL = re.compile(r"^[^@\s']+@[^@\s']+\.[^@\s']+$")


def _response(r: UserRoles) -> PlatformRolesResponse:
    return PlatformRolesResponse(
        email=r.email, roles=r.roles,
        groups=[AdminGroupMembership(group=g, relation=Relation(rel)) for g, rel in sorted(r.groups.items())],
    )


# Declared before /{email}/roles so that "me" is never read as an email.
@router.get("/me/roles", response_model=PlatformRolesResponse, responses=ERRORS)
async def get_my_platform_roles(request: Request,
                                ctx: RequestContext = Depends(acl.allow("platform_users.roles.self"))):
    """All platform roles of the caller (ACL: platform_users.roles.self)."""
    return _response(caller_roles(request, ctx))


@router.get("/{email}/roles", response_model=PlatformRolesResponse, responses=ERRORS)
async def get_platform_roles(request: Request, email: str = Path(description="The user's email"),
                             ctx: RequestContext = Depends(acl.allow("platform_users.roles"))):
    """All platform roles of any user (ACL: platform_users.roles)."""
    target = email.strip().lower()
    if not EMAIL.match(target):
        raise ApiError(ErrorCode.INVALID_REQUEST, f"Not a valid email: {target}")
    return _response(caller_roles(request, ctx) if target == ctx.caller.email else roles_of(request, target))
