"""Access control (specs/02-tdd/tdd-apis/tdd-apis-common-acl.md).

The ACL itself is configuration: settings `LSB_ACL` maps every operation to 1..N roles (default in
settings.DEFAULT_ACL). The same rules apply to every client (lsb CLI, REST, scripts, future UI).

Roles: USER (any authenticated user of the domain), IT_ADMIN, BU_ADMIN (from the in-memory admin roster);
PLATFORM_ADMIN is reserved for future use. Default deny. The API refuses to start if a route's operation
has no ACL entry, or if the ACL names an operation no route uses.
"""

from fastapi import Depends, Request

from lsb_api.context import RequestContext, get_context, personas
from lsb_api.errors import ApiError
from lsb_api.models.common import ErrorCode, Persona
from lsb_api.settings import Settings

OPERATIONS: set[str] = set()   # every operation used by a route (one route, one operation)


def operation(name: str) -> str:
    OPERATIONS.add(name)
    return name


def check(request: Request, ctx: RequestContext, op: str) -> None:
    """Raise 403 unless the caller holds one of the roles the ACL allows for `op`."""
    allowed = request.app.state.settings.acl.get(op)
    if not allowed:
        raise ApiError(ErrorCode.PERMISSION_DENIED, f"Operation {op} is not allowed for anyone")
    if Persona.USER in allowed:
        return  # any authenticated user; no roster needed
    # Cached roster by default; LSB_ROLE_CHECK_USE_CACHE=false reads the directory live and refreshes the roster.
    live = not request.app.state.settings.LSB_ROLE_CHECK_USE_CACHE
    held = personas(request, ctx, live=live)   # 500 INTERNAL if roster not loaded or live read fails
    if not held & allowed:
        roles = ", ".join(sorted(r.value for r in allowed))
        raise ApiError(ErrorCode.PERMISSION_DENIED, f"This operation needs one of these roles: {roles}")


def allow(op: str):
    """FastAPI dependency: authenticate, then apply the ACL for `op`. Returns the RequestContext."""
    operation(op)

    def dependency(request: Request, ctx: RequestContext = Depends(get_context)) -> RequestContext:
        check(request, ctx, op)
        return ctx

    return dependency


def verify(settings: Settings) -> None:
    """Startup check: the ACL maps exactly the operations the API uses."""
    configured = set(settings.LSB_ACL)
    missing, unknown = OPERATIONS - configured, configured - OPERATIONS
    problems = []
    if missing:
        problems.append(f"operations without an ACL entry: {sorted(missing)}")
    if unknown:
        problems.append(f"ACL entries for unknown operations: {sorted(unknown)}")
    if problems:
        raise RuntimeError("LSB_ACL does not match the API: " + "; ".join(problems))
