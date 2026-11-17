"""Unit tests for ProjectIamCoalescer: Policy v3, idempotent merge, 409 ETag retry, and quota guards."""

from __future__ import annotations

import inspect
import pytest

from tests.conftest import FakeClock, MockGcpRouter
from tests.unit.test_rate_limiter import _make_mock_rest_client


def _build_coalescer(client, project_id: str = "mg-ntu-01"):
    from manualground.core.iam_coalescer import ProjectIamCoalescer

    sig = inspect.signature(ProjectIamCoalescer.__init__)
    kwargs = {}
    for pname in sig.parameters:
        if pname == "self":
            continue
        if pname in ("client", "admin_client", "rest_client", "http_client"):
            kwargs[pname] = client
        elif pname == "project_id":
            kwargs[pname] = project_id
    return ProjectIamCoalescer(**kwargs)


def _add_specs(coalescer, specs) -> None:
    for method_name in ("add_bindings", "extend", "register_bindings"):
        fn = getattr(coalescer, method_name, None)
        if callable(fn):
            fn(specs)
            return
    for method_name in ("add", "add_binding", "register"):
        fn = getattr(coalescer, method_name, None)
        if callable(fn):
            for s in specs:
                fn(s)
            return
    raise AssertionError("ProjectIamCoalescer has no add/add_bindings method")


def _commit_coalescer(coalescer, project_id: str = "mg-ntu-01"):
    for method_name in ("commit", "apply", "flush", "execute"):
        fn = getattr(coalescer, method_name, None)
        if callable(fn):
            sig = inspect.signature(fn)
            if "project_id" in sig.parameters:
                return fn(project_id=project_id)
            return fn()
    raise AssertionError("ProjectIamCoalescer has no commit/apply method")


def test_coalescer_fetches_policy_v3_and_merges_idempotently(
    gcp_router: MockGcpRouter,
    fake_clock: FakeClock,
) -> None:
    from manualground.core.models import ConditionalBindingSpec

    project_id = "mg-ntu-01"
    existing_policy = {
        "version": 1,
        "etag": "BwXhInitial==",
        "bindings": [
            {
                "role": "roles/viewer",
                "members": ["user:admin@shankyram.altostrat.com"],
            },
            {
                "role": f"projects/{project_id}/roles/custom_ntu_firestore_db_user",
                "members": ["user:lsb-student1@shankyram.altostrat.com"],
                "condition": {
                    "title": "fs_lsb_student1",
                    "description": "Isolate fs-lsb-student1",
                    "expression": (
                        f'resource.type == "firestore.googleapis.com/Database" && '
                        f'resource.name == "projects/{project_id}/databases/fs-lsb-student1"'
                    ),
                },
            },
        ],
    }

    gcp_router.add_regex("POST", r":getIamPolicy$", (200, existing_policy))
    gcp_router.add_regex("POST", r":setIamPolicy$", lambda req: (200, json_from_set_iam(req)))

    captured_policies: list[dict] = []

    def json_from_set_iam(req):
        import json

        body = json.loads(req.read().decode("utf-8"))
        pol = body.get("policy", body)
        captured_policies.append(pol)
        return pol

    client = _make_mock_rest_client(gcp_router, fake_clock)
    coalescer = _build_coalescer(client, project_id=project_id)

    cond_s1 = (
        f'resource.type == "firestore.googleapis.com/Database" && '
        f'resource.name == "projects/{project_id}/databases/fs-lsb-student1"'
    )
    cond_s2 = (
        f'resource.type == "firestore.googleapis.com/Database" && '
        f'resource.name == "projects/{project_id}/databases/fs-lsb-student2"'
    )

    # Re-add existing user + new SA on student1 (must merge idempotently without duplicating student1 user!)
    # Plus add student2's isolated conditional binding + an unconditional group binding.
    _add_specs(
        coalescer,
        [
            ConditionalBindingSpec(
                role=f"projects/{project_id}/roles/custom_ntu_firestore_db_user",
                members=[
                    "user:lsb-student1@shankyram.altostrat.com",
                    f"serviceAccount:sa-lsb-student1@{project_id}.iam.gserviceaccount.com",
                ],
                condition_title="fs_lsb_student1",
                condition_expression=cond_s1,
                condition_description="Isolate fs-lsb-student1",
            ),
            ConditionalBindingSpec(
                role=f"projects/{project_id}/roles/custom_ntu_firestore_db_user",
                members=[
                    "user:lsb-student2@shankyram.altostrat.com",
                    f"serviceAccount:sa-lsb-student2@{project_id}.iam.gserviceaccount.com",
                ],
                condition_title="fs_lsb_student2",
                condition_expression=cond_s2,
                condition_description="Isolate fs-lsb-student2",
            ),
            ConditionalBindingSpec(
                role=f"projects/{project_id}/roles/custom_ntu_run_creator",
                members=["group:ntu-students@shankyram.altostrat.com"],
            ),
        ],
    )

    _commit_coalescer(coalescer, project_id=project_id)

    # Verify getIamPolicy requested policy version 3
    get_reqs = [r for r in gcp_router.requests if r.url.endswith(":getIamPolicy")]
    assert len(get_reqs) == 1
    assert get_reqs[0].json_body["options"]["requestedPolicyVersion"] == 3

    # Verify single setIamPolicy commit with version=3 and zero duplicate principals
    set_reqs = [r for r in gcp_router.requests if r.url.endswith(":setIamPolicy")]
    assert len(set_reqs) == 1
    committed = captured_policies[0]
    assert committed["version"] == 3

    s1_bindings = [
        b
        for b in committed["bindings"]
        if b.get("condition", {}).get("expression") == cond_s1
    ]
    assert len(s1_bindings) == 1
    assert sorted(s1_bindings[0]["members"]) == [
        f"serviceAccount:sa-lsb-student1@{project_id}.iam.gserviceaccount.com",
        "user:lsb-student1@shankyram.altostrat.com",
    ]


def test_coalescer_retries_on_409_etag_conflict_preserving_concurrent_binding(
    gcp_router: MockGcpRouter,
    fake_clock: FakeClock,
) -> None:
    from manualground.core.models import ConditionalBindingSpec

    project_id = "mg-ntu-01"
    pol_v1 = {
        "version": 3,
        "etag": "etag-1",
        "bindings": [{"role": "roles/viewer", "members": ["user:ops1@ntu.edu.sg"]}],
    }
    pol_v2_concurrent = {
        "version": 3,
        "etag": "etag-2",
        "bindings": [
            {"role": "roles/viewer", "members": ["user:ops1@ntu.edu.sg"]},
            {"role": "roles/browser", "members": ["user:concurrent-actor@ntu.edu.sg"]},
        ],
    }

    gcp_router.add_regex("POST", r":getIamPolicy$", (200, pol_v1), (200, pol_v2_concurrent))
    gcp_router.add_regex(
        "POST",
        r":setIamPolicy$",
        (409, {"error": {"code": 409, "status": "ABORTED", "message": "There were concurrent policy changes."}}),
        (200, {"version": 3, "etag": "etag-3", "bindings": []}),
    )

    client = _make_mock_rest_client(gcp_router, fake_clock)
    coalescer = _build_coalescer(client, project_id=project_id)
    _add_specs(
        coalescer,
        [
            ConditionalBindingSpec(
                role=f"projects/{project_id}/roles/custom_ntu_run_creator",
                members=["group:ntu-students@ntu.edu.sg"],
            )
        ],
    )

    _commit_coalescer(coalescer, project_id=project_id)

    get_reqs = [r for r in gcp_router.requests if r.url.endswith(":getIamPolicy")]
    set_reqs = [r for r in gcp_router.requests if r.url.endswith(":setIamPolicy")]
    assert len(get_reqs) == 2
    assert len(set_reqs) == 2

    second_policy = set_reqs[1].json_body.get("policy", set_reqs[1].json_body)
    assert second_policy["etag"] == "etag-2"
    roles_in_second = {b["role"] for b in second_policy["bindings"]}
    assert "roles/browser" in roles_in_second, "Re-fetch after 409 must preserve concurrent binding"
    assert f"projects/{project_id}/roles/custom_ntu_run_creator" in roles_in_second


def test_coalescer_raises_quota_budget_exceeded_above_1400_principals_or_95_conditions(
    gcp_router: MockGcpRouter,
    fake_clock: FakeClock,
) -> None:
    from manualground.core.iam_coalescer import QuotaBudgetExceededError
    from manualground.core.models import ConditionalBindingSpec

    project_id = "mg-ntu-01"
    gcp_router.add_regex(
        "POST",
        r":getIamPolicy$",
        (200, {"version": 3, "etag": "etag-ok", "bindings": []}),
        (200, {"version": 3, "etag": "etag-ok", "bindings": []}),
    )

    client = _make_mock_rest_client(gcp_router, fake_clock)

    # Case A: > 1,400 total principals across bindings -> must raise BEFORE setIamPolicy!
    c_principals = _build_coalescer(client, project_id=project_id)
    _add_specs(
        c_principals,
        [
            ConditionalBindingSpec(
                role="roles/viewer",
                members=[f"user:stu-{i:04d}@ntu.edu.sg" for i in range(1405)],
            )
        ],
    )
    with pytest.raises(QuotaBudgetExceededError):
        _commit_coalescer(c_principals, project_id=project_id)

    # Case B: > 95 conditional bindings -> must raise BEFORE setIamPolicy!
    c_conds = _build_coalescer(client, project_id=project_id)
    _add_specs(
        c_conds,
        [
            ConditionalBindingSpec(
                role=f"projects/{project_id}/roles/custom_ntu_firestore_db_user",
                members=[f"user:stu-{i:03d}@ntu.edu.sg"],
                condition_title=f"cond_{i}",
                condition_expression=f'resource.name == "projects/{project_id}/databases/fs-{i}"',
            )
            for i in range(96)
        ],
    )
    with pytest.raises(QuotaBudgetExceededError):
        _commit_coalescer(c_conds, project_id=project_id)

    # Confirm zero setIamPolicy calls were made!
    set_reqs = [r for r in gcp_router.requests if r.url.endswith(":setIamPolicy")]
    assert len(set_reqs) == 0
