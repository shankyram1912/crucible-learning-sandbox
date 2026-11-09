"""Firestore reachability checks used by health db and health service."""

import asyncio
import logging
import time

from google.api_core import exceptions as gexc
from google.cloud import firestore

from lsb_api.models.health import CheckStatus, DatabaseCheck, DatabaseError, DatabaseRole
from lsb_api.settings import Settings

log = logging.getLogger("lsb_api")


def _classify(exc: BaseException) -> DatabaseError:
    if isinstance(exc, (asyncio.TimeoutError, gexc.DeadlineExceeded)):
        return DatabaseError.DEADLINE_EXCEEDED
    if isinstance(exc, gexc.PermissionDenied):
        return DatabaseError.PERMISSION_DENIED
    if isinstance(exc, gexc.NotFound):
        return DatabaseError.DATABASE_NOT_FOUND
    if isinstance(exc, (gexc.ServiceUnavailable, gexc.TooManyRequests)):
        return DatabaseError.UNAVAILABLE
    return DatabaseError.UNKNOWN


class FirestoreChecker:
    """One small read of `_health/ping` per database, as the API's own identity."""

    def __init__(self, settings: Settings):
        self._s = settings
        self._clients: dict[str, firestore.AsyncClient] = {}
        self.databases = [(settings.FIRESTORE_CONFIG_DATABASE, DatabaseRole.CONFIG),
                          (settings.FIRESTORE_DATABASE, DatabaseRole.RUNTIME_JOBS)]

    def _client(self, db: str) -> firestore.AsyncClient:
        if db not in self._clients:
            self._clients[db] = firestore.AsyncClient(project=self._s.CT_PROJECT_ID, database=db)
        return self._clients[db]

    async def _check_one(self, db: str, role: DatabaseRole, request_id: str) -> DatabaseCheck:
        timeout = min(self._s.LSB_HEALTH_DB_READ_TIMEOUT_SECONDS, self._s.LSB_HEALTH_DB_TOTAL_TIMEOUT_SECONDS)
        t0 = time.monotonic()
        try:
            doc = self._client(db).collection("_health").document("ping")
            await asyncio.wait_for(doc.get(timeout=timeout), timeout=timeout + 0.5)
            return DatabaseCheck(database=db, role=role, status=CheckStatus.OK,
                                 latency_ms=int((time.monotonic() - t0) * 1000))
        except Exception as exc:  # noqa: BLE001 - every failure is reported as a code
            err = _classify(exc)
            log.warning("health db check failed request_id=%s database=%s error=%s detail=%r",
                        request_id, db, err.value, exc)
            return DatabaseCheck(database=db, role=role, status=CheckStatus.FAIL,
                                 latency_ms=int((time.monotonic() - t0) * 1000), error=err)

    async def check_all(self, request_id: str) -> list[DatabaseCheck]:
        return list(await asyncio.gather(*(self._check_one(db, role, request_id) for db, role in self.databases)))
