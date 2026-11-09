"""Authentication and the server-built RequestContext.

specs/tdd-apis/tdd-apis-common-auth.md section 1, tdd-apis-common-models.md sections 2-3.
"""

import logging
import threading
import time
from dataclasses import dataclass, field

import requests
from google.auth import jwt
from fastapi import Request

from lsb_api.admin_roster import RosterNotLoaded
from lsb_api.directory import DirectoryError
from lsb_api.errors import ApiError
from lsb_api.models.common import ErrorCode, Persona, TokenType
from lsb_api.settings import Settings

log = logging.getLogger("lsb_api")

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"


@dataclass
class Caller:
    email: str
    subject: str
    token_type: TokenType


@dataclass
class Client:
    id: str
    name: str | None = None
    version: str | None = None


@dataclass
class RequestContext:
    request_id: str
    session_id: str | None
    received_at: float
    caller: Caller
    client: Client
    _roles: "UserRoles | None" = field(default=None, repr=False)   # caller's roles, cached per request
    _roles_live: bool = field(default=False, repr=False)            # _roles came from a live directory read


class TokenVerifier:
    """Verifies Google ID tokens. Certificates are cached for an hour."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._certs: dict[str, str] = {}
        self._certs_at = 0.0
        self._lock = threading.Lock()

    def _get_certs(self) -> dict[str, str]:
        with self._lock:
            if not self._certs or time.time() - self._certs_at > 3600:
                resp = requests.get(GOOGLE_CERTS_URL, timeout=5)
                resp.raise_for_status()
                self._certs, self._certs_at = resp.json(), time.time()
            return self._certs

    def verify(self, token: str) -> tuple[Caller, str]:
        try:
            claims = jwt.decode(token, certs=self._get_certs(), audience=self._settings.allowed_audiences,
                                clock_skew_in_seconds=10)
        except Exception as exc:  # signature, expiry, audience, malformed
            reason = "audience not accepted" if "audience" in str(exc).lower() else type(exc).__name__
            log.info("token rejected: %s", exc)
            raise ApiError(ErrorCode.UNAUTHENTICATED, f"Invalid ID token: {reason}") from exc
        if claims.get("iss") not in GOOGLE_ISSUERS:
            raise ApiError(ErrorCode.UNAUTHENTICATED, "Token issuer is not Google")
        email = str(claims.get("email", "")).lower()
        if not email or claims.get("email_verified") is not True:
            raise ApiError(ErrorCode.UNAUTHENTICATED, "Token has no verified email")
        domain = self._settings.DOMAIN
        if str(claims.get("hd", "")).lower() != domain or not email.endswith("@" + domain):
            raise ApiError(ErrorCode.UNAUTHENTICATED, f"Caller is not in {domain}")
        return Caller(email=email, subject=str(claims.get("sub", "")), token_type=TokenType.GOOGLE), str(claims.get("aud"))


def _parse_user_agent(ua: str | None) -> tuple[str | None, str | None]:
    if not ua:
        return None, None
    first = ua.split()[0]
    name, _, version = first.partition("/")
    return name or None, version or None


def get_context(request: Request) -> RequestContext:
    """FastAPI dependency: verify the bearer ID token and build the RequestContext."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer ") or not auth[7:].strip():
        raise ApiError(ErrorCode.UNAUTHENTICATED, "Missing bearer ID token")
    token = auth[7:].strip()
    if token.count(".") != 2:  # access tokens are not JWTs; only ID tokens are identity
        raise ApiError(ErrorCode.UNAUTHENTICATED, "Bearer must be an ID token, not an access token")
    caller, aud = request.app.state.verifier.verify(token)
    name, version = _parse_user_agent(request.headers.get("user-agent"))
    ctx = RequestContext(request_id=request.state.request_id, session_id=request.state.session_id,
                         received_at=request.state.received_at, caller=caller,
                         client=Client(id=aud, name=name, version=version))
    request.state.ctx = ctx
    return ctx


def personas_from_groups(settings: Settings, groups: set[str]) -> set[Persona]:
    """Personas from the set of groups a user is in (direct or nested), using the settings groups."""
    found: set[Persona] = set()
    if settings.it_admins_group in groups:
        found.add(Persona.IT_ADMIN)
    if settings.bu_admins_group in groups:
        found.add(Persona.BU_ADMIN)
    if any(g in groups for g in settings.platform_admin_groups):
        found.add(Persona.PLATFORM_ADMIN)
    return found


ROLE_ORDER = [Persona.USER, Persona.BU_ADMIN, Persona.IT_ADMIN, Persona.PLATFORM_ADMIN]


@dataclass(frozen=True)
class UserRoles:
    email: str                 # lowercase
    roles: list[Persona]       # every role held, in ROLE_ORDER; always includes USER
    groups: dict[str, str]     # {admin group: DIRECT|INDIRECT} that give those roles


def roles_of(request: Request, email: str, *, live: bool = False) -> UserRoles:
    """The one place that derives a user's roles: admin groups plus personas_from_groups.

    Groups come from the in-memory admin roster, or with `live` from the directory (written back into the
    roster). Used by the ACL (through caller_roles) and by the platform roles API. 500 INTERNAL if the
    roster has not loaded yet, or if the live directory read fails (no fallback to the cache).
    """
    email = email.strip().lower()
    request_id = getattr(request.state, "request_id", None)
    roster = request.app.state.roster
    try:
        groups = roster.refresh_user(email) if live else roster.groups_of(email)
    except RosterNotLoaded as exc:
        log.warning("admin roster not loaded request_id=%s detail=%s", request_id, exc)
        raise ApiError(ErrorCode.INTERNAL, "Admin roster not available yet")
    except DirectoryError as exc:
        log.error("live role check failed request_id=%s email=%s detail=%s", request_id, email, exc)
        raise ApiError(ErrorCode.INTERNAL, "Directory read for the role check failed")
    held = {Persona.USER} | personas_from_groups(request.app.state.settings, set(groups))
    return UserRoles(email=email, roles=[r for r in ROLE_ORDER if r in held], groups=groups)


def caller_roles(request: Request, ctx: RequestContext, *, live: bool = False) -> UserRoles:
    """The caller's roles, computed once per request and cached on the context (a live read wins)."""
    if ctx._roles is None or (live and not ctx._roles_live):
        ctx._roles, ctx._roles_live = roles_of(request, ctx.caller.email, live=live), live
    return ctx._roles


def personas(request: Request, ctx: RequestContext, *, live: bool = False) -> set[Persona]:
    """The caller's roles as a set, for ACL checks."""
    return set(caller_roles(request, ctx, live=live).roles)
