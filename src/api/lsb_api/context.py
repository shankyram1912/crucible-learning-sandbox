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
    _personas: set[Persona] | None = field(default=None, repr=False)


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


def personas(request: Request, ctx: RequestContext) -> set[Persona]:
    """The caller's personas from the in-memory admin roster (no directory call per request)."""
    if ctx._personas is None:
        groups = set(request.app.state.roster.groups_of(ctx.caller.email))
        ctx._personas = {Persona.USER} | personas_from_groups(request.app.state.settings, groups)
    return ctx._personas


def require_persona(request: Request, ctx: RequestContext, persona: Persona,
                    denied_message: str | None = None) -> None:
    try:
        ok = persona in personas(request, ctx)
    except ApiError:
        raise
    except Exception:
        log.exception("persona lookup failed request_id=%s", ctx.request_id)
        raise ApiError(ErrorCode.INTERNAL, "Admin roster not available yet")
    if not ok:
        raise ApiError(ErrorCode.PERMISSION_DENIED,
                       denied_message or f"This operation needs the {persona.value} persona")
