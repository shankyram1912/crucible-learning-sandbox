"""Thread-safe token-bucket RPM rate limiters for GCP API pacing."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping

DEFAULT_LIMITER_RPMS: dict[str, float] = {
    "iam": 45.0,
    "storage_bucket": 24.0,
    "storage_iam": 60.0,
    "artifact_registry": 25.0,
    "cloud_run": 30.0,
    "sql_admin": 20.0,
    "firestore_admin": 15.0,
    "discovery_engine": 15.0,
    "import_documents": 5.0,
    "discovery_import": 5.0,
    "crm_iam": 15.0,
    "vertex_ai": 60.0,
    "default": 60.0,
}


class TokenBucketLimiter:
    """Thread-safe token-bucket rate limiter enforcing exact 60/rpm spacing at burst=1."""

    def __init__(
        self,
        rpm: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        burst: int = 1,
    ) -> None:
        if rpm <= 0:
            raise ValueError(f"rpm must be positive, got {rpm}")
        if burst < 1:
            raise ValueError(f"burst must be >= 1, got {burst}")
        self._rpm = float(rpm)
        self._interval = 60.0 / self._rpm
        self._burst = int(burst)
        self._capacity = float(burst)
        self._tokens = float(burst)
        self._last_refill: float | None = None
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()

    @property
    def rpm(self) -> float:
        return self._rpm

    @property
    def interval_s(self) -> float:
        return self._interval

    @property
    def burst(self) -> int:
        return self._burst

    def acquire(self) -> float:
        """Acquire one request slot, sleeping if needed, and return seconds waited."""
        with self._lock:
            now = self._clock()
            if self._last_refill is None:
                self._last_refill = now
            else:
                elapsed = max(0.0, now - self._last_refill)
                self._tokens = min(
                    self._capacity,
                    self._tokens + (elapsed / self._interval),
                )
                self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                wait_s = 0.0
            else:
                deficit = 1.0 - self._tokens
                wait_s = deficit * self._interval
                self._tokens -= 1.0

        if wait_s > 0.0:
            self._sleep(wait_s)
        return wait_s


def build_default_limiters(
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    overrides: Mapping[str, float] | None = None,
) -> dict[str, TokenBucketLimiter]:
    """Construct the standard named GCP API limiters for a ManualGround shard."""
    rpms = dict(DEFAULT_LIMITER_RPMS)
    if overrides:
        rpms.update(overrides)
    return {
        name: TokenBucketLimiter(rpm=rpm, clock=clock, sleep=sleep)
        for name, rpm in rpms.items()
    }
