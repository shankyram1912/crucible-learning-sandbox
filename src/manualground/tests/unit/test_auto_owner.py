"""Unit tests for terraform/03-cloud-run-auto-owner/auto_owner.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest


MG_ROOT = Path(__file__).resolve().parents[2]
AUTO_OWNER_PATH = MG_ROOT / "terraform" / "03-cloud-run-auto-owner" / "auto_owner.py"


def _load_auto_owner_module():
    assert AUTO_OWNER_PATH.is_file(), f"Missing {AUTO_OWNER_PATH}"
    mod_name = "mg_auto_owner_under_test"
    spec = importlib.util.spec_from_file_location(mod_name, AUTO_OWNER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeRunControlPlane:
    """In-memory Cloud Run v2 REST control plane plugged into CloudRunAdminClient(requester=...)."""

    def __init__(self, project_id: str = "mg-ntu-01", region: str = "asia-southeast1") -> None:
        self.project_id = project_id
        self.region = region
        self.services: dict[str, dict[str, Any]] = {
            "ntu-run-auto-owner": {
                "name": f"projects/{project_id}/locations/{region}/services/ntu-run-auto-owner",
                "creator": f"sa-ntu-provisioner@{project_id}.iam.gserviceaccount.com",
                "template": {"serviceAccount": f"sa-run-auto-owner@{project_id}.iam.gserviceaccount.com"},
                "labels": {},
            }
        }
        self.policies: dict[str, dict[str, Any]] = {
            "ntu-run-auto-owner": {"version": 3, "etag": "etag-sys", "bindings": []}
        }
        self.deleted_services: list[str] = []
        self.set_iam_calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_next_set_iam_409: bool = False

    def add_service(
        self,
        service_id: str,
        runtime_sa: str,
        owner_email: str | None = None,
        creator: str = "",
        labels: dict[str, str] | None = None,
    ) -> None:
        svc_full = f"projects/{self.project_id}/locations/{self.region}/services/{service_id}"
        self.services[service_id] = {
            "name": svc_full,
            "creator": creator or (owner_email or ""),
            "template": {
                "serviceAccount": runtime_sa,
            },
            "labels": labels or {},
        }
        bindings = []
        if owner_email:
            bindings.append(
                {
                    "role": f"projects/{self.project_id}/roles/custom_ntu_run_owner",
                    "members": [f"user:{owner_email}"],
                }
            )
        self.policies[service_id] = {
            "version": 3,
            "etag": f"etag-{service_id}-1",
            "bindings": bindings,
        }

    def requester(
        self,
        method: str,
        url: str,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        clean_url = url.split("?", 1)[0]
        method = method.upper()

        if clean_url.endswith(":getIamPolicy"):
            svc_id = clean_url.split("/services/", 1)[1].split(":", 1)[0]
            pol = self.policies.get(svc_id, {"version": 3, "etag": "etag-init", "bindings": []})
            return 200, json.loads(json.dumps(pol))

        if clean_url.endswith(":setIamPolicy"):
            svc_id = clean_url.split("/services/", 1)[1].split(":", 1)[0]
            if self.fail_next_set_iam_409:
                self.fail_next_set_iam_409 = False
                cur = self.policies.setdefault(svc_id, {"version": 3, "etag": "etag-1", "bindings": []})
                cur["etag"] = "etag-concurrent-2"
                cur["bindings"].append({"role": "roles/run.viewer", "members": ["user:auditor@ntu.edu.sg"]})
                return 409, {"error": {"code": 409, "status": "ABORTED", "message": "ETag conflict"}}

            body = json_body or {}
            pol = body.get("policy", body)
            pol["etag"] = "etag-committed"
            self.policies[svc_id] = json.loads(json.dumps(pol))
            self.set_iam_calls.append((svc_id, self.policies[svc_id]))
            return 200, self.policies[svc_id]

        if clean_url.endswith("/services") and method == "GET":
            return 200, {"services": list(self.services.values())}

        if "/services/" in clean_url:
            svc_id = clean_url.split("/services/", 1)[1].split("/", 1)[0]
            if method == "GET":
                if svc_id not in self.services:
                    return 404, {"error": {"code": 404, "message": "Not found"}}
                return 200, self.services[svc_id]
            if method == "DELETE":
                self.deleted_services.append(svc_id)
                self.services.pop(svc_id, None)
                return 200, {"name": f"operations/del-{svc_id}", "done": True}

        raise AssertionError(f"Unhandled auto_owner HTTP call: {method} {url}")


def _make_audit_cloudevent(
    method_name: str,
    resource_name: str,
    principal_email: str,
    service_account: str = "",
    structured_envelope: bool = False,
) -> dict[str, Any]:
    audit_payload: dict[str, Any] = {
        "protoPayload": {
            "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
            "serviceName": "run.googleapis.com",
            "methodName": method_name,
            "resourceName": resource_name,
            "authenticationInfo": {"principalEmail": principal_email},
            "request": {
                "service": {
                    "template": {
                        "serviceAccount": service_account,
                        "spec": {"serviceAccountName": service_account},
                    }
                }
            },
            "response": {
                "name": resource_name,
                "template": {"serviceAccount": service_account},
                "spec": {"template": {"spec": {"serviceAccountName": service_account}}},
            },
        },
        "resource": {
            "type": "cloud_run_revision",
            "labels": {
                "project_id": "mg-ntu-01",
                "location": "asia-southeast1",
                "service_name": resource_name.rsplit("/", 1)[-1],
            },
        },
    }
    if structured_envelope:
        return {
            "specversion": "1.0",
            "type": "google.cloud.audit.log.v1.written",
            "data": audit_payload,
        }
    return audit_payload


def _reconcile(
    mod: Any,
    event: dict[str, Any],
    cp: FakeRunControlPlane,
    max_services: int = 3,
):
    client = mod.CloudRunAdminClient(requester=cp.requester)
    cfg = mod.AutoOwnerConfig(
        project_id=cp.project_id,
        default_region=cp.region,
        auto_owner_service_name="ntu-run-auto-owner",
        max_services_per_student=max_services,
    )
    return mod.reconcile_cloudevent(event, client=client, config=cfg, sleep_fn=lambda _s: None)


def test_auto_owner_parses_v1_and_v2_createservice_and_grants_idempotent_owner_iam() -> None:
    mod = _load_auto_owner_module()
    cp = FakeRunControlPlane()

    # 1. Cloud Run v2 CreateService + 409 ETag conflict retry!
    cp.add_service(
        "app-v2",
        runtime_sa="sa-lsb-student1@mg-ntu-01.iam.gserviceaccount.com",
        creator="lsb-student1@shankyram.altostrat.com",
    )
    cp.fail_next_set_iam_409 = True

    ev_v2 = _make_audit_cloudevent(
        method_name="google.cloud.run.v2.Services.CreateService",
        resource_name="projects/mg-ntu-01/locations/asia-southeast1/services/app-v2",
        principal_email="lsb-student1@shankyram.altostrat.com",
        service_account="sa-lsb-student1@mg-ntu-01.iam.gserviceaccount.com",
    )
    res_v2 = _reconcile(mod, ev_v2, cp, max_services=3)
    assert res_v2.action == "BOUND_OWNER"
    assert "app-v2" not in cp.deleted_services

    pol_v2 = cp.policies["app-v2"]
    by_role = {b["role"]: b["members"] for b in pol_v2["bindings"]}
    assert "user:lsb-student1@shankyram.altostrat.com" in by_role["projects/mg-ntu-01/roles/custom_ntu_run_owner"]
    assert "user:lsb-student1@shankyram.altostrat.com" in by_role["roles/run.invoker"]
    assert (
        "serviceAccount:sa-lsb-student1@mg-ntu-01.iam.gserviceaccount.com"
        in by_role["roles/run.invoker"]
    )
    assert "user:auditor@ntu.edu.sg" in by_role.get("roles/run.viewer", [])

    # Re-delivering exact same event must return UNCHANGED with zero duplicate bindings or extra setIamPolicy!
    calls_before = len(cp.set_iam_calls)
    res_repeat = _reconcile(mod, ev_v2, cp, max_services=3)
    assert res_repeat.action == "UNCHANGED"
    assert len(cp.set_iam_calls) == calls_before

    # 2. Cloud Run v1 CreateService (namespaces/<project>/services/<name>, structured CloudEvent envelope)
    cp.add_service(
        "app-v1",
        runtime_sa="sa-lsb-student1@mg-ntu-01.iam.gserviceaccount.com",
        creator="lsb-student1@shankyram.altostrat.com",
    )
    ev_v1 = _make_audit_cloudevent(
        method_name="google.cloud.run.v1.Services.CreateService",
        resource_name="namespaces/mg-ntu-01/services/app-v1",
        principal_email="lsb-student1@shankyram.altostrat.com",
        service_account="sa-lsb-student1@mg-ntu-01.iam.gserviceaccount.com",
        structured_envelope=True,
    )
    res_v1 = _reconcile(mod, ev_v1, cp, max_services=3)
    assert res_v1.action == "BOUND_OWNER"
    by_role_v1 = {b["role"]: b["members"] for b in cp.policies["app-v1"]["bindings"]}
    assert "user:lsb-student1@shankyram.altostrat.com" in by_role_v1["projects/mg-ntu-01/roles/custom_ntu_run_owner"]


def test_auto_owner_ignores_system_sa_and_protects_self() -> None:
    mod = _load_auto_owner_module()
    cp = FakeRunControlPlane()

    # 1. Self-protection: ntu-run-auto-owner is NEVER modified or deleted
    ev_self = _make_audit_cloudevent(
        method_name="google.cloud.run.v2.Services.CreateService",
        resource_name="projects/mg-ntu-01/locations/asia-southeast1/services/ntu-run-auto-owner",
        principal_email="lsb-student1@shankyram.altostrat.com",
        service_account="sa-lsb-student2@mg-ntu-01.iam.gserviceaccount.com",
    )
    res_self = _reconcile(mod, ev_self, cp)
    assert res_self.action == "IGNORED_PROTECTED_SERVICE"
    assert "ntu-run-auto-owner" not in cp.deleted_services
    assert len(cp.set_iam_calls) == 0

    # 2. System / Admin / Provisioner SA principal is ignored cleanly
    cp.add_service(
        "sys-helper",
        runtime_sa="sa-run-auto-owner@mg-ntu-01.iam.gserviceaccount.com",
        creator="sa-ntu-provisioner@mg-ntu-01.iam.gserviceaccount.com",
    )
    ev_sys = _make_audit_cloudevent(
        method_name="google.cloud.run.v2.Services.CreateService",
        resource_name="projects/mg-ntu-01/locations/asia-southeast1/services/sys-helper",
        principal_email="sa-ntu-provisioner@mg-ntu-01.iam.gserviceaccount.com",
        service_account="sa-run-auto-owner@mg-ntu-01.iam.gserviceaccount.com",
    )
    res_sys = _reconcile(mod, ev_sys, cp)
    assert res_sys.action == "IGNORED_SYSTEM_PRINCIPAL"
    assert "sys-helper" not in cp.deleted_services
    assert len(cp.set_iam_calls) == 0


def test_auto_owner_rejects_and_deletes_cross_student_or_default_sa() -> None:
    mod = _load_auto_owner_module()
    cp = FakeRunControlPlane()

    # Student 1 attempts to deploy a service running as Student 2's SA (sa-lsb-student2)
    cp.add_service(
        "sneaky-cross-sa",
        runtime_sa="sa-lsb-student2@mg-ntu-01.iam.gserviceaccount.com",
        creator="lsb-student1@shankyram.altostrat.com",
    )
    ev_cross = _make_audit_cloudevent(
        method_name="google.cloud.run.v2.Services.CreateService",
        resource_name="projects/mg-ntu-01/locations/asia-southeast1/services/sneaky-cross-sa",
        principal_email="lsb-student1@shankyram.altostrat.com",
        service_account="sa-lsb-student2@mg-ntu-01.iam.gserviceaccount.com",
    )
    res = _reconcile(mod, ev_cross, cp)
    assert res.action == "DELETED_UNAUTHORIZED_SA"
    assert "sneaky-cross-sa" in cp.deleted_services
    assert len(cp.set_iam_calls) == 0


def test_auto_owner_enforces_max_services_per_student_auto_deleting_fourth_service() -> None:
    mod = _load_auto_owner_module()
    cp = FakeRunControlPlane()

    student_email = "lsb-student1@shankyram.altostrat.com"
    student_sa = "sa-lsb-student1@mg-ntu-01.iam.gserviceaccount.com"

    for idx in (1, 2, 3):
        cp.add_service(
            f"stu1-svc-{idx}",
            runtime_sa=student_sa,
            owner_email=student_email,
            creator=student_email,
        )

    # 4th service exceeds MAX_SERVICES_PER_STUDENT=3 -> auto-deleted!
    cp.add_service(
        "stu1-svc-4",
        runtime_sa=student_sa,
        creator=student_email,
    )
    ev_fourth = _make_audit_cloudevent(
        method_name="google.cloud.run.v2.Services.CreateService",
        resource_name="projects/mg-ntu-01/locations/asia-southeast1/services/stu1-svc-4",
        principal_email=student_email,
        service_account=student_sa,
    )
    res = _reconcile(mod, ev_fourth, cp, max_services=3)
    assert res.action == "DELETED_QUOTA_EXCEEDED"
    assert "stu1-svc-4" in cp.deleted_services
    assert {"stu1-svc-1", "stu1-svc-2", "stu1-svc-3"}.issubset(cp.services.keys())
    assert len(cp.set_iam_calls) == 0
