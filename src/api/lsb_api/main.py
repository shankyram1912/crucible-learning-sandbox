"""LSB Control Tower: Learning Sandbox Self Service APIs (FastAPI app)."""

import logging
import time
import uuid

from fastapi import FastAPI, Request

from lsb_api import health
from lsb_api.context import MembershipChecker, TokenVerifier
from lsb_api.errors import install_error_handlers
from lsb_api.firestore_check import FirestoreChecker
from lsb_api.settings import Settings, get_settings

log = logging.getLogger("lsb_api")


def create_app(settings: Settings | None = None, *, verifier=None, membership=None, db_checker=None) -> FastAPI:
    s = settings or get_settings()  # validates settings: refuses to start if invalid
    logging.basicConfig(level=s.LSB_LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(title="Learning Sandbox Self Service APIs", version=s.LSB_API_VERSION)
    app.state.settings = s
    app.state.verifier = verifier or TokenVerifier(s)
    app.state.membership = membership if membership is not None else _LazyMembership()
    app.state.db_checker = db_checker or FirestoreChecker(s)
    install_error_handlers(app)
    app.include_router(health.router)

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or f"r-{uuid.uuid4().hex[:16]}"
        request.state.session_id = request.headers.get("x-lsb-session-id")
        request.state.received_at = time.time()
        t0 = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        if request.state.session_id:
            response.headers["X-LSB-Session-Id"] = request.state.session_id
        ctx = getattr(request.state, "ctx", None)
        log.info("request_id=%s session_id=%s client_id=%s caller=%s %s %s -> %s %dms",
                 request.state.request_id, request.state.session_id or "-",
                 ctx.client.id if ctx else "-", ctx.caller.email if ctx else "-",
                 request.method, request.url.path, response.status_code, int((time.monotonic() - t0) * 1000))
        return response

    return app


class _LazyMembership:
    """Creates the Cloud Identity client on first use, so apps that never check personas need no credentials."""

    def __init__(self):
        self._real: MembershipChecker | None = None

    def is_member(self, group: str, member: str) -> bool:
        if self._real is None:
            self._real = MembershipChecker()
        return self._real.is_member(group, member)


def app_factory() -> FastAPI:
    return create_app()
