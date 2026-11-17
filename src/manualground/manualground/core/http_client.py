"""Rate-paced GCP REST client with ADC/impersonation, quota header injection, and LRO polling."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable, Collection, Mapping
from typing import Any

import google.auth
import httpx
from google.auth import impersonated_credentials
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest

from manualground.core.rate_limiter import (
    DEFAULT_LIMITER_RPMS,
    TokenBucketLimiter,
    build_default_limiters,
)

CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


class GcpError(RuntimeError):
    """Base error for GCP REST operations."""


class GcpHttpError(GcpError):
    """Raised when an HTTP request fails after retries or violates expected status codes."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        response: httpx.Response | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class GcpLroError(GcpError):
    """Raised when a GCP long-running operation completes with an error payload."""

    def __init__(self, message: str, *, operation: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.operation = operation or {}


class GcpLroTimeoutError(GcpLroError, TimeoutError):
    """Raised when polling a GCP long-running operation exceeds timeout_s."""


class _DualMethod:
    """Descriptor allowing factory helpers to be called on either GcpRestClient or an instance."""

    def __init__(self, cls_fn: Callable[..., Any], inst_fn: Callable[..., Any]) -> None:
        self._cls_fn = cls_fn
        self._inst_fn = inst_fn

    def __get__(self, obj: Any, objtype: type[Any] | None = None) -> Callable[..., Any]:
        if obj is None:
            target_cls = objtype or GcpRestClient
            return lambda *args, **kwargs: self._cls_fn(target_cls, *args, **kwargs)
        return lambda *args, **kwargs: self._inst_fn(obj, *args, **kwargs)


class GcpRestClient:
    """Rate-limited REST client wrapping httpx.Client and Google Cloud credentials."""

    def __init__(
        self,
        quota_project: str = "",
        *,
        credentials: Credentials | None = None,
        bearer_token: str | None = None,
        transport: httpx.BaseTransport | None = None,
        http_client: httpx.Client | None = None,
        limiters: dict[str, TokenBucketLimiter] | None = None,
        rpm_overrides: Mapping[str, float] | None = None,
        serial_locks: dict[str, threading.RLock] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
        max_retries: int = 4,
        base_backoff_s: float = 0.5,
        max_backoff_s: float = 16.0,
        jitter_ratio: float = 0.25,
        timeout_s: float = 60.0,
    ) -> None:
        self.quota_project = quota_project
        self._credentials = credentials
        self._bearer_token = bearer_token
        self._transport = transport
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(transport=transport, timeout=timeout_s)
        self._clock = clock
        self._sleep = sleep
        self._rng = rng
        self._max_retries = max_retries
        self._base_backoff_s = base_backoff_s
        self._max_backoff_s = max_backoff_s
        self._jitter_ratio = jitter_ratio
        self._timeout_s = timeout_s
        self._auth_lock = threading.Lock()
        self._limiter_lock = threading.Lock()
        self._limiters = (
            dict(limiters)
            if limiters is not None
            else build_default_limiters(clock=clock, sleep=sleep, overrides=rpm_overrides)
        )
        self._serial_locks = (
            serial_locks
            if serial_locks is not None
            else {"sql_admin": threading.RLock()}
        )

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> GcpRestClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _cls_with_token(
        cls: type[GcpRestClient],
        bearer_token: str,
        quota_project: str = "",
        **kwargs: Any,
    ) -> GcpRestClient:
        return cls(quota_project=quota_project, bearer_token=bearer_token, **kwargs)

    def _inst_with_token(
        self,
        bearer_token: str,
        quota_project: str | None = None,
        **kwargs: Any,
    ) -> GcpRestClient:
        qp = self.quota_project if quota_project is None else quota_project
        return GcpRestClient(
            quota_project=qp,
            bearer_token=bearer_token,
            transport=kwargs.pop("transport", self._transport),
            http_client=kwargs.pop("http_client", None if self._transport is not None else self._http),
            limiters=kwargs.pop("limiters", self._limiters),
            serial_locks=kwargs.pop("serial_locks", self._serial_locks),
            clock=kwargs.pop("clock", self._clock),
            sleep=kwargs.pop("sleep", self._sleep),
            rng=kwargs.pop("rng", self._rng),
            max_retries=kwargs.pop("max_retries", self._max_retries),
            base_backoff_s=kwargs.pop("base_backoff_s", self._base_backoff_s),
            max_backoff_s=kwargs.pop("max_backoff_s", self._max_backoff_s),
            jitter_ratio=kwargs.pop("jitter_ratio", self._jitter_ratio),
            timeout_s=kwargs.pop("timeout_s", self._timeout_s),
            **kwargs,
        )

    with_token = _DualMethod(_cls_with_token, _inst_with_token)

    def _cls_for_impersonated_sa(
        cls: type[GcpRestClient],
        sa_email: str,
        quota_project: str = "",
        *,
        source_credentials: Credentials | None = None,
        target_scopes: list[str] | None = None,
        lifetime: int = 3600,
        **kwargs: Any,
    ) -> GcpRestClient:
        scopes = target_scopes or [CLOUD_PLATFORM_SCOPE]
        if source_credentials is None:
            source_credentials, _ = google.auth.default(scopes=scopes)
        imp_creds = impersonated_credentials.Credentials(
            source_credentials=source_credentials,
            target_principal=sa_email,
            target_scopes=scopes,
            lifetime=lifetime,
        )
        return cls(quota_project=quota_project, credentials=imp_creds, **kwargs)

    def _inst_for_impersonated_sa(
        self,
        sa_email: str,
        quota_project: str | None = None,
        *,
        source_credentials: Credentials | None = None,
        target_scopes: list[str] | None = None,
        lifetime: int = 3600,
        **kwargs: Any,
    ) -> GcpRestClient:
        qp = self.quota_project if quota_project is None else quota_project
        if self._transport is not None and source_credentials is None and self._credentials is None:
            return self._inst_with_token(
                f"mock-impersonated-{sa_email}",
                quota_project=qp,
                **kwargs,
            )
        scopes = target_scopes or [CLOUD_PLATFORM_SCOPE]
        src_creds = source_credentials or self._credentials
        if src_creds is None:
            src_creds, _ = google.auth.default(scopes=scopes)
        imp_creds = impersonated_credentials.Credentials(
            source_credentials=src_creds,
            target_principal=sa_email,
            target_scopes=scopes,
            lifetime=lifetime,
        )
        return GcpRestClient(
            quota_project=qp,
            credentials=imp_creds,
            transport=kwargs.pop("transport", self._transport),
            limiters=kwargs.pop("limiters", self._limiters),
            serial_locks=kwargs.pop("serial_locks", self._serial_locks),
            clock=kwargs.pop("clock", self._clock),
            sleep=kwargs.pop("sleep", self._sleep),
            rng=kwargs.pop("rng", self._rng),
            max_retries=kwargs.pop("max_retries", self._max_retries),
            base_backoff_s=kwargs.pop("base_backoff_s", self._base_backoff_s),
            max_backoff_s=kwargs.pop("max_backoff_s", self._max_backoff_s),
            jitter_ratio=kwargs.pop("jitter_ratio", self._jitter_ratio),
            timeout_s=kwargs.pop("timeout_s", self._timeout_s),
            **kwargs,
        )

    for_impersonated_sa = _DualMethod(_cls_for_impersonated_sa, _inst_for_impersonated_sa)

    def get_limiter(self, limiter_name: str) -> TokenBucketLimiter:
        with self._limiter_lock:
            limiter = self._limiters.get(limiter_name)
            if limiter is None:
                rpm = DEFAULT_LIMITER_RPMS.get(limiter_name, DEFAULT_LIMITER_RPMS["default"])
                limiter = TokenBucketLimiter(rpm=rpm, clock=self._clock, sleep=self._sleep)
                self._limiters[limiter_name] = limiter
            return limiter

    def serial_lock(self, name: str = "sql_admin") -> threading.RLock:
        """Return a re-entrant concurrency=1 lock for serialized endpoints such as Cloud SQL Admin."""
        with self._limiter_lock:
            lock = self._serial_locks.get(name)
            if lock is None:
                lock = threading.RLock()
                self._serial_locks[name] = lock
            return lock

    def _get_bearer_token(self) -> str:
        if self._bearer_token is not None:
            return self._bearer_token
        if self._credentials is None and self._transport is not None:
            return "mock-bearer-token"
        with self._auth_lock:
            if self._credentials is None:
                self._credentials, _ = google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
            if not self._credentials.valid or not self._credentials.token:
                self._credentials.refresh(GoogleAuthRequest())
            token = self._credentials.token
            if not token:
                raise GcpError("Google credentials refresh did not produce an access token.")
            return str(token)

    def _compute_backoff(self, attempt: int, response: httpx.Response | None = None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    parsed = float(retry_after)
                    if parsed > 0:
                        return min(self._max_backoff_s, parsed)
                except ValueError:
                    pass
        exp = min(self._max_backoff_s, self._base_backoff_s * (2**attempt))
        jitter = self._rng() * (self._jitter_ratio * self._base_backoff_s)
        return exp + jitter

    def request(
        self,
        method: str,
        url: str,
        *,
        limiter_name: str = "default",
        limiter: str | None = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        content: bytes | str | None = None,
        data: Any = None,
        headers: Mapping[str, str] | None = None,
        expected_statuses: Collection[int] | None = None,
        raise_for_status: bool = False,
        timeout_s: float | None = None,
    ) -> httpx.Response:
        """Execute a rate-limited HTTP request with exponential backoff on transient failures."""
        effective_limiter = limiter or limiter_name
        req_headers: dict[str, str] = {
            "Authorization": f"Bearer {self._get_bearer_token()}",
        }
        if self.quota_project:
            req_headers["X-Goog-User-Project"] = self.quota_project
        if headers:
            req_headers.update(headers)

        lock_ctx = (
            self.serial_lock("sql_admin")
            if effective_limiter == "sql_admin"
            else None
        )

        def _dispatch() -> httpx.Response:
            self.get_limiter(effective_limiter).acquire()
            last_exc: Exception | None = None
            resp: httpx.Response | None = None

            for attempt in range(self._max_retries + 1):
                try:
                    resp = self._http.request(
                        method=method.upper(),
                        url=url,
                        params=params,
                        json=json,
                        content=content,
                        data=data,
                        headers=req_headers,
                        timeout=timeout_s if timeout_s is not None else self._timeout_s,
                    )
                except httpx.TransportError as exc:
                    last_exc = exc
                    if attempt >= self._max_retries:
                        raise GcpHttpError(
                            f"Transport error on {method.upper()} {url}: {exc}"
                        ) from exc
                    self._sleep(self._compute_backoff(attempt))
                    continue

                if (
                    resp.status_code in RETRYABLE_STATUS_CODES
                    and attempt < self._max_retries
                ):
                    self._sleep(self._compute_backoff(attempt, response=resp))
                    continue

                break

            assert resp is not None
            if expected_statuses is not None and resp.status_code not in expected_statuses:
                raise GcpHttpError(
                    f"Unexpected HTTP {resp.status_code} for {method.upper()} {url}: "
                    f"{resp.text[:500]}",
                    status_code=resp.status_code,
                    response=resp,
                )
            if raise_for_status and resp.status_code >= 400:
                raise GcpHttpError(
                    f"HTTP {resp.status_code} for {method.upper()} {url}: {resp.text[:500]}",
                    status_code=resp.status_code,
                    response=resp,
                )
            return resp

        if lock_ctx is not None:
            with lock_ctx:
                return _dispatch()
        return _dispatch()

    def get(
        self,
        url: str,
        *,
        limiter_name: str = "default",
        limiter: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        return self.request("GET", url, limiter_name=limiter_name, limiter=limiter, **kwargs)

    def post(
        self,
        url: str,
        *,
        limiter_name: str = "default",
        limiter: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        return self.request("POST", url, limiter_name=limiter_name, limiter=limiter, **kwargs)

    def put(
        self,
        url: str,
        *,
        limiter_name: str = "default",
        limiter: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        return self.request("PUT", url, limiter_name=limiter_name, limiter=limiter, **kwargs)

    def patch(
        self,
        url: str,
        *,
        limiter_name: str = "default",
        limiter: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        return self.request("PATCH", url, limiter_name=limiter_name, limiter=limiter, **kwargs)

    def delete(
        self,
        url: str,
        *,
        limiter_name: str = "default",
        limiter: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        return self.request("DELETE", url, limiter_name=limiter_name, limiter=limiter, **kwargs)

    def poll_lro(
        self,
        url: str,
        limiter_name: str = "default",
        timeout_s: float = 180.0,
        interval_s: float = 2.0,
        *,
        base_url: str = "",
    ) -> dict[str, Any]:
        """Poll a GCP long-running operation (google.longrunning or Cloud SQL Admin) until done."""
        full_url = (
            url
            if url.startswith(("http://", "https://"))
            else f"{base_url.rstrip('/')}/{url.lstrip('/')}"
        )
        lock_ctx = (
            self.serial_lock("sql_admin")
            if limiter_name == "sql_admin"
            else None
        )

        def _poll() -> dict[str, Any]:
            deadline = self._clock() + timeout_s
            while True:
                resp = self.get(full_url, limiter_name=limiter_name)
                if resp.status_code >= 400:
                    raise GcpHttpError(
                        f"Failed polling operation {full_url} (HTTP {resp.status_code}): "
                        f"{resp.text[:500]}",
                        status_code=resp.status_code,
                        response=resp,
                    )
                payload: dict[str, Any] = resp.json() if resp.content else {}
                is_done = bool(
                    payload.get("done") is True or payload.get("status") == "DONE"
                )
                if is_done:
                    err = payload.get("error")
                    if isinstance(err, dict) and (
                        err.get("code") or err.get("message") or err.get("errors")
                    ):
                        raise GcpLroError(
                            f"Operation {full_url} failed: {err}",
                            operation=payload,
                        )
                    return payload

                now = self._clock()
                if now >= deadline:
                    raise GcpLroTimeoutError(
                        f"Timed out after {timeout_s}s waiting for operation {full_url}",
                        operation=payload,
                    )
                self._sleep(min(interval_s, max(0.01, deadline - now)))

        if lock_ctx is not None:
            with lock_ctx:
                return _poll()
        return _poll()
