"""Cloud Storage (GCS) service driver for per-student isolated buckets."""

from __future__ import annotations

import copy
from typing import Any
from urllib.parse import quote

from manualground.config import ShardSettings
from manualground.core.http_client import GcpHttpError, GcpRestClient
from manualground.core.models import (
    CheckOutcome,
    ConditionalBindingSpec,
    ServiceName,
    StepResult,
    StudentSpec,
)
from manualground.services.base import BaseServiceDriver

STORAGE_V1_BASE = "https://storage.googleapis.com/storage/v1"
STORAGE_UPLOAD_V1_BASE = "https://storage.googleapis.com/upload/storage/v1"
SERVICE_USAGE_V1_BASE = "https://serviceusage.googleapis.com/v1"

METADATA_VIEWER_ROLE_ID = "custom_ntu_gcs_bucket_metadata_viewer"
OBJECT_USER_ROLE = "roles/storage.objectUser"
OBJECT_VIEWER_ROLE = "roles/storage.objectViewer"
VERIFY_PROBE_OBJECT = "manualground-verify/isolation-probe.txt"


def _merge_bucket_iam_bindings(
    policy: dict[str, Any],
    desired_role_members: dict[str, list[str]],
) -> tuple[dict[str, Any], bool]:
    """Idempotently merge unconditional role bindings into a GCS bucket IAM policy."""
    updated = copy.deepcopy(policy)
    original_bindings = copy.deepcopy(updated.get("bindings") or [])
    bindings: list[dict[str, Any]] = [
        {
            **b,
            "members": list(b.get("members") or []),
        }
        for b in original_bindings
    ]

    for role, members in desired_role_members.items():
        clean_members = [m.strip() for m in members if m and m.strip()]
        if not clean_members:
            continue
        existing = next(
            (b for b in bindings if b.get("role") == role and not b.get("condition")),
            None,
        )
        if existing is not None:
            existing["members"] = sorted(
                set(existing.get("members") or []) | set(clean_members)
            )
        else:
            bindings.append(
                {
                    "role": role,
                    "members": sorted(set(clean_members)),
                }
            )

    changed = bindings != original_bindings
    updated["bindings"] = bindings
    if "version" not in updated or int(updated.get("version") or 1) < 3:
        updated["version"] = 3
    return updated, changed


class GcsDriver(BaseServiceDriver):
    """Provisions per-student buckets (bkt-<project>-<student>) and verifies isolation."""

    service: ServiceName = ServiceName.GCS

    def _elapsed_ms(self, start: float) -> int:
        return max(0, int((self.admin_client._clock() - start) * 1000))

    def preflight(
        self,
        settings: ShardSettings,
        roster: list[StudentSpec],
    ) -> list[CheckOutcome]:
        """Validate GCS API enablement, custom metadata role, and bucket naming bounds."""
        outcomes: list[CheckOutcome] = []
        project_id = settings.project_id

        # 1. Validate deterministic bucket naming and uniqueness across the roster.
        seen_buckets: set[str] = set()
        invalid_buckets: list[str] = []
        duplicate_buckets: list[str] = []
        for student in roster:
            bkt = student.bucket_name(project_id)
            if not (3 <= len(bkt) <= 63) or bkt != bkt.lower():
                invalid_buckets.append(bkt)
            if bkt in seen_buckets:
                duplicate_buckets.append(bkt)
            seen_buckets.add(bkt)

        naming_ok = not invalid_buckets and not duplicate_buckets
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gcs.bucket_naming_bounds",
                kind="GUARDRAIL",
                actor="preflight",
                target=project_id,
                passed=naming_ok,
                expected="unique 3..63 char bucket names",
                actual=(
                    f"{len(seen_buckets)} valid unique bucket names"
                    if naming_ok
                    else f"invalid={invalid_buckets}, duplicates={duplicate_buckets}"
                ),
                detail=f"Region: {settings.region}",
            )
        )

        # 2. Verify storage.googleapis.com is enabled on the shard project.
        su_url = f"{SERVICE_USAGE_V1_BASE}/projects/{project_id}/services/storage.googleapis.com"
        su_resp = self.admin_client.get(su_url, limiter_name="default")
        su_payload: dict[str, Any] = su_resp.json() if su_resp.status_code == 200 and su_resp.content else {}
        su_state = su_payload.get("state", "ENABLED" if su_resp.status_code == 200 else f"HTTP_{su_resp.status_code}")
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gcs.api_enabled",
                kind="POSITIVE",
                actor="preflight",
                target="storage.googleapis.com",
                passed=(su_resp.status_code == 200 and su_state == "ENABLED"),
                expected="ENABLED",
                actual=str(su_state),
                detail=su_url,
            )
        )

        # 3. Verify Cloud Storage bucket control-plane reachability on the shard project.
        bkt_list_url = f"{STORAGE_V1_BASE}/b"
        bkt_resp = self.admin_client.get(
            bkt_list_url,
            limiter_name="storage_iam",
            params={"project": project_id, "maxResults": 1},
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gcs.control_plane_reachable",
                kind="GUARDRAIL",
                actor="preflight",
                target=project_id,
                passed=bkt_resp.status_code == 200,
                expected="HTTP 200",
                actual=f"HTTP {bkt_resp.status_code}",
                detail=bkt_list_url,
            )
        )

        return outcomes

    def provision_student(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[StepResult]:
        """Idempotently create bkt-<project>-<student> and apply per-bucket IAM bindings."""
        project_id = settings.project_id
        bucket_name = student.bucket_name(project_id)
        steps: list[StepResult] = []

        # Step 1: Idempotent bucket creation at 24 RPM (storage_bucket limiter).
        t0 = self.admin_client._clock()
        bucket_body: dict[str, Any] = {
            "name": bucket_name,
            "location": settings.region,
            "storageClass": "STANDARD",
            "iamConfiguration": {
                "uniformBucketLevelAccess": {"enabled": True},
                "publicAccessPrevention": "enforced",
            },
            "lifecycle": {
                "rule": [
                    {
                        "action": {"type": "Delete"},
                        "condition": {"age": 90},
                    }
                ]
            },
            "labels": {
                "managed-by": "manualground",
                "student": student.slug,
            },
        }
        create_resp = self.admin_client.post(
            f"{STORAGE_V1_BASE}/b",
            limiter_name="storage_bucket",
            params={"project": project_id},
            json=bucket_body,
        )

        bucket_data: dict[str, Any] = {}
        if create_resp.status_code in (200, 201):
            bucket_status = "CREATED"
            bucket_data = create_resp.json() if create_resp.content else {}
        elif create_resp.status_code == 409:
            bucket_status = "UNCHANGED"
            get_resp = self.admin_client.get(
                f"{STORAGE_V1_BASE}/b/{bucket_name}",
                limiter_name="storage_iam",
            )
            if get_resp.status_code == 403:
                raise GcpHttpError(
                    f"Bucket {bucket_name!r} returned 409 on insert and 403 on get "
                    "(globally owned by another project).",
                    status_code=403,
                    response=get_resp,
                )
            if get_resp.status_code == 200:
                bucket_data = get_resp.json() if get_resp.content else {}
                owner_proj_num = str(bucket_data.get("projectNumber") or "").strip()
                if (
                    settings.project_number
                    and owner_proj_num
                    and owner_proj_num != settings.project_number.strip()
                ):
                    raise GcpHttpError(
                        f"Bucket {bucket_name!r} belongs to projectNumber {owner_proj_num}, "
                        f"expected {settings.project_number}.",
                        status_code=409,
                        response=create_resp,
                    )
                iam_cfg = bucket_data.get("iamConfiguration")
                if isinstance(iam_cfg, dict):
                    ubla_ok = bool(
                        (iam_cfg.get("uniformBucketLevelAccess") or {}).get("enabled")
                    )
                    pap_ok = iam_cfg.get("publicAccessPrevention") == "enforced"
                    if not (ubla_ok and pap_ok):
                        patch_resp = self.admin_client.patch(
                            f"{STORAGE_V1_BASE}/b/{bucket_name}",
                            limiter_name="storage_iam",
                            json={
                                "iamConfiguration": {
                                    "uniformBucketLevelAccess": {"enabled": True},
                                    "publicAccessPrevention": "enforced",
                                }
                            },
                            raise_for_status=True,
                        )
                        bucket_data = patch_resp.json() if patch_resp.content else bucket_data
            elif get_resp.status_code not in (200, 404):
                raise GcpHttpError(
                    f"Unexpected HTTP {get_resp.status_code} inspecting existing bucket {bucket_name!r}: "
                    f"{get_resp.text[:500]}",
                    status_code=get_resp.status_code,
                    response=get_resp,
                )
        else:
            raise GcpHttpError(
                f"Failed creating bucket {bucket_name!r} (HTTP {create_resp.status_code}): "
                f"{create_resp.text[:500]}",
                status_code=create_resp.status_code,
                response=create_resp,
            )

        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="ensure_bucket",
                resource_id=bucket_name,
                status=bucket_status,  # type: ignore[arg-type]
                duration_ms=self._elapsed_ms(t0),
                detail=f"location={settings.region}, UBLA=true, PAP=enforced",
            )
        )

        # Step 2: Bucket-level IAM policy merge (getIamPolicy -> setIamPolicy).
        t1 = self.admin_client._clock()
        student_principals = [
            f"user:{student.email}",
            f"serviceAccount:{student.sa_email(project_id)}",
        ]
        desired_bindings: dict[str, list[str]] = {
            OBJECT_USER_ROLE: student_principals,
            f"projects/{project_id}/roles/{METADATA_VIEWER_ROLE_ID}": student_principals,
        }
        effective_project_number = (
            settings.project_number.strip()
            or str(bucket_data.get("projectNumber") or "").strip()
        )
        if effective_project_number:
            discovery_p4sa = (
                f"serviceAccount:service-{effective_project_number}"
                "@gcp-sa-discoveryengine.iam.gserviceaccount.com"
            )
            desired_bindings[OBJECT_VIEWER_ROLE] = [discovery_p4sa]

        iam_url = f"{STORAGE_V1_BASE}/b/{bucket_name}/iam"
        iam_status = "UNCHANGED"
        max_iam_attempts = 4
        for attempt in range(max_iam_attempts):
            pol_resp = self.admin_client.get(
                iam_url,
                limiter_name="storage_iam",
                params={"optionsRequestedPolicyVersion": 3},
                raise_for_status=True,
            )
            current_policy: dict[str, Any] = (
                pol_resp.json() if pol_resp.content else {"version": 3, "bindings": []}
            )
            merged_policy, changed = _merge_bucket_iam_bindings(
                current_policy,
                desired_bindings,
            )
            if not changed:
                iam_status = "UNCHANGED"
                break

            set_resp = self.admin_client.put(
                iam_url,
                limiter_name="storage_iam",
                json=merged_policy,
            )
            if set_resp.status_code == 200:
                iam_status = "CREATED"
                break
            if set_resp.status_code in (409, 412) and attempt < max_iam_attempts - 1:
                self.admin_client._sleep(
                    self.admin_client._compute_backoff(attempt, response=set_resp)
                )
                continue
            raise GcpHttpError(
                f"Failed setting bucket IAM policy on {bucket_name!r} "
                f"(HTTP {set_resp.status_code}): {set_resp.text[:500]}",
                status_code=set_resp.status_code,
                response=set_resp,
            )

        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="bind_bucket_iam",
                resource_id=bucket_name,
                status=iam_status,  # type: ignore[arg-type]
                duration_ms=self._elapsed_ms(t1),
                detail=", ".join(sorted(desired_bindings.keys())),
            )
        )

        return steps

    def project_iam_bindings(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[ConditionalBindingSpec]:
        """Return empty list: all per-student GCS permissions attach directly on the bucket."""
        return []

    def verify_isolation(
        self,
        settings: ShardSettings,
        student_a: StudentSpec,
        student_b: StudentSpec,
        client_a: GcpRestClient,
        client_b: GcpRestClient,
    ) -> list[CheckOutcome]:
        """Prove positive CRUD on own bucket and 403 on peer bucket & control-plane mutations."""
        del client_b  # Peer bucket existence is pre-provisioned; client_a exercises attacks.
        project_id = settings.project_id
        bucket_a = student_a.bucket_name(project_id)
        bucket_b = student_b.bucket_name(project_id)
        encoded_obj = quote(VERIFY_PROBE_OBJECT, safe="")
        probe_payload = f"manualground-probe:{student_a.slug}".encode("utf-8")

        outcomes: list[CheckOutcome] = []

        # 1. Positive: Student A writes object to own bucket (200/201).
        write_own = client_a.post(
            f"{STORAGE_UPLOAD_V1_BASE}/b/{bucket_a}/o",
            limiter_name="storage_iam",
            params={"uploadType": "media", "name": VERIFY_PROBE_OBJECT},
            content=probe_payload,
            headers={"Content-Type": "text/plain"},
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gcs.own_object_write",
                kind="POSITIVE",
                actor=student_a.slug,
                target=f"gs://{bucket_a}/{VERIFY_PROBE_OBJECT}",
                passed=write_own.status_code in (200, 201),
                expected="HTTP 200",
                actual=f"HTTP {write_own.status_code}",
                detail="storage.objects.create on own bucket",
            )
        )

        # 2. Positive: Student A reads object from own bucket (200).
        read_own = client_a.get(
            f"{STORAGE_V1_BASE}/b/{bucket_a}/o/{encoded_obj}",
            limiter_name="storage_iam",
            params={"alt": "media"},
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gcs.own_object_read",
                kind="POSITIVE",
                actor=student_a.slug,
                target=f"gs://{bucket_a}/{VERIFY_PROBE_OBJECT}",
                passed=read_own.status_code == 200,
                expected="HTTP 200",
                actual=f"HTTP {read_own.status_code}",
                detail="storage.objects.get on own bucket",
            )
        )

        # 3. Positive: Student A deletes object from own bucket (200/204).
        delete_own = client_a.delete(
            f"{STORAGE_V1_BASE}/b/{bucket_a}/o/{encoded_obj}",
            limiter_name="storage_iam",
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gcs.own_object_delete",
                kind="POSITIVE",
                actor=student_a.slug,
                target=f"gs://{bucket_a}/{VERIFY_PROBE_OBJECT}",
                passed=delete_own.status_code in (200, 204),
                expected="HTTP 200/204",
                actual=f"HTTP {delete_own.status_code}",
                detail="storage.objects.delete on own bucket",
            )
        )

        # 4. Negative cross-student: Student A cannot read from Student B's bucket (403).
        read_peer = client_a.get(
            f"{STORAGE_V1_BASE}/b/{bucket_b}/o/{encoded_obj}",
            limiter_name="storage_iam",
            params={"alt": "media"},
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gcs.cross_student_object_read",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=f"gs://{bucket_b}/{VERIFY_PROBE_OBJECT}",
                passed=read_peer.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {read_peer.status_code}",
                detail="Cross-student storage.objects.get must be denied",
            )
        )

        # 5. Negative cross-student: Student A cannot write to Student B's bucket (403).
        write_peer = client_a.post(
            f"{STORAGE_UPLOAD_V1_BASE}/b/{bucket_b}/o",
            limiter_name="storage_iam",
            params={"uploadType": "media", "name": VERIFY_PROBE_OBJECT},
            content=b"unauthorized-cross-student-write",
            headers={"Content-Type": "text/plain"},
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gcs.cross_student_object_write",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=f"gs://{bucket_b}/{VERIFY_PROBE_OBJECT}",
                passed=write_peer.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {write_peer.status_code}",
                detail="Cross-student storage.objects.create must be denied",
            )
        )

        # 6. Negative cross-student: Student A cannot delete from Student B's bucket (403).
        delete_peer = client_a.delete(
            f"{STORAGE_V1_BASE}/b/{bucket_b}/o/{encoded_obj}",
            limiter_name="storage_iam",
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gcs.cross_student_object_delete",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=f"gs://{bucket_b}/{VERIFY_PROBE_OBJECT}",
                passed=delete_peer.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {delete_peer.status_code}",
                detail="Cross-student storage.objects.delete must be denied",
            )
        )

        # 7. Guardrail: Student A cannot create an unprovisioned bucket (403).
        unauth_bucket = f"bkt-{project_id}-{student_a.slug}-unauth"[:63].rstrip("-")
        create_bkt = client_a.post(
            f"{STORAGE_V1_BASE}/b",
            limiter_name="storage_bucket",
            params={"project": project_id},
            json={"name": unauth_bucket, "location": settings.region},
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gcs.guardrail_bucket_create",
                kind="GUARDRAIL",
                actor=student_a.slug,
                target=unauth_bucket,
                passed=create_bkt.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {create_bkt.status_code}",
                detail="Folder IAM Deny v2 blocks storage.googleapis.com/buckets.create",
            )
        )

        # 8. Guardrail: Student A cannot delete a bucket (403).
        delete_bkt = client_a.delete(
            f"{STORAGE_V1_BASE}/b/{bucket_b}",
            limiter_name="storage_bucket",
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="gcs.guardrail_bucket_delete",
                kind="GUARDRAIL",
                actor=student_a.slug,
                target=bucket_b,
                passed=delete_bkt.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {delete_bkt.status_code}",
                detail="Folder IAM Deny v2 blocks storage.googleapis.com/buckets.delete",
            )
        )

        return outcomes
