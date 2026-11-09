"""Health domain (specs/02-tdd/tdd-apis/tdd-apis-health.md): health api, health db, health service."""

import asyncio
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from lsb_api.acl import allow
from lsb_api.context import RequestContext
from lsb_api.models.common import ErrorResponse
from lsb_api.models.health import (CheckStatus, DatabaseRole, HealthApiResponse, HealthDbResponse,
                                   HealthServiceResponse, ServiceStatus)

router = APIRouter(prefix="/v1/health", tags=["health"])
ERRORS = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}


@router.get("/api", response_model=HealthApiResponse, responses=ERRORS)
def health_api(request: Request, ctx: RequestContext = Depends(allow("health.api"))) -> HealthApiResponse:
    """Operation 01: the API process is up. No dependency calls."""
    return HealthApiResponse(version=request.app.state.settings.LSB_API_VERSION,
                             time=datetime.now(timezone.utc).replace(microsecond=0), caller=ctx.caller.email)


@router.get("/db", response_model=HealthDbResponse,
            responses={**ERRORS, 503: {"model": HealthDbResponse}})
async def health_db(request: Request, ctx: RequestContext = Depends(allow("health.db"))):
    """Operation 02: one read per Firestore database, with details."""
    checks = await request.app.state.db_checker.check_all(ctx.request_id)
    ok = all(c.status == CheckStatus.OK for c in checks)
    body = HealthDbResponse(status=CheckStatus.OK if ok else CheckStatus.FAIL, databases=checks)
    return JSONResponse(status_code=200 if ok else 503, content=body.model_dump(mode="json", exclude_none=True))


@router.get("/service", response_model=HealthServiceResponse,
            responses={**ERRORS, 503: {"model": HealthServiceResponse}})
async def health_service(request: Request, ctx: RequestContext = Depends(allow("health.service"))):
    """Operation 03: the same data check, answered only as OK / NOT_OK. Cached briefly."""
    state = request.app.state
    ttl = state.settings.LSB_HEALTH_SERVICE_CACHE_SECONDS
    if not hasattr(state, "service_lock"):
        state.service_lock, state.service_cache = asyncio.Lock(), None
    async with state.service_lock:
        hit = state.service_cache
        if hit and time.monotonic() - hit[0] < ttl:
            body = hit[1]
        else:
            checks = await request.app.state.db_checker.check_all(ctx.request_id)
            by_role = {c.role: (ServiceStatus.OK if c.status == CheckStatus.OK else ServiceStatus.NOT_OK)
                       for c in checks}
            config = by_role.get(DatabaseRole.CONFIG, ServiceStatus.NOT_OK)
            runtime = by_role.get(DatabaseRole.RUNTIME_JOBS, ServiceStatus.NOT_OK)
            overall = ServiceStatus.OK if config == runtime == ServiceStatus.OK else ServiceStatus.NOT_OK
            body = HealthServiceResponse(status=overall, config=config, runtime_jobs=runtime)
            state.service_cache = (time.monotonic(), body)
    return JSONResponse(status_code=200 if body.status == ServiceStatus.OK else 503,
                        content=body.model_dump(mode="json"))
