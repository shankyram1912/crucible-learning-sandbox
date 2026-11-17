"""Shared pytest fixtures, deterministic fake clock, and HTTP mock router for ManualGround."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import threading
from typing import Any

import httpx
import pytest


MG_ROOT = Path(__file__).resolve().parent.parent


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers so pytest runs cleanly with strict markers."""
    config.addinivalue_line(
        "markers",
        "e2e: live cross-student isolation verification against a real GCP shard (requires MG_LIVE_E2E=1)",
    )


class FakeClock:
    """Thread-safe deterministic monotonic clock + fake sleep recorder (zero wall-clock delay)."""

    def __init__(self, initial: float = 1000.0) -> None:
        self._now = initial
        self._lock = threading.Lock()
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        with self._lock:
            return self._now

    def monotonic(self) -> float:
        return self()

    def sleep(self, seconds: float) -> None:
        with self._lock:
            dt = max(0.0, float(seconds))
            self.sleeps.append(dt)
            self._now += dt

    def advance(self, seconds: float) -> float:
        with self._lock:
            self._now += float(seconds)
            return self._now

    @property
    def now(self) -> float:
        return self()


HandlerReturn = httpx.Response | tuple[int, Any] | Callable[[httpx.Request], httpx.Response | tuple[int, Any]]


@dataclass
class RecordedRequest:
    """Captured HTTP request with pre-parsed JSON payload when applicable."""

    method: str
    url: str
    headers: dict[str, str]
    body_text: str
    json_body: Any = None


@dataclass
class _RouteRule:
    method: str
    pattern: re.Pattern[str]
    responses: list[HandlerReturn] = field(default_factory=list)
    call_count: int = 0


class MockGcpRouter:
    """Deterministic regex/substring HTTP router wrapping ``httpx.MockTransport``."""

    def __init__(self) -> None:
        self._rules: list[_RouteRule] = []
        self.requests: list[RecordedRequest] = []
        self._lock = threading.Lock()
        self.fallback: Callable[[httpx.Request], httpx.Response | tuple[int, Any]] | None = None

    def add(
        self,
        method: str,
        url_pattern: str,
        *responses: HandlerReturn,
        is_regex: bool = False,
    ) -> None:
        compiled = re.compile(url_pattern if is_regex else re.escape(url_pattern))
        self._rules.append(
            _RouteRule(
                method=method.upper(),
                pattern=compiled,
                responses=list(responses) if responses else [(200, {})],
            )
        )

    def add_regex(self, method: str, regex_pattern: str, *responses: HandlerReturn) -> None:
        self.add(method, regex_pattern, *responses, is_regex=True)

    @staticmethod
    def _coerce_response(item: httpx.Response | tuple[int, Any], request: httpx.Request) -> httpx.Response:
        if isinstance(item, httpx.Response):
            return item
        status_code, payload = item
        if isinstance(payload, (dict, list)):
            return httpx.Response(status_code=status_code, json=payload, request=request)
        if payload is None:
            return httpx.Response(status_code=status_code, content=b"", request=request)
        return httpx.Response(status_code=status_code, text=str(payload), request=request)

    def handle(self, request: httpx.Request) -> httpx.Response:
        raw_bytes = request.read()
        body_text = raw_bytes.decode("utf-8", errors="replace") if raw_bytes else ""
        parsed_json: Any = None
        if body_text:
            try:
                parsed_json = json.loads(body_text)
            except json.JSONDecodeError:
                parsed_json = None

        url_str = str(request.url)
        with self._lock:
            self.requests.append(
                RecordedRequest(
                    method=request.method.upper(),
                    url=url_str,
                    headers={k.lower(): v for k, v in request.headers.items()},
                    body_text=body_text,
                    json_body=parsed_json,
                )
            )
            matched: _RouteRule | None = None
            for rule in reversed(self._rules):
                if rule.method in (request.method.upper(), "*") and rule.pattern.search(url_str):
                    matched = rule
                    break

            if matched is not None:
                idx = min(matched.call_count, len(matched.responses) - 1)
                matched.call_count += 1
                chosen = matched.responses[idx]
            elif self.fallback is not None:
                chosen = self.fallback
            else:
                raise AssertionError(
                    f"Unmocked GCP HTTP call: {request.method} {url_str}\nBody: {body_text[:400]}"
                )

        if callable(chosen) and not isinstance(chosen, httpx.Response):
            out = chosen(request)
            return self._coerce_response(out, request)
        return self._coerce_response(chosen, request)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def gcp_router() -> MockGcpRouter:
    return MockGcpRouter()


@pytest.fixture
def mg_root() -> Path:
    return MG_ROOT
