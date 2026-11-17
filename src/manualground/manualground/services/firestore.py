"""Firestore Native service driver for named per-student databases and CEL IAM Conditions."""

from __future__ import annotations

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

FIRESTORE_V1_BASE = "https://firestore.googleapis.com/v1"
FIRESTORE_DB_USER_ROLE_ID = "custom_ntu_firestore_db_user"
FIRESTORE_HARD_DB_QUOTA = 100
VERIFY_COLLECTION = "mg_verify"
VERIFY_DOC_ID = "isolation_probe"


class FirestoreDriver(BaseServiceDriver):
    """Provisions named Native databases (fs-<student>) and conditional IAM bindings."""

    service: ServiceName = ServiceName.FIRESTORE

    def _elapsed_ms(self, start: float) -> int:
        return max(0, int((self.admin_client._clock() - start) * 1000))

    def preflight(
        self,
        settings: ShardSettings,
        roster: list[StudentSpec],
    ) -> list[CheckOutcome]:
        """Verify <100 total Firestore databases and confirm (default) is uncreated."""
        project_id = settings.project_id
        list_url = f"{FIRESTORE_V1_BASE}/projects/{project_id}/databases"
        resp = self.admin_client.get(list_url, limiter_name="firestore_admin")

        if resp.status_code != 200:
            return [
                CheckOutcome(
                    service=self.service,
                    check_id="firestore.databases_list",
                    kind="GUARDRAIL",
                    actor="preflight",
                    target=project_id,
                    passed=False,
                    expected="HTTP 200",
                    actual=f"HTTP {resp.status_code}",
                    detail=resp.text[:300],
                )
            ]

        payload: dict[str, Any] = resp.json() if resp.content else {}
        databases = payload.get("databases") or []
        existing_ids: set[str] = set()
        for entry in databases:
            if isinstance(entry, dict) and entry.get("name"):
                existing_ids.add(str(entry["name"]).rsplit("/", 1)[-1])

        roster_ids = {s.firestore_db_id() for s in roster}
        projected_total = len(existing_ids | roster_ids)
        has_default = "(default)" in existing_ids

        outcomes: list[CheckOutcome] = [
            CheckOutcome(
                service=self.service,
                check_id="firestore.no_default_database",
                kind="GUARDRAIL",
                actor="preflight",
                target=f"projects/{project_id}/databases/(default)",
                passed=not has_default,
                expected="ABSENT",
                actual="PRESENT" if has_default else "ABSENT",
                detail="(default) is intentionally omitted so unconfigured SDK clients fail fast",
            ),
            CheckOutcome(
                service=self.service,
                check_id="firestore.database_quota_headroom",
                kind="GUARDRAIL",
                actor="preflight",
                target=project_id,
                passed=(
                    len(existing_ids) < FIRESTORE_HARD_DB_QUOTA
                    and projected_total < FIRESTORE_HARD_DB_QUOTA
                ),
                expected=f"< {FIRESTORE_HARD_DB_QUOTA} databases",
                actual=f"existing={len(existing_ids)}, projected={projected_total}",
                detail=f"Hard GCP cap is {FIRESTORE_HARD_DB_QUOTA} databases per project",
            ),
        ]
        return outcomes

    def provision_student(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[StepResult]:
        """Idempotently create named FIRESTORE_NATIVE database fs-<student> at 15 RPM."""
        project_id = settings.project_id
        db_id = student.firestore_db_id()
        db_resource = f"projects/{project_id}/databases/{db_id}"
        create_url = f"{FIRESTORE_V1_BASE}/projects/{project_id}/databases"

        t0 = self.admin_client._clock()
        resp = self.admin_client.post(
            create_url,
            limiter_name="firestore_admin",
            params={"databaseId": db_id},
            json={
                "type": "FIRESTORE_NATIVE",
                "locationId": settings.region,
                "deleteProtectionState": "DELETE_PROTECTION_ENABLED",
            },
        )

        if resp.status_code in (200, 201):
            payload: dict[str, Any] = resp.json() if resp.content else {}
            op_name = str(payload.get("name") or "").strip()
            status = "CREATED"

            if payload.get("done") is True:
                err = payload.get("error")
                if isinstance(err, dict) and (err.get("code") or err.get("message")):
                    if err.get("code") == 6 or "already exists" in str(err.get("message", "")).lower():
                        status = "UNCHANGED"
                    else:
                        raise GcpLroError(
                            f"Firestore database creation LRO failed for {db_id}: {err}",
                            operation=payload,
                        )
            elif "/operations/" in op_name or op_name.startswith("operations/"):
                try:
                    self.admin_client.poll_lro(
                        op_name,
                        limiter_name="firestore_admin",
                        base_url=FIRESTORE_V1_BASE,
                    )
                except GcpLroError as exc:
                    if "already exists" in str(exc).lower() or "already_exists" in str(exc).lower():
                        status = "UNCHANGED"
                    else:
                        raise
        elif resp.status_code == 409:
            status = "UNCHANGED"
        else:
            raise GcpHttpError(
                f"Failed creating Firestore database {db_id!r} "
                f"(HTTP {resp.status_code}): {resp.text[:500]}",
                status_code=resp.status_code,
                response=resp,
            )

        return [
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="ensure_database",
                resource_id=db_resource,
                status=status,  # type: ignore[arg-type]
                duration_ms=self._elapsed_ms(t0),
                detail=f"type=FIRESTORE_NATIVE, locationId={settings.region}, deleteProtection=ENABLED",
            )
        ]

    def project_iam_bindings(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[ConditionalBindingSpec]:
        """Emit 1 conditional project IAM binding scoping custom_ntu_firestore_db_user to fs-<student>."""
        project_id = settings.project_id
        db_id = student.firestore_db_id()
        db_path = f"projects/{project_id}/databases/{db_id}"
        return [
            ConditionalBindingSpec(
                role=f"projects/{project_id}/roles/{FIRESTORE_DB_USER_ROLE_ID}",
                members=[
                    f"user:{student.email}",
                    f"serviceAccount:{student.sa_email(project_id)}",
                ],
                condition_title=f"ntu-fs-{student.slug}",
                condition_expression=(
                    'resource.type == "firestore.googleapis.com/Database" && '
                    f'resource.name == "{db_path}"'
                ),
                condition_description=f"Isolate Firestore access for {student.slug} to {db_id}",
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
        """Verify positive CRUD on fs-<a>, 403 on fs-<b>, fail-fast on (default), and 403 on delete."""
        del client_b
        project_id = settings.project_id
        db_a = student_a.firestore_db_id()
        db_b = student_b.firestore_db_id()

        doc_a_url = (
            f"{FIRESTORE_V1_BASE}/projects/{project_id}/databases/{db_a}"
            f"/documents/{VERIFY_COLLECTION}/{VERIFY_DOC_ID}"
        )
        doc_b_url = (
            f"{FIRESTORE_V1_BASE}/projects/{project_id}/databases/{db_b}"
            f"/documents/{VERIFY_COLLECTION}/{VERIFY_DOC_ID}"
        )
        default_doc_url = (
            f"{FIRESTORE_V1_BASE}/projects/{project_id}/databases/(default)"
            f"/documents/{VERIFY_COLLECTION}/{VERIFY_DOC_ID}"
        )
        delete_db_b_url = f"{FIRESTORE_V1_BASE}/projects/{project_id}/databases/{db_b}"

        doc_payload = {
            "fields": {
                "owner": {"stringValue": student_a.slug},
                "probe": {"stringValue": "manualground-verify"},
            }
        }

        outcomes: list[CheckOutcome] = []

        # 1. Positive: Student A writes document to own named database fs-<a> (200).
        write_own = client_a.patch(
            doc_a_url,
            limiter_name="default",
            json=doc_payload,
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="firestore.own_doc_write",
                kind="POSITIVE",
                actor=student_a.slug,
                target=f"{db_a}/{VERIFY_COLLECTION}/{VERIFY_DOC_ID}",
                passed=write_own.status_code == 200,
                expected="HTTP 200",
                actual=f"HTTP {write_own.status_code}",
                detail="datastore.entities.update/create on own named database",
            )
        )

        # 2. Positive: Student A reads document from own named database fs-<a> (200).
        read_own = client_a.get(doc_a_url, limiter_name="default")
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="firestore.own_doc_read",
                kind="POSITIVE",
                actor=student_a.slug,
                target=f"{db_a}/{VERIFY_COLLECTION}/{VERIFY_DOC_ID}",
                passed=read_own.status_code == 200,
                expected="HTTP 200",
                actual=f"HTTP {read_own.status_code}",
                detail="datastore.entities.get on own named database",
            )
        )

        # 3. Negative cross-student: Student A cannot read from Student B's database fs-<b> (403).
        read_peer = client_a.get(doc_b_url, limiter_name="default")
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="firestore.cross_student_doc_read",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=f"{db_b}/{VERIFY_COLLECTION}/{VERIFY_DOC_ID}",
                passed=read_peer.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {read_peer.status_code}",
                detail="CEL resource.name condition blocks cross-student document read",
            )
        )

        # 4. Negative cross-student: Student A cannot write to Student B's database fs-<b> (403).
        write_peer = client_a.patch(
            doc_b_url,
            limiter_name="default",
            json=doc_payload,
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="firestore.cross_student_doc_write",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=f"{db_b}/{VERIFY_COLLECTION}/{VERIFY_DOC_ID}",
                passed=write_peer.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {write_peer.status_code}",
                detail="CEL resource.name condition blocks cross-student document write",
            )
        )

        # 5. Guardrail: Unconfigured access to (default) database fails fast (404 or 403).
        read_default = client_a.get(default_doc_url, limiter_name="default")
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="firestore.default_db_fail_fast",
                kind="GUARDRAIL",
                actor=student_a.slug,
                target=f"(default)/{VERIFY_COLLECTION}/{VERIFY_DOC_ID}",
                passed=read_default.status_code in (403, 404),
                expected="HTTP 404 or 403",
                actual=f"HTTP {read_default.status_code}",
                detail="(default) database is uncreated and excluded from CEL IAM condition",
            )
        )

        # 6. Guardrail: Student A cannot delete a Firestore database container (403).
        delete_db = client_a.delete(delete_db_b_url, limiter_name="firestore_admin")
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="firestore.guardrail_db_delete",
                kind="GUARDRAIL",
                actor=student_a.slug,
                target=f"projects/{project_id}/databases/{db_b}",
                passed=delete_db.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {delete_db.status_code}",
                detail="Folder IAM Deny v2 + role omission block datastore.databases.delete",
            )
        )

        return outcomes
