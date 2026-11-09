"""Authentication and the server-built RequestContext.

specs/tdd-apis/tdd-apis-common-auth.md section 1, tdd-apis-common-models.md sections 2-3.
"""

import logging
import threading
import time
from dataclasses import dataclass, field

import google.auth
import requests
from google.auth import jwt
from google.auth.transport.requests import AuthorizedSession
from fastapi import Request

from lsb_api.errors import ApiError
from lsb_api.models.common import ErrorCode, Persona, TokenType
from lsb_api.settings import Settings

log = logging.getLogger("lsb_api")

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"
CLOUD_IDENTITY = "https://cloudidentity.googleapis.com/v1"


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


class MembershipChecker:
    """Transitive Google Group membership through the Cloud Identity API, as the API's own identity."""

    def __init__(self, ttl_seconds: float = 60.0):
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self._session = AuthorizedSession(creds)
        self._group_names: dict[str, str] = {}
        self._cache: dict[tuple[str, str], tuple[float, bool]] = {}
        self._ttl = ttl_seconds

    def _group_name(self, group_email: str) -> str:
        if group_email not in self._group_names:
            r = self._session.get(f"{CLOUD_IDENTITY}/groups:lookup", params={"groupKey.id": group_email}, timeout=5)
            r.raise_for_status()
            self._group_names[group_email] = r.json()["name"]
        return self._group_names[group_email]

    def is_member(self, group_email: str, member_email: str) -> bool:
        key = (group_email, member_email)
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < self._ttl:
            return hit[1]
        name = self._group_name(group_email)
        r = self._session.get(f"{CLOUD_IDENTITY}/{name}/memberships:checkTransitiveMembership",
                              params={"query": f"member_key_id == '{member_email}'"}, timeout=5)
        r.raise_for_status()
        result = bool(r.json().get("hasMembership", False))
        self._cache[key] = (time.time(), result)
        return result


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


def personas(request: Request, ctx: RequestContext) -> set[Persona]:
    """Resolve personas on demand (transitive group membership), cached on the context."""
    if ctx._personas is not None:
        return ctx._personas
    s: Settings = request.app.state.settings
    checker: MembershipChecker = request.app.state.membership
    found: set[Persona] = set()
    if any(checker.is_member(g, ctx.caller.email) for g in s.platform_admin_groups):
        found.add(Persona.PLATFORM_ADMIN)
    ctx._personas = found
    return found


def require_persona(request: Request, ctx: RequestContext, persona: Persona) -> None:
    try:
        ok = persona in personas(request, ctx)
    except ApiError:
        raise
    except Exception:
        log.exception("persona lookup failed request_id=%s", ctx.request_id)
        raise ApiError(ErrorCode.INTERNAL, "Could not check group membership")
    if not ok:
        raise ApiError(ErrorCode.PERMISSION_DENIED, f"This operation needs the {persona.value} persona")
