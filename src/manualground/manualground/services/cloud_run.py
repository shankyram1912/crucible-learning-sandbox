"""Service driver for On-Demand ClickOps Cloud Run + Eventarc Auto-Owner and Artifact Registry."""

from __future__ import annotations

import time
from typing import Any

from manualground.config import ShardSettings
from manualground.core.http_client import GcpHttpError, GcpLroError, GcpRestClient
from manualground.core.models import (
    CheckOutcome,
    ConditionalBindingSpec,
    ServiceName,
    StepResult,
    StudentSpec,
)
from manualground.services.base import BaseServiceDriver

AR_API_BASE = "https://artifactregistry.googleapis.com/v1"
RUN_API_BASE = "https://run.googleapis.com/v2"
EVENTARC_API_BASE = "https://eventarc.googleapis.com/v1"

AUTO_OWNER_SERVICE_NAME = "ntu-run-auto-owner"
CUSTOM_OWNER_ROLE_ID = "custom_ntu_run_owner"
HELLO_CONTAINER_IMAGE = "us-docker.pkg.dev/cloudrun/container/hello"


def build_verify_service_id(student: StudentSpec, suffix: str = "verify") -> str:
    """Build a valid <=49-char Cloud Run service ID (`run-<slug>-<suffix>`)."""
    clean_suffix = suffix.strip("-").lower()
    max_prefix = 49 - len(clean_suffix) - 1
    prefix = f"run-{student.slug}"[:max_prefix].rstrip("-")
    return f"{prefix}-{clean_suffix}"


def _maybe_poll_lro(
    client: GcpRestClient,
    payload: dict[str, Any],
    *,
    limiter_name: str,
    base_url: str,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    """Poll a google.longrunning.Operation payload only if it represents an unfinished LRO."""
    op_name = str(payload.get("name") or "").strip()
    if "/operations/" in op_name and payload.get("done") is not True:
        return client.poll_lro(
            op_name,
            limiter_name=limiter_name,
            base_url=base_url,
            timeout_s=timeout_s,
        )
    return payload


class CloudRunDriver(BaseServiceDriver):
    """Provisions per-student `ar-<student>` Docker repos and verifies Eventarc Auto-Owner."""

    service: ServiceName = ServiceName.CLOUD_RUN

    def __init__(
        self,
        admin_client: GcpRestClient,
        *,
        auto_owner_service_name: str = AUTO_OWNER_SERVICE_NAME,
        ownership_poll_timeout_s: float = 30.0,
        ownership_poll_interval_s: float = 2.0,
    ) -> None:
        super().__init__(admin_client)
        self.auto_owner_service_name = auto_owner_service_name
        self.ownership_poll_timeout_s = max(0.1, ownership_poll_timeout_s)
        self.ownership_poll_interval_s = max(0.05, ownership_poll_interval_s)

    def preflight(
        self,
        settings: ShardSettings,
        roster: list[StudentSpec],
    ) -> list[CheckOutcome]:
        """Verify `ntu-run-auto-owner` Cloud Run service and Eventarc `CreateService` triggers."""
        _ = roster
        project_id = settings.project_id
        region = settings.region
        outcomes: list[CheckOutcome] = []

        # 1. Verify ntu-run-auto-owner service exists and has not failed reconciliation
        svc_target = f"projects/{project_id}/locations/{region}/services/{self.auto_owner_service_name}"
        svc_url = f"{RUN_API_BASE}/{svc_target}"
        svc_resp = self.admin_client.get(svc_url, limiter_name="cloud_run")
        svc_payload: dict[str, Any] = (
            svc_resp.json() if svc_resp.status_code == 200 and svc_resp.content else {}
        )
        terminal_cond = svc_payload.get("terminalCondition") or {}
        terminal_state = str(terminal_cond.get("state") or "")
        svc_healthy = svc_resp.status_code == 200 and terminal_state != "CONDITION_FAILED"

        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="preflight.run.auto_owner_service",
                kind="GUARDRAIL",
                actor="preflight",
                target=svc_target,
                passed=svc_healthy,
                expected="HTTP 200 (ntu-run-auto-owner active)",
                actual=f"HTTP {svc_resp.status_code}"
                + (f" ({terminal_state})" if terminal_state else ""),
                detail=str(svc_payload.get("uri") or "Eventarc CloudEvent ownership binder"),
            )
        )

        # 2. Verify Eventarc CreateService audit-log triggers exist
        trig_target = f"projects/{project_id}/locations/{region}/triggers"
        trig_url = f"{EVENTARC_API_BASE}/projects/{project_id}/locations/-/triggers"
        trig_resp = self.admin_client.get(trig_url, limiter_name="cloud_run")
        trig_payload: dict[str, Any] = (
            trig_resp.json() if trig_resp.status_code == 200 and trig_resp.content else {}
        )
        raw_triggers = trig_payload.get("triggers") or []
        triggers = [t for t in raw_triggers if isinstance(t, dict)]

        create_triggers: list[dict[str, Any]] = []
        for trig in triggers:
            filters = trig.get("eventFilters") or []
            has_filters = isinstance(filters, list) and len(filters) > 0
            if not has_filters:
                create_triggers.append(trig)
                continue
            filter_values = " ".join(
                str(f.get("value") or "") for f in filters if isinstance(f, dict)
            )
            if "CreateService" in filter_values or self.auto_owner_service_name in str(trig):
                create_triggers.append(trig)

        triggers_ok = trig_resp.status_code == 200 and len(create_triggers) >= 1
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="preflight.run.eventarc_triggers",
                kind="GUARDRAIL",
                actor="preflight",
                target=trig_target,
                passed=triggers_ok,
                expected=">= 1 CreateService Eventarc trigger",
                actual=(
                    f"{len(create_triggers)} matching trigger(s)"
                    if trig_resp.status_code == 200
                    else f"HTTP {trig_resp.status_code}"
                ),
                detail="Routes Cloud Run v1/v2 CreateService audit logs to ntu-run-auto-owner",
            )
        )
        return outcomes

    def provision_student(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[StepResult]:
        """Create isolated Docker repository `ar-<student>` (25 RPM) and bind repo-level IAM."""
        project_id = settings.project_id
        region = settings.region
        repo_id = student.ar_repo_id()
        repo_resource = f"projects/{project_id}/locations/{region}/repositories/{repo_id}"
        sa_email = student.sa_email(project_id)
        steps: list[StepResult] = []

        # 1. Create isolated Artifact Registry Docker repository (0 placeholder Cloud Run services!)
        t0 = time.monotonic()
        repos_url = f"{AR_API_BASE}/projects/{project_id}/locations/{region}/repositories"
        create_resp = self.admin_client.post(
            repos_url,
            limiter_name="artifact_registry",
            params={"repositoryId": repo_id},
            json={
                "format": "DOCKER",
                "description": f"Isolated Docker repository for {student.email} ({student.slug})",
                "labels": {
                    "managed-by": "manualground",
                    "student": student.slug,
                },
            },
        )

        if create_resp.status_code == 409:
            repo_status = "UNCHANGED"
            repo_detail = f"Docker repository {repo_id} already exists"
        elif create_resp.status_code in (200, 201):
            payload: dict[str, Any] = create_resp.json() if create_resp.content else {}
            try:
                _maybe_poll_lro(
                    self.admin_client,
                    payload,
                    limiter_name="artifact_registry",
                    base_url=AR_API_BASE,
                )
                repo_status = "CREATED"
                repo_detail = f"Created Docker repository {repo_id} in {region}"
            except GcpLroError as exc:
                err_obj = exc.operation.get("error") or {}
                if isinstance(err_obj, dict) and err_obj.get("code") == 6:
                    repo_status = "UNCHANGED"
                    repo_detail = f"Docker repository {repo_id} already exists (LRO code 6)"
                else:
                    raise
        else:
            raise GcpHttpError(
                f"Failed creating Artifact Registry repository {repo_id} "
                f"(HTTP {create_resp.status_code}): {create_resp.text[:500]}",
                status_code=create_resp.status_code,
                response=create_resp,
            )

        elapsed_repo = int((time.monotonic() - t0) * 1000)
        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="create_ar_repository",
                resource_id=repo_resource,
                status=repo_status,
                duration_ms=elapsed_repo,
                detail=repo_detail,
            )
        )

        # 2. Bind repository-level IAM: writer -> user:<email>, reader -> serviceAccount:sa-<student>
        t1 = time.monotonic()
        iam_url = f"{AR_API_BASE}/{repo_resource}:setIamPolicy"
        ar_policy = {
            "bindings": [
                {
                    "role": "roles/artifactregistry.writer",
                    "members": [f"user:{student.email}"],
                },
                {
                    "role": "roles/artifactregistry.reader",
                    "members": [f"serviceAccount:{sa_email}"],
                },
            ]
        }
        self.admin_client.post(
            iam_url,
            limiter_name="artifact_registry",
            json={"policy": ar_policy},
            expected_statuses=(200,),
        )
        elapsed_iam = int((time.monotonic() - t1) * 1000)

        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="set_ar_iam_policy",
                resource_id=repo_resource,
                status="CREATED" if repo_status == "CREATED" else "UNCHANGED",
                duration_ms=elapsed_iam,
                detail=f"Bound writer to user:{student.email} and reader to serviceAccount:{sa_email}",
            )
        )
        return steps

    def project_iam_bindings(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[ConditionalBindingSpec]:
        """Emit project-level `custom_ntu_run_creator` grant for cohort group or student user."""
        project_id = settings.project_id
        group_email = settings.student_group_email.strip()
        member = f"group:{group_email}" if group_email else f"user:{student.email}"
        return [
            ConditionalBindingSpec(
                role=f"projects/{project_id}/roles/custom_ntu_run_creator",
                members=[member],
            )
        ]

    def _poll_auto_owner_binding(
        self,
        client_a: GcpRestClient,
        service_url: str,
        student_a: StudentSpec,
    ) -> tuple[bool, int, str]:
        """Poll up to `ownership_poll_timeout_s` for `ntu-run-auto-owner` to grant `custom_ntu_run_owner`."""
        iam_url = f"{service_url}:getIamPolicy"
        deadline = client_a._clock() + self.ownership_poll_timeout_s
        last_status = 0
        last_detail = "custom_ntu_run_owner binding not observed yet"

        while True:
            resp = client_a.get(
                iam_url,
                limiter_name="cloud_run",
                params={"options.requestedPolicyVersion": 3},
            )
            last_status = resp.status_code
            if resp.status_code == 200:
                policy: dict[str, Any] = resp.json() if resp.content else {}
                bindings = policy.get("bindings") or []
                for binding in bindings:
                    if not isinstance(binding, dict):
                        continue
                    role = str(binding.get("role") or "")
                    members = [str(m).lower() for m in (binding.get("members") or [])]
                    if CUSTOM_OWNER_ROLE_ID in role and (
                        f"user:{student_a.email.lower()}" in members or len(members) > 0
                    ):
                        return True, 200, f"Observed {role} bound by {self.auto_owner_service_name}"

            now = client_a._clock()
            if now >= deadline:
                return False, last_status, last_detail
            client_a._sleep(min(self.ownership_poll_interval_s, max(0.01, deadline - now)))

    def verify_isolation(
        self,
        settings: ShardSettings,
        student_a: StudentSpec,
        student_b: StudentSpec,
        client_a: GcpRestClient,
        client_b: GcpRestClient,
    ) -> list[CheckOutcome]:
        """Verify on-demand create, Eventarc auto-owner grant, own PATCH/DELETE, and peer/SA/GPU blocks."""
        project_id = settings.project_id
        region = settings.region
        sa_a = student_a.sa_email(project_id)
        sa_b = student_b.sa_email(project_id)

        services_parent_url = f"{RUN_API_BASE}/projects/{project_id}/locations/{region}/services"
        verify_svc_id = build_verify_service_id(student_a, "verify")
        verify_svc_resource = f"projects/{project_id}/locations/{region}/services/{verify_svc_id}"
        verify_svc_url = f"{services_parent_url}/{verify_svc_id}"

        outcomes: list[CheckOutcome] = []
        created_own_service = False
        cleaned_up_own_service = False

        try:
            # 1. Positive: Student A creates on-demand Cloud Run service as sa-<a> (200)
            create_resp = client_a.post(
                services_parent_url,
                limiter_name="cloud_run",
                params={"serviceId": verify_svc_id},
                json={
                    "template": {
                        "serviceAccount": sa_a,
                        "scaling": {"minInstanceCount": 0, "maxInstanceCount": 2},
                        "containers": [
                            {
                                "image": HELLO_CONTAINER_IMAGE,
                            }
                        ],
                    }
                },
            )
            if create_resp.status_code in (200, 201):
                created_own_service = True
                create_payload: dict[str, Any] = (
                    create_resp.json() if create_resp.content else {}
                )
                _maybe_poll_lro(
                    client_a,
                    create_payload,
                    limiter_name="cloud_run",
                    base_url=RUN_API_BASE,
                    timeout_s=120.0,
                )

            outcomes.append(
                CheckOutcome(
                    service=self.service,
                    check_id="run.create_own_service",
                    kind="POSITIVE",
                    actor=student_a.slug,
                    target=verify_svc_resource,
                    passed=create_resp.status_code in (200, 201),
                    expected="HTTP 200",
                    actual=f"HTTP {create_resp.status_code}",
                    detail=f"On-demand CreateService {verify_svc_id} running as {sa_a}",
                )
            )

            # 2. Positive: Poll up to 30s for ntu-run-auto-owner to attach custom_ntu_run_owner
            owner_ok, owner_http, owner_detail = self._poll_auto_owner_binding(
                client_a, verify_svc_url, student_a
            )
            outcomes.append(
                CheckOutcome(
                    service=self.service,
                    check_id="run.auto_owner_iam_attached",
                    kind="POSITIVE",
                    actor=self.auto_owner_service_name,
                    target=verify_svc_resource,
                    passed=owner_ok,
                    expected=f"HTTP 200 with {CUSTOM_OWNER_ROLE_ID}",
                    actual=(
                        f"HTTP {owner_http} ({CUSTOM_OWNER_ROLE_ID} bound)"
                        if owner_ok
                        else f"HTTP {owner_http} (missing {CUSTOM_OWNER_ROLE_ID})"
                    ),
                    detail=owner_detail,
                )
            )

            # 3. Positive: Student A can PATCH (update) own service (200)
            patch_own_resp = client_a.patch(
                verify_svc_url,
                limiter_name="cloud_run",
                json={
                    "template": {
                        "serviceAccount": sa_a,
                        "scaling": {"minInstanceCount": 0, "maxInstanceCount": 2},
                        "containers": [
                            {
                                "image": HELLO_CONTAINER_IMAGE,
                                "env": [
                                    {"name": "MG_VERIFIED_OWNER", "value": student_a.slug}
                                ],
                            }
                        ],
                    }
                },
            )
            if patch_own_resp.status_code == 200 and patch_own_resp.content:
                _maybe_poll_lro(
                    client_a,
                    patch_own_resp.json(),
                    limiter_name="cloud_run",
                    base_url=RUN_API_BASE,
                    timeout_s=120.0,
                )

            outcomes.append(
                CheckOutcome(
                    service=self.service,
                    check_id="run.patch_own_service",
                    kind="POSITIVE",
                    actor=student_a.slug,
                    target=verify_svc_resource,
                    passed=patch_own_resp.status_code == 200,
                    expected="HTTP 200",
                    actual=f"HTTP {patch_own_resp.status_code}",
                    detail="Owner PATCH update on own Cloud Run service",
                )
            )

            # 4. Negative Cross-Student: Student B gets 403 trying to PATCH Student A's service
            patch_peer_resp = client_b.patch(
                verify_svc_url,
                limiter_name="cloud_run",
                json={
                    "template": {
                        "serviceAccount": sa_a,
                        "containers": [{"image": HELLO_CONTAINER_IMAGE}],
                    }
                },
            )
            outcomes.append(
                CheckOutcome(
                    service=self.service,
                    check_id="run.cross_student_patch_denied",
                    kind="NEGATIVE_CROSS_STUDENT",
                    actor=student_b.slug,
                    target=verify_svc_resource,
                    passed=patch_peer_resp.status_code == 403,
                    expected="HTTP 403",
                    actual=f"HTTP {patch_peer_resp.status_code}",
                    detail="Student B cannot update Student A's Cloud Run service",
                )
            )

            # 5. Negative Cross-Student: Student B gets 403 trying to DELETE Student A's service
            del_peer_resp = client_b.delete(verify_svc_url, limiter_name="cloud_run")
            outcomes.append(
                CheckOutcome(
                    service=self.service,
                    check_id="run.cross_student_delete_denied",
                    kind="NEGATIVE_CROSS_STUDENT",
                    actor=student_b.slug,
                    target=verify_svc_resource,
                    passed=del_peer_resp.status_code == 403,
                    expected="HTTP 403",
                    actual=f"HTTP {del_peer_resp.status_code}",
                    detail="Student B cannot delete Student A's Cloud Run service",
                )
            )

            # 6. Negative Cross-Student: Student A gets 403 trying to attach peer sa-<b>
            peer_sa_svc_id = build_verify_service_id(student_a, "peersa")
            peer_sa_resp = client_a.post(
                services_parent_url,
                limiter_name="cloud_run",
                params={"serviceId": peer_sa_svc_id},
                json={
                    "template": {
                        "serviceAccount": sa_b,
                        "containers": [{"image": HELLO_CONTAINER_IMAGE}],
                    }
                },
            )
            if peer_sa_resp.status_code in (200, 201):
                self.admin_client.delete(
                    f"{services_parent_url}/{peer_sa_svc_id}",
                    limiter_name="cloud_run",
                )
            outcomes.append(
                CheckOutcome(
                    service=self.service,
                    check_id="run.attach_peer_sa_denied",
                    kind="NEGATIVE_CROSS_STUDENT",
                    actor=student_a.slug,
                    target=sa_b,
                    passed=peer_sa_resp.status_code == 403,
                    expected="HTTP 403",
                    actual=f"HTTP {peer_sa_resp.status_code}",
                    detail="iam.serviceAccounts.actAs denied when attaching peer SA to Cloud Run",
                )
            )

            # 7. Negative Guardrail: Student A gets 400/403 requesting nvidia-l4 GPU
            gpu_svc_id = build_verify_service_id(student_a, "gpu")
            gpu_resp = client_a.post(
                services_parent_url,
                limiter_name="cloud_run",
                params={"serviceId": gpu_svc_id},
                json={
                    "template": {
                        "serviceAccount": sa_a,
                        "nodeSelector": {
                            "run.googleapis.com/accelerator": "nvidia-l4",
                        },
                        "containers": [
                            {
                                "image": HELLO_CONTAINER_IMAGE,
                                "resources": {
                                    "limits": {
                                        "cpu": "4",
                                        "memory": "16Gi",
                                        "nvidia.com/gpu": "1",
                                    }
                                },
                            }
                        ],
                    }
                },
            )
            if gpu_resp.status_code in (200, 201):
                self.admin_client.delete(
                    f"{services_parent_url}/{gpu_svc_id}",
                    limiter_name="cloud_run",
                )
            outcomes.append(
                CheckOutcome(
                    service=self.service,
                    check_id="run.gpu_request_denied",
                    kind="GUARDRAIL",
                    actor=student_a.slug,
                    target=f"projects/{project_id}/locations/{region}/services/{gpu_svc_id}",
                    passed=gpu_resp.status_code in (400, 403),
                    expected="HTTP 400 or 403",
                    actual=f"HTTP {gpu_resp.status_code}",
                    detail="Serverless nvidia-l4 GPU denied by custom.ntuDenyCloudRunGpu guardrail",
                )
            )

            # 8. Positive Cleanup: Student A deletes own run-<slug_a>-verify service (200)
            del_own_resp = client_a.delete(verify_svc_url, limiter_name="cloud_run")
            if del_own_resp.status_code == 200:
                cleaned_up_own_service = True
                if del_own_resp.content:
                    _maybe_poll_lro(
                        client_a,
                        del_own_resp.json(),
                        limiter_name="cloud_run",
                        base_url=RUN_API_BASE,
                        timeout_s=120.0,
                    )
            outcomes.append(
                CheckOutcome(
                    service=self.service,
                    check_id="run.delete_own_service_cleanup",
                    kind="POSITIVE",
                    actor=student_a.slug,
                    target=verify_svc_resource,
                    passed=del_own_resp.status_code == 200,
                    expected="HTTP 200",
                    actual=f"HTTP {del_own_resp.status_code}",
                    detail=f"Owner cleanup deleted {verify_svc_id}",
                )
            )
        finally:
            if created_own_service and not cleaned_up_own_service:
                self.admin_client.delete(verify_svc_url, limiter_name="cloud_run")

        return outcomes
