"""Service driver for unified student Service Accounts (`sa-<student>`) and Vertex AI Gemini."""

from __future__ import annotations

import time
from typing import Any

from manualground.config import ShardSettings
from manualground.core.http_client import (
    CLOUD_PLATFORM_SCOPE,
    GcpHttpError,
    GcpRestClient,
)
from manualground.core.models import (
    CheckOutcome,
    ConditionalBindingSpec,
    ServiceName,
    StepResult,
    StudentSpec,
)
from manualground.services.base import BaseServiceDriver

IAM_API_BASE = "https://iam.googleapis.com/v1"
IAM_CREDENTIALS_API_BASE = "https://iamcredentials.googleapis.com/v1"
MAX_SERVICE_ACCOUNTS_PER_PROJECT = 100
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def aiplatform_base_url(region: str) -> str:
    """Return the regional or global Vertex AI v1 REST endpoint."""
    cleaned = (region or "asia-southeast1").strip().lower()
    if cleaned == "global":
        return "https://aiplatform.googleapis.com/v1"
    return f"https://{cleaned}-aiplatform.googleapis.com/v1"


class IamGeminiDriver(BaseServiceDriver):
    """Provisions `sa-<student>` identities, resource-level impersonation IAM, and Gemini checks."""

    service: ServiceName = ServiceName.GEMINI_SA

    def __init__(
        self,
        admin_client: GcpRestClient,
        *,
        gemini_model: str = DEFAULT_GEMINI_MODEL,
        max_propagation_attempts: int = 6,
        propagation_poll_interval_s: float = 1.0,
    ) -> None:
        super().__init__(admin_client)
        self.gemini_model = gemini_model
        self.max_propagation_attempts = max(1, max_propagation_attempts)
        self.propagation_poll_interval_s = max(0.01, propagation_poll_interval_s)

    def _list_service_accounts(self, project_id: str) -> list[dict[str, Any]]:
        url = f"{IAM_API_BASE}/projects/{project_id}/serviceAccounts"
        accounts: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params: dict[str, Any] = {"pageSize": 100}
            if page_token:
                params["pageToken"] = page_token
            resp = self.admin_client.get(
                url,
                limiter_name="iam",
                params=params,
                raise_for_status=True,
            )
            payload: dict[str, Any] = resp.json() if resp.content else {}
            batch = payload.get("accounts") or []
            if isinstance(batch, list):
                accounts.extend(item for item in batch if isinstance(item, dict))
            page_token = str(payload.get("nextPageToken") or "").strip()
            if not page_token:
                break
        return accounts

    def preflight(
        self,
        settings: ShardSettings,
        roster: list[StudentSpec],
    ) -> list[CheckOutcome]:
        """Verify user-managed Service Account count stays strictly below the 100-SA project cap."""
        project_id = settings.project_id
        accounts = self._list_service_accounts(project_id)
        existing_emails = {
            str(acc.get("email") or "").strip().lower()
            for acc in accounts
            if acc.get("email")
        }
        existing_count = len(accounts)
        new_student_sas = {
            stu.sa_email(project_id).lower() for stu in roster
        } - existing_emails
        projected_total = existing_count + len(new_student_sas)

        passed = (
            existing_count < MAX_SERVICE_ACCOUNTS_PER_PROJECT
            and projected_total < MAX_SERVICE_ACCOUNTS_PER_PROJECT
        )
        return [
            CheckOutcome(
                service=self.service,
                check_id="preflight.gemini.sa_quota_cap",
                kind="GUARDRAIL",
                actor="preflight",
                target=f"projects/{project_id}/serviceAccounts",
                passed=passed,
                expected=f"< {MAX_SERVICE_ACCOUNTS_PER_PROJECT} service accounts",
                actual=f"{existing_count} existing ({projected_total} projected)",
                detail=(
                    f"{len(new_student_sas)} net-new student SA(s) from {len(roster)} roster entries"
                ),
            )
        ]

    def provision_student(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[StepResult]:
        """Idempotently create `sa-<student>`, bind strict user impersonation IAM, and verify read."""
        project_id = settings.project_id
        sa_id = student.sa_id()
        sa_email = student.sa_email(project_id)
        sa_resource = f"projects/{project_id}/serviceAccounts/{sa_email}"
        steps: list[StepResult] = []

        # 1. Create unified per-student Service Account (45 RPM via "iam" limiter)
        t0 = time.monotonic()
        create_url = f"{IAM_API_BASE}/projects/{project_id}/serviceAccounts"
        create_resp = self.admin_client.post(
            create_url,
            limiter_name="iam",
            json={
                "accountId": sa_id,
                "serviceAccount": {
                    "displayName": (
                        student.display_name or f"ManualGround Student ({student.slug})"
                    )[:100],
                    "description": f"Unified playground workload identity for {student.email}",
                },
            },
        )
        elapsed_create = int((time.monotonic() - t0) * 1000)

        if create_resp.status_code in (200, 201):
            create_status = "CREATED"
            create_detail = f"Created unified workload SA {sa_email}"
        elif create_resp.status_code == 409:
            create_status = "UNCHANGED"
            create_detail = f"Service account {sa_email} already exists"
        else:
            raise GcpHttpError(
                f"Failed creating service account {sa_email} "
                f"(HTTP {create_resp.status_code}): {create_resp.text[:500]}",
                status_code=create_resp.status_code,
                response=create_resp,
            )

        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="create_service_account",
                resource_id=sa_email,
                status=create_status,
                duration_ms=elapsed_create,
                detail=create_detail,
            )
        )

        # 2. Authoritative resource-level IAM on sa-<student> strictly for user:<email>
        t1 = time.monotonic()
        iam_url = f"{IAM_API_BASE}/{sa_resource}:setIamPolicy"
        sa_policy = {
            "version": 3,
            "bindings": [
                {
                    "role": "roles/iam.serviceAccountUser",
                    "members": [f"user:{student.email}"],
                },
                {
                    "role": "roles/iam.serviceAccountTokenCreator",
                    "members": [f"user:{student.email}"],
                },
            ],
        }
        iam_resp = self.admin_client.post(
            iam_url,
            limiter_name="iam",
            json={"policy": sa_policy},
            expected_statuses=(200,),
        )
        elapsed_iam = int((time.monotonic() - t1) * 1000)
        _ = iam_resp

        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="set_sa_iam_policy",
                resource_id=sa_resource,
                status="CREATED" if create_status == "CREATED" else "UNCHANGED",
                duration_ms=elapsed_iam,
                detail=(
                    f"Bound serviceAccountUser + serviceAccountTokenCreator strictly to user:{student.email}"
                ),
            )
        )

        # 3. Verify SA resource propagation via IAM GET
        t2 = time.monotonic()
        get_url = f"{IAM_API_BASE}/{sa_resource}"
        propagated = False
        last_resp = None
        for attempt in range(self.max_propagation_attempts):
            last_resp = self.admin_client.get(get_url, limiter_name="iam")
            if last_resp.status_code == 200:
                propagated = True
                break
            if last_resp.status_code == 404 and attempt + 1 < self.max_propagation_attempts:
                self.admin_client._sleep(self.propagation_poll_interval_s)
                continue
            break

        if not propagated:
            code = last_resp.status_code if last_resp is not None else 0
            body = last_resp.text[:500] if last_resp is not None else ""
            raise GcpHttpError(
                f"Service account {sa_email} failed propagation verification (HTTP {code}): {body}",
                status_code=code,
                response=last_resp,
            )

        elapsed_prop = int((time.monotonic() - t2) * 1000)
        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="verify_sa_propagation",
                resource_id=sa_email,
                status="UNCHANGED",
                duration_ms=elapsed_prop,
                detail="Verified service account visibility on IAM control plane",
            )
        )
        return steps

    def project_iam_bindings(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[ConditionalBindingSpec]:
        """Emit unconditional project-level `custom_ntu_gemini_caller` grant for student + SA."""
        project_id = settings.project_id
        sa_member = f"serviceAccount:{student.sa_email(project_id)}"
        group_email = settings.student_group_email.strip()
        human_member = f"group:{group_email}" if group_email else f"user:{student.email}"
        return [
            ConditionalBindingSpec(
                role=f"projects/{project_id}/roles/custom_ntu_gemini_caller",
                members=[human_member, sa_member],
            )
        ]

    def verify_isolation(
        self,
        settings: ShardSettings,
        student_a: StudentSpec,
        student_b: StudentSpec,
        client_a: GcpRestClient,
        client_b: GcpRestClient,
    ) -> list[CheckOutcome]:
        """Verify own-SA token minting & Gemini inference (200) and cross-SA / key / job blocks."""
        _ = client_b
        project_id = settings.project_id
        region = settings.region
        sa_a = student_a.sa_email(project_id)
        sa_b = student_b.sa_email(project_id)
        outcomes: list[CheckOutcome] = []

        # 1. Positive: Student A mints short-lived OAuth access token on own sa-<a> (200)
        tok_a_url = f"{IAM_CREDENTIALS_API_BASE}/projects/-/serviceAccounts/{sa_a}:generateAccessToken"
        tok_a_resp = client_a.post(
            tok_a_url,
            limiter_name="iam",
            json={"scope": [CLOUD_PLATFORM_SCOPE], "lifetime": "3600s"},
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gemini.sa_impersonate_own",
                kind="POSITIVE",
                actor=student_a.slug,
                target=sa_a,
                passed=tok_a_resp.status_code == 200,
                expected="HTTP 200",
                actual=f"HTTP {tok_a_resp.status_code}",
                detail="generateAccessToken on own unified service account",
            )
        )

        # 2. Positive: Vertex AI Gemini publisher model generateContent (200)
        vertex_base = aiplatform_base_url(region)
        gemini_target = (
            f"projects/{project_id}/locations/{region}/publishers/google/models/{self.gemini_model}"
        )
        gemini_url = f"{vertex_base}/{gemini_target}:generateContent"
        gemini_resp = client_a.post(
            gemini_url,
            limiter_name="vertex_ai",
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": "Reply with the single word OK."}],
                    }
                ],
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 16,
                },
            },
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gemini.generate_content_positive",
                kind="POSITIVE",
                actor=student_a.slug,
                target=gemini_target,
                passed=gemini_resp.status_code == 200,
                expected="HTTP 200",
                actual=f"HTTP {gemini_resp.status_code}",
                detail=f"Stateless {self.gemini_model}:generateContent inference",
            )
        )

        # 3. Negative Cross-Student: Student A cannot generateAccessToken on peer sa-<b> (403)
        tok_b_url = f"{IAM_CREDENTIALS_API_BASE}/projects/-/serviceAccounts/{sa_b}:generateAccessToken"
        tok_b_resp = client_a.post(
            tok_b_url,
            limiter_name="iam",
            json={"scope": [CLOUD_PLATFORM_SCOPE], "lifetime": "3600s"},
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gemini.sa_impersonate_cross_student_denied",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=sa_b,
                passed=tok_b_resp.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {tok_b_resp.status_code}",
                detail="Cross-student generateAccessToken must be denied",
            )
        )

        # 4. Negative Guardrail: Static SA key creation blocked (400 Org Policy or 403 IAM Deny)
        key_url = f"{IAM_API_BASE}/projects/{project_id}/serviceAccounts/{sa_a}/keys"
        key_resp = client_a.post(
            key_url,
            limiter_name="iam",
            json={"privateKeyType": "TYPE_GOOGLE_CREDENTIALS_FILE"},
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gemini.sa_key_create_denied",
                kind="GUARDRAIL",
                actor=student_a.slug,
                target=f"{sa_a}/keys",
                passed=key_resp.status_code in (400, 403),
                expected="HTTP 400 or 403",
                actual=f"HTTP {key_resp.status_code}",
                detail="Static JSON key creation blocked by Org Policy and Folder IAM Deny",
            )
        )

        # 5. Negative Guardrail / Cross-Student: Service Account deletion blocked (403)
        del_sa_url = f"{IAM_API_BASE}/projects/{project_id}/serviceAccounts/{sa_b}"
        del_sa_resp = client_a.delete(del_sa_url, limiter_name="iam")
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gemini.sa_delete_denied",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=sa_b,
                passed=del_sa_resp.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {del_sa_resp.status_code}",
                detail="Service account deletion blocked by IAM and Folder Deny v2",
            )
        )

        # 6. Negative Guardrail: Vertex AI customJobs.create denied (403)
        jobs_url = f"{vertex_base}/projects/{project_id}/locations/{region}/customJobs"
        jobs_resp = client_a.post(
            jobs_url,
            limiter_name="vertex_ai",
            json={
                "displayName": f"unauthorized-custom-job-{student_a.slug}",
                "jobSpec": {
                    "workerPoolSpecs": [
                        {
                            "machineSpec": {"machineType": "n1-standard-4"},
                            "replicaCount": 1,
                            "containerSpec": {
                                "imageUri": "us-docker.pkg.dev/cloudrun/container/hello"
                            },
                        }
                    ]
                },
            },
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gemini.custom_jobs_create_denied",
                kind="GUARDRAIL",
                actor=student_a.slug,
                target=f"projects/{project_id}/locations/{region}/customJobs",
                passed=jobs_resp.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {jobs_resp.status_code}",
                detail="Billable Vertex AI custom training jobs omitted from custom_ntu_gemini_caller",
            )
        )

        return outcomes
