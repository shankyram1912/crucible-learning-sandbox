"""Platform users domain (specs/tdd-apis/tdd-apis-platform-users.md): platform role."""

import logging
import re

from fastapi import APIRouter, Depends, Query, Request

from lsb_api import acl
from lsb_api.context import RequestContext
from lsb_api.admin_roster import RosterNotLoaded
from lsb_api.errors import ApiError
from lsb_api.models.common import ErrorCode, ErrorResponse
from lsb_api.models.platform_users import PlatformRole, PlatformRoleResponse, Relation
from lsb_api.settings import Settings

log = logging.getLogger("lsb_api")
router = APIRouter(prefix="/v1/platform-users", tags=["platform-users"])
ERRORS = {400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
          500: {"model": ErrorResponse}}
ROLE_OTHER = acl.operation("platform_users.role.other")
EMAIL = re.compile(r"^[^@\s']+@[^@\s']+\.[^@\s']+$")


def platform_role(settings: Settings, email: str, groups: dict[str, str]) -> PlatformRoleResponse:
    """IT_ADMIN if in IT_ADMINS_GROUP, else BU_ADMIN if in BU_ADMINS_GROUP, else OTHER.

    `groups` is {admin group: DIRECT|INDIRECT} for the user, from the admin roster.
    """
    for role, group in ((PlatformRole.IT_ADMIN, settings.it_admins_group),
                        (PlatformRole.BU_ADMIN, settings.bu_admins_group)):
        if group in groups:
            return PlatformRoleResponse(email=email, platform_role=role, matched_group=group,
                                        relation=Relation(groups[group]))
    return PlatformRoleResponse(email=email, platform_role=PlatformRole.OTHER)


def _lookup(request: Request, ctx: RequestContext, email: str | None) -> PlatformRoleResponse:
    target = (email or ctx.caller.email).strip().lower()
    if not EMAIL.match(target):
        raise ApiError(ErrorCode.INVALID_REQUEST, f"Not a valid email: {target}")
    if target != ctx.caller.email:
        acl.check(request, ctx, ROLE_OTHER)
    try:
        groups = request.app.state.roster.groups_of(target)
    except RosterNotLoaded as exc:
        log.warning("admin roster not loaded request_id=%s detail=%s", ctx.request_id, exc)
        raise ApiError(ErrorCode.INTERNAL, "Admin roster not available yet")
    return platform_role(request.app.state.settings, target, groups)


@router.get("/role", response_model=PlatformRoleResponse, responses=ERRORS)
async def get_platform_role(request: Request, ctx: RequestContext = Depends(acl.allow("platform_users.role")),
                            email: str | None = Query(None, description="Another user's email (ACL platform_users.role.other)")):
    """The platform role of the caller, or of `email` (ACL: platform_users.role / platform_users.role.other)."""
    return _lookup(request, ctx, email)
