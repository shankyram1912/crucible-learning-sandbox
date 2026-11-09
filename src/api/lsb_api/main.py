"""LSB Control Tower: Learning Sandbox Self Service APIs (FastAPI app)."""

import asyncio
import contextlib
import logging
import time
import uuid

from fastapi import FastAPI, Request

from lsb_api import health, platform_users
from lsb_api.context import TokenVerifier
from lsb_api.admin_roster import AdminRoster
from lsb_api.errors import install_error_handlers
from lsb_api.firestore_check import FirestoreChecker
from lsb_api.settings import Settings, get_settings

log = logging.getLogger("lsb_api")


def create_app(settings: Settings | None = None, *, verifier=None, roster=None, db_checker=None) -> FastAPI:
    s = settings or get_settings()  # validates settings: refuses to start if invalid
    logging.basicConfig(level=s.LSB_LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        # Final startup step: load the admin roster, then refresh it in the background.
        try:
            await asyncio.to_thread(app.state.roster.refresh)
        except Exception as exc:  # serve anyway; persona checks answer 500 until a refresh succeeds
            app.state.roster.last_error = f"{type(exc).__name__}: {exc}"
            log.error("admin roster failed to load at startup: %s", app.state.roster.last_error)
        task = asyncio.create_task(app.state.roster.run())
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title="Learning Sandbox Self Service APIs", version=s.LSB_API_VERSION, lifespan=lifespan)
    app.state.settings = s
    app.state.verifier = verifier or TokenVerifier(s)
    app.state.roster = roster if roster is not None else AdminRoster(s)
    app.state.db_checker = db_checker or FirestoreChecker(s)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(platform_users.router)
    from lsb_api import acl
    acl.verify(s)  # refuse to start if the ACL does not map exactly the operations in use

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


def app_factory() -> FastAPI:
    return create_app()
