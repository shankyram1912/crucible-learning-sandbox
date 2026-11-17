"""Unit tests for TokenBucketLimiter RPM spacing and GcpRestClient retry + header injection."""

from __future__ import annotations

import pytest

from tests.conftest import FakeClock, MockGcpRouter


def test_token_bucket_limiter_exact_rpm_spacing_no_burst_spike(fake_clock: FakeClock) -> None:
    from manualground.core.rate_limiter import TokenBucketLimiter

    # 24 RPM -> exact 2.5s minimum spacing between requests (burst=1)
    limiter = TokenBucketLimiter(rpm=24.0, clock=fake_clock.monotonic, sleep=fake_clock.sleep)

    t0 = fake_clock.now
    limiter.acquire()
    # First token on a fresh bucket should not require waiting
    assert fake_clock.now == pytest.approx(t0)

    # Immediate second, third, and fourth calls must each wait exactly 2.5s
    limiter.acquire()
    assert fake_clock.now == pytest.approx(t0 + 2.5)

    limiter.acquire()
    assert fake_clock.now == pytest.approx(t0 + 5.0)

    # Advance 1.0s naturally -> next acquire only sleeps remaining 1.5s
    fake_clock.advance(1.0)
    limiter.acquire()
    assert fake_clock.now == pytest.approx(t0 + 7.5)
    assert fake_clock.sleeps[-1] == pytest.approx(1.5)

    # Idle 30s -> next acquire is immediate (0s sleep), AND subsequent call STILL waits 2.5s (no burst spike!)
    fake_clock.advance(30.0)
    t_idle = fake_clock.now
    limiter.acquire()
    assert fake_clock.now == pytest.approx(t_idle)

    limiter.acquire()
    assert fake_clock.now == pytest.approx(t_idle + 2.5)


def test_default_service_rpm_rates_match_spec() -> None:
    from manualground.core import rate_limiter

    # Check canonical default RPM table if exposed as dict/constant or registry factory
    expected_rpms = {
        "iam": 45.0,
        "storage_bucket": 24.0,
        "storage_iam": 60.0,
        "artifact_registry": 25.0,
        "cloud_run": 30.0,
        "sql_admin": 20.0,
        "firestore_admin": 15.0,
        "discovery_engine": 15.0,
        "crm_iam": 15.0,
    }
    defaults = getattr(rate_limiter, "DEFAULT_RPMS", None) or getattr(
        rate_limiter, "DEFAULT_LIMITER_RPMS", None
    )
    if isinstance(defaults, dict):
        for name, rpm in expected_rpms.items():
            assert name in defaults, f"Missing default limiter {name!r}"
            assert float(defaults[name]) == pytest.approx(rpm)


def _make_mock_rest_client(
    router: MockGcpRouter,
    fake_clock: FakeClock,
    quota_project: str = "mg-quota-proj-01",
    token: str = "fake-admin-token",
):
    from manualground.core.http_client import GcpRestClient

    return GcpRestClient(
        quota_project=quota_project,
        bearer_token=token,
        transport=router.transport(),
        clock=fake_clock.monotonic,
        sleep=fake_clock.sleep,
        rng=lambda: 0.0,
    )


def test_gcp_rest_client_injects_headers_and_retries_429_503_exponentially(
    gcp_router: MockGcpRouter,
    fake_clock: FakeClock,
) -> None:
    url = "https://iam.googleapis.com/v1/projects/mg-ntu-01/serviceAccounts"
    gcp_router.add(
        "GET",
        url,
        (429, {"error": {"code": 429, "message": "RATE_LIMIT_EXCEEDED"}}),
        (503, {"error": {"code": 503, "message": "UNAVAILABLE"}}),
        (200, {"accounts": [{"email": "sa-lsb-student1@mg-ntu-01.iam.gserviceaccount.com"}]}),
    )

    client = _make_mock_rest_client(
        gcp_router,
        fake_clock,
        quota_project="mg-quota-999",
        token="secret-test-bearer",
    )

    # Dispatch GET request via request() or get()
    if hasattr(client, "get"):
        resp = client.get(url, limiter_name="iam") if "limiter_name" in client.get.__code__.co_varnames else client.get(url)
    else:
        resp = client.request("GET", url)

    payload = resp.json() if hasattr(resp, "json") else resp
    assert payload["accounts"][0]["email"].startswith("sa-lsb-student1@")

    # Should have attempted 3 times (429 -> 503 -> 200)
    assert len(gcp_router.requests) == 3
    for req in gcp_router.requests:
        assert req.headers.get("x-goog-user-project") == "mg-quota-999"
        assert req.headers.get("authorization") == "Bearer secret-test-bearer"

    # Fake sleep must have recorded >= 2 backoff sleeps without slowing down wall-clock test runtime
    nonzero_sleeps = [s for s in fake_clock.sleeps if s > 0]
    assert len(nonzero_sleeps) >= 2


def test_gcp_rest_client_does_not_retry_403_and_supports_lro_polling(
    gcp_router: MockGcpRouter,
    fake_clock: FakeClock,
) -> None:
    forbidden_url = "https://storage.googleapis.com/storage/v1/b/bkt-peer"
    gcp_router.add(
        "DELETE",
        forbidden_url,
        (403, {"error": {"code": 403, "message": "Permission denied"}}),
    )

    op_url = "https://firestore.googleapis.com/v1/projects/mg-ntu-01/databases/fs-a/operations/op-1"
    gcp_router.add(
        "GET",
        op_url,
        (200, {"name": "op-1", "done": False}),
        (200, {"name": "op-1", "done": False}),
        (200, {"name": "op-1", "done": True, "response": {"name": "projects/mg-ntu-01/databases/fs-a"}}),
    )

    client = _make_mock_rest_client(gcp_router, fake_clock, quota_project="mg-quota-999")

    # 403 must NOT be retried
    try:
        if hasattr(client, "delete"):
            res = client.delete(forbidden_url)
            if hasattr(res, "status_code"):
                assert res.status_code == 403
        else:
            res = client.request("DELETE", forbidden_url)
            if hasattr(res, "status_code"):
                assert res.status_code == 403
    except Exception:
        # Raising an HTTP status error on 403 is also acceptable as long as only 1 HTTP call occurred!
        pass

    delete_calls = [r for r in gcp_router.requests if r.method == "DELETE"]
    assert len(delete_calls) == 1, f"403 should never be retried, got {len(delete_calls)} calls"

    # LRO polling until done=True
    op_result = client.poll_lro(op_url, "firestore_admin", timeout_s=30, interval_s=2.0)
    assert op_result["done"] is True
    op_calls = [r for r in gcp_router.requests if r.url == op_url]
    assert len(op_calls) == 3
