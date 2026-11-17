"""Service driver for Vertex AI Search / Discovery Engine (`ds-<student>` + `eng-<student>`)."""

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

DISCOVERY_API_BASE = "https://discoveryengine.googleapis.com/v1"
DEFAULT_SEARCH_LOCATION = "global"
DEFAULT_COLLECTION = "default_collection"

MAX_DATA_STORES_PER_PROJECT = 100
MAX_ENGINES_PER_PROJECT = 150


def _maybe_poll_lro(
    client: GcpRestClient,
    payload: dict[str, Any],
    *,
    limiter_name: str,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    """Poll a Discovery Engine long-running operation if `done` is not already True."""
    op_name = str(payload.get("name") or "").strip()
    if "/operations/" in op_name and payload.get("done") is not True:
        return client.poll_lro(
            op_name,
            limiter_name=limiter_name,
            base_url=DISCOVERY_API_BASE,
            timeout_s=timeout_s,
        )
    return payload


class VertexSearchDriver(BaseServiceDriver):
    """Provisions isolated Discovery Engine `DataStore` + Search `Engine` slices per student."""

    service: ServiceName = ServiceName.VERTEX_SEARCH

    def __init__(
        self,
        admin_client: GcpRestClient,
        *,
        location: str = DEFAULT_SEARCH_LOCATION,
        trigger_initial_import: bool = True,
        wait_sync: bool = False,
    ) -> None:
        super().__init__(admin_client)
        self.location = location
        self.trigger_initial_import = trigger_initial_import
        self.wait_sync = wait_sync
        self._acl_configured_projects: set[str] = set()

    def _collection_base(self, project_id: str) -> str:
        return (
            f"projects/{project_id}/locations/{self.location}/collections/{DEFAULT_COLLECTION}"
        )

    def _list_collection_resources(
        self,
        project_id: str,
        resource_plural: str,
    ) -> list[dict[str, Any]]:
        url = f"{DISCOVERY_API_BASE}/{self._collection_base(project_id)}/{resource_plural}"
        items: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params: dict[str, Any] = {"pageSize": 100}
            if page_token:
                params["pageToken"] = page_token
            resp = self.admin_client.get(
                url,
                limiter_name="discovery_engine",
                params=params,
            )
            if resp.status_code == 404:
                return []
            if resp.status_code >= 400:
                raise GcpHttpError(
                    f"Failed listing Discovery Engine {resource_plural} "
                    f"(HTTP {resp.status_code}): {resp.text[:500]}",
                    status_code=resp.status_code,
                    response=resp,
                )
            payload: dict[str, Any] = resp.json() if resp.content else {}
            batch = payload.get(resource_plural) or []
            if isinstance(batch, list):
                items.extend(entry for entry in batch if isinstance(entry, dict))
            page_token = str(payload.get("nextPageToken") or "").strip()
            if not page_token:
                break
        return items

    def preflight(
        self,
        settings: ShardSettings,
        roster: list[StudentSpec],
    ) -> list[CheckOutcome]:
        """Verify Discovery Engine DataStore (<100) and Engine (<150) project quota caps."""
        project_id = settings.project_id
        coll_base = self._collection_base(project_id)

        datastores = self._list_collection_resources(project_id, "dataStores")
        existing_ds_ids = {
            str(ds.get("name") or "").rsplit("/", 1)[-1]
            for ds in datastores
            if ds.get("name")
        }
        new_ds_ids = {stu.search_datastore_id() for stu in roster} - existing_ds_ids
        projected_ds = len(datastores) + len(new_ds_ids)
        ds_ok = (
            len(datastores) < MAX_DATA_STORES_PER_PROJECT
            and projected_ds < MAX_DATA_STORES_PER_PROJECT
        )

        engines = self._list_collection_resources(project_id, "engines")
        existing_eng_ids = {
            str(eng.get("name") or "").rsplit("/", 1)[-1]
            for eng in engines
            if eng.get("name")
        }
        new_eng_ids = {stu.search_engine_id() for stu in roster} - existing_eng_ids
        projected_eng = len(engines) + len(new_eng_ids)
        eng_ok = (
            len(engines) < MAX_ENGINES_PER_PROJECT
            and projected_eng < MAX_ENGINES_PER_PROJECT
        )

        return [
            CheckOutcome(
                service=self.service,
                check_id="preflight.search.datastore_quota_cap",
                kind="GUARDRAIL",
                actor="preflight",
                target=f"{coll_base}/dataStores",
                passed=ds_ok,
                expected=f"< {MAX_DATA_STORES_PER_PROJECT} data stores",
                actual=f"{len(datastores)} existing ({projected_ds} projected)",
                detail=f"{len(new_ds_ids)} net-new DataStore(s) from {len(roster)} roster entries",
            ),
            CheckOutcome(
                service=self.service,
                check_id="preflight.search.engine_quota_cap",
                kind="GUARDRAIL",
                actor="preflight",
                target=f"{coll_base}/engines",
                passed=eng_ok,
                expected=f"< {MAX_ENGINES_PER_PROJECT} engines",
                actual=f"{len(engines)} existing ({projected_eng} projected)",
                detail=f"{len(new_eng_ids)} net-new Engine(s) from {len(roster)} roster entries",
            ),
        ]

    def _ensure_acl_config(self, project_id: str, student_slug: str) -> StepResult | None:
        """Ensure regional `aclConfig` (`data_store_access_control_enabled`) once per shard run."""
        if project_id in self._acl_configured_projects:
            return None

        t0 = time.monotonic()
        acl_resource = f"projects/{project_id}/locations/{self.location}/aclConfig"
        acl_url = f"{DISCOVERY_API_BASE}/{acl_resource}"
        resp = self.admin_client.patch(
            acl_url,
            limiter_name="discovery_engine",
            json={
                "name": acl_resource,
                "idpConfig": {"idpType": "GSUITE"},
            },
        )
        if resp.status_code not in (200, 201, 409):
            raise GcpHttpError(
                f"Failed configuring Discovery Engine aclConfig on {project_id} "
                f"(HTTP {resp.status_code}): {resp.text[:500]}",
                status_code=resp.status_code,
                response=resp,
            )

        self._acl_configured_projects.add(project_id)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return StepResult(
            service=self.service,
            student_slug=student_slug,
            action="ensure_acl_config",
            resource_id=acl_resource,
            status="UNCHANGED",
            duration_ms=elapsed_ms,
            detail="Ensured Discovery Engine aclConfig / data_store_access_control_enabled",
        )

    def provision_student(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[StepResult]:
        """Provision `ds-<student>` + `eng-<student>`, bind resource IAM, and start non-blocking sync."""
        project_id = settings.project_id
        sa_email = student.sa_email(project_id)
        coll_base = self._collection_base(project_id)
        ds_id = student.search_datastore_id()
        eng_id = student.search_engine_id()
        ds_resource = f"{coll_base}/dataStores/{ds_id}"
        eng_resource = f"{coll_base}/engines/{eng_id}"
        steps: list[StepResult] = []

        # 0. Ensure shard aclConfig once per driver run
        acl_step = self._ensure_acl_config(project_id, student.slug)
        if acl_step is not None:
            steps.append(acl_step)

        # 1. Idempotently create Unstructured GCS DataStore ds-<student> (15 RPM)
        t_ds = time.monotonic()
        ds_parent_url = f"{DISCOVERY_API_BASE}/{coll_base}/dataStores"
        ds_resp = self.admin_client.post(
            ds_parent_url,
            limiter_name="discovery_engine",
            params={"dataStoreId": ds_id},
            json={
                "displayName": f"ManualGround RAG DataStore ({student.slug})",
                "industryVertical": "GENERIC",
                "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
                "contentConfig": "CONTENT_REQUIRED",
            },
        )
        if ds_resp.status_code == 409:
            ds_status = "UNCHANGED"
            ds_detail = f"DataStore {ds_id} already exists"
        elif ds_resp.status_code in (200, 201):
            ds_payload: dict[str, Any] = ds_resp.json() if ds_resp.content else {}
            try:
                _maybe_poll_lro(
                    self.admin_client,
                    ds_payload,
                    limiter_name="discovery_engine",
                )
                ds_status = "CREATED"
                ds_detail = f"Created unstructured DataStore {ds_id}"
            except GcpLroError as exc:
                err_obj = exc.operation.get("error") or {}
                if isinstance(err_obj, dict) and err_obj.get("code") == 6:
                    ds_status = "UNCHANGED"
                    ds_detail = f"DataStore {ds_id} already exists (LRO code 6)"
                else:
                    raise
        else:
            raise GcpHttpError(
                f"Failed creating DataStore {ds_id} (HTTP {ds_resp.status_code}): "
                f"{ds_resp.text[:500]}",
                status_code=ds_resp.status_code,
                response=ds_resp,
            )

        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="create_datastore",
                resource_id=ds_resource,
                status=ds_status,
                duration_ms=int((time.monotonic() - t_ds) * 1000),
                detail=ds_detail,
            )
        )

        # 2. Resource-level DataStore IAM (viewer + user to student + sa-<student>; zero import!)
        t_ds_iam = time.monotonic()
        ds_iam_url = f"{DISCOVERY_API_BASE}/{ds_resource}:setIamPolicy"
        ds_policy = {
            "bindings": [
                {
                    "role": "roles/discoveryengine.viewer",
                    "members": [
                        f"user:{student.email}",
                        f"serviceAccount:{sa_email}",
                    ],
                },
                {
                    "role": "roles/discoveryengine.user",
                    "members": [
                        f"user:{student.email}",
                        f"serviceAccount:{sa_email}",
                    ],
                },
            ]
        }
        self.admin_client.post(
            ds_iam_url,
            limiter_name="discovery_engine",
            json={"policy": ds_policy},
            expected_statuses=(200,),
        )
        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="set_datastore_iam_policy",
                resource_id=ds_resource,
                status="CREATED" if ds_status == "CREATED" else "UNCHANGED",
                duration_ms=int((time.monotonic() - t_ds_iam) * 1000),
                detail=f"Bound viewer + user on {ds_id} to user:{student.email} and {sa_email}",
            )
        )

        # 3. Idempotently create Search Engine eng-<student> (Enterprise + LLM add-on, 15 RPM)
        t_eng = time.monotonic()
        eng_parent_url = f"{DISCOVERY_API_BASE}/{coll_base}/engines"
        eng_resp = self.admin_client.post(
            eng_parent_url,
            limiter_name="discovery_engine",
            params={"engineId": eng_id},
            json={
                "displayName": f"ManualGround RAG Search Engine ({student.slug})",
                "dataStoreIds": [ds_id],
                "solutionType": "SOLUTION_TYPE_SEARCH",
                "industryVertical": "GENERIC",
                "searchEngineConfig": {
                    "searchTier": "SEARCH_TIER_ENTERPRISE",
                    "searchAddOns": ["SEARCH_ADD_ON_LLM"],
                },
            },
        )
        if eng_resp.status_code == 409:
            eng_status = "UNCHANGED"
            eng_detail = f"Search Engine {eng_id} already exists"
        elif eng_resp.status_code in (200, 201):
            eng_payload: dict[str, Any] = eng_resp.json() if eng_resp.content else {}
            try:
                _maybe_poll_lro(
                    self.admin_client,
                    eng_payload,
                    limiter_name="discovery_engine",
                )
                eng_status = "CREATED"
                eng_detail = f"Created Enterprise + LLM Search Engine {eng_id}"
            except GcpLroError as exc:
                err_obj = exc.operation.get("error") or {}
                if isinstance(err_obj, dict) and err_obj.get("code") == 6:
                    eng_status = "UNCHANGED"
                    eng_detail = f"Search Engine {eng_id} already exists (LRO code 6)"
                else:
                    raise
        else:
            raise GcpHttpError(
                f"Failed creating Search Engine {eng_id} (HTTP {eng_resp.status_code}): "
                f"{eng_resp.text[:500]}",
                status_code=eng_resp.status_code,
                response=eng_resp,
            )

        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="create_engine",
                resource_id=eng_resource,
                status=eng_status,
                duration_ms=int((time.monotonic() - t_eng) * 1000),
                detail=eng_detail,
            )
        )

        # 4. Resource-level Engine IAM (agentspaceAdmin to user:<email>; viewer + user to sa-<student>)
        t_eng_iam = time.monotonic()
        eng_iam_url = f"{DISCOVERY_API_BASE}/{eng_resource}:setIamPolicy"
        eng_policy = {
            "bindings": [
                {
                    "role": "roles/discoveryengine.agentspaceAdmin",
                    "members": [f"user:{student.email}"],
                },
                {
                    "role": "roles/discoveryengine.viewer",
                    "members": [f"serviceAccount:{sa_email}"],
                },
                {
                    "role": "roles/discoveryengine.user",
                    "members": [f"serviceAccount:{sa_email}"],
                },
            ]
        }
        self.admin_client.post(
            eng_iam_url,
            limiter_name="discovery_engine",
            json={"policy": eng_policy},
            expected_statuses=(200,),
        )
        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="set_engine_iam_policy",
                resource_id=eng_resource,
                status="CREATED" if eng_status == "CREATED" else "UNCHANGED",
                duration_ms=int((time.monotonic() - t_eng_iam) * 1000),
                detail=f"Bound agentspaceAdmin to user:{student.email} and user/viewer to {sa_email}",
            )
        )

        # 5. Optional non-blocking initial GCS documents:import at 5 RPM (--no-wait-sync default)
        if self.trigger_initial_import:
            t_imp = time.monotonic()
            rag_gcs_uri = f"gs://{student.bucket_name(project_id)}/rag/*"
            import_resource = f"{ds_resource}/branches/0"
            import_url = f"{DISCOVERY_API_BASE}/{import_resource}/documents:import"
            imp_resp = self.admin_client.post(
                import_url,
                limiter_name="import_documents",
                json={
                    "gcsSource": {
                        "inputUris": [rag_gcs_uri],
                        "dataSchema": "content",
                    },
                    "reconciliationMode": "INCREMENTAL",
                },
            )
            elapsed_imp = int((time.monotonic() - t_imp) * 1000)

            if imp_resp.status_code in (200, 201):
                imp_payload: dict[str, Any] = imp_resp.json() if imp_resp.content else {}
                if self.wait_sync:
                    _maybe_poll_lro(
                        self.admin_client,
                        imp_payload,
                        limiter_name="discovery_engine",
                        timeout_s=300.0,
                    )
                op_name = str(imp_payload.get("name") or "submitted")
                steps.append(
                    StepResult(
                        service=self.service,
                        student_slug=student.slug,
                        action="import_gcs_documents",
                        resource_id=import_resource,
                        status="CREATED" if ds_status == "CREATED" else "UNCHANGED",
                        duration_ms=elapsed_imp,
                        detail=(
                            f"Triggered non-blocking GCS import from {rag_gcs_uri} ({op_name})"
                            if not self.wait_sync
                            else f"Completed GCS import from {rag_gcs_uri} ({op_name})"
                        ),
                    )
                )
            elif imp_resp.status_code in (400, 404):
                steps.append(
                    StepResult(
                        service=self.service,
                        student_slug=student.slug,
                        action="import_gcs_documents",
                        resource_id=import_resource,
                        status="SKIPPED",
                        duration_ms=elapsed_imp,
                        detail=f"No initial documents matched {rag_gcs_uri} yet (HTTP {imp_resp.status_code})",
                    )
                )
            else:
                raise GcpHttpError(
                    f"Failed triggering GCS documents:import on {ds_id} "
                    f"(HTTP {imp_resp.status_code}): {imp_resp.text[:500]}",
                    status_code=imp_resp.status_code,
                    response=imp_resp,
                )

        return steps

    def project_iam_bindings(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[ConditionalBindingSpec]:
        """Emit unconditional project-level `custom_ntu_vertex_search_console` binding."""
        project_id = settings.project_id
        sa_member = f"serviceAccount:{student.sa_email(project_id)}"
        group_email = settings.student_group_email.strip()
        human_member = f"group:{group_email}" if group_email else f"user:{student.email}"
        return [
            ConditionalBindingSpec(
                role=f"projects/{project_id}/roles/custom_ntu_vertex_search_console",
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
        """Verify own Engine search (200) and peer Engine/DataStore/cross-bucket import blocks (403)."""
        _ = client_b
        project_id = settings.project_id
        coll_base = self._collection_base(project_id)

        eng_a = f"{coll_base}/engines/{student_a.search_engine_id()}"
        eng_b = f"{coll_base}/engines/{student_b.search_engine_id()}"
        ds_a = f"{coll_base}/dataStores/{student_a.search_datastore_id()}"
        ds_b = f"{coll_base}/dataStores/{student_b.search_datastore_id()}"
        bkt_b_uri = f"gs://{student_b.bucket_name(project_id)}/*"

        outcomes: list[CheckOutcome] = []

        # 1. Positive: Student A searches own Engine eng-<a> servingConfigs/default_search (200)
        search_a_sc = f"{eng_a}/servingConfigs/default_search"
        search_a_resp = client_a.post(
            f"{DISCOVERY_API_BASE}/{search_a_sc}:search",
            limiter_name="discovery_engine",
            json={
                "servingConfig": search_a_sc,
                "query": "manualground isolation verification",
                "pageSize": 5,
            },
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="search.engine_search_own",
                kind="POSITIVE",
                actor=student_a.slug,
                target=search_a_sc,
                passed=search_a_resp.status_code == 200,
                expected="HTTP 200",
                actual=f"HTTP {search_a_resp.status_code}",
                detail="Search query against own Engine default_search serving config",
            )
        )

        # 2. Negative Cross-Student: Student A cannot search peer Engine eng-<b> (403)
        search_b_sc = f"{eng_b}/servingConfigs/default_search"
        search_b_resp = client_a.post(
            f"{DISCOVERY_API_BASE}/{search_b_sc}:search",
            limiter_name="discovery_engine",
            json={
                "servingConfig": search_b_sc,
                "query": "unauthorized peer search",
                "pageSize": 5,
            },
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="search.engine_search_cross_student_denied",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=search_b_sc,
                passed=search_b_resp.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {search_b_resp.status_code}",
                detail="Cross-student search on peer Engine blocked by resource-level IAM",
            )
        )

        # 3. Negative Cross-Student: Student A cannot update peer Engine eng-<b> (403)
        patch_eng_b_resp = client_a.patch(
            f"{DISCOVERY_API_BASE}/{eng_b}",
            limiter_name="discovery_engine",
            params={"updateMask": "displayName"},
            json={"displayName": "unauthorized-peer-engine-edit"},
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="search.engine_update_cross_student_denied",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=eng_b,
                passed=patch_eng_b_resp.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {patch_eng_b_resp.status_code}",
                detail="Cross-student PATCH on peer Engine blocked",
            )
        )

        # 4. Negative Cross-Student: Student A cannot delete peer Engine eng-<b> (403)
        del_eng_b_resp = client_a.delete(
            f"{DISCOVERY_API_BASE}/{eng_b}",
            limiter_name="discovery_engine",
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="search.engine_delete_cross_student_denied",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=eng_b,
                passed=del_eng_b_resp.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {del_eng_b_resp.status_code}",
                detail="Engine deletion blocked by resource IAM and Folder IAM Deny v2",
            )
        )

        # 5. Negative Cross-Student: Student A cannot update peer DataStore ds-<b> (403)
        patch_ds_b_resp = client_a.patch(
            f"{DISCOVERY_API_BASE}/{ds_b}",
            limiter_name="discovery_engine",
            params={"updateMask": "displayName"},
            json={"displayName": "unauthorized-peer-datastore-edit"},
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="search.datastore_update_cross_student_denied",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=ds_b,
                passed=patch_ds_b_resp.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {patch_ds_b_resp.status_code}",
                detail="Cross-student PATCH on peer DataStore blocked",
            )
        )

        # 6. Negative Cross-Student: Student A cannot delete peer DataStore ds-<b> (403)
        del_ds_b_resp = client_a.delete(
            f"{DISCOVERY_API_BASE}/{ds_b}",
            limiter_name="discovery_engine",
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="search.datastore_delete_cross_student_denied",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=ds_b,
                passed=del_ds_b_resp.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {del_ds_b_resp.status_code}",
                detail="DataStore deletion blocked by resource IAM and Folder IAM Deny v2",
            )
        )

        # 7. Negative Cross-Student / Confused-Deputy Guardrail:
        # Student A cannot import from gs://bkt-<proj>-<student_b>/* into own ds-<a> (403)
        confused_deputy_resp = client_a.post(
            f"{DISCOVERY_API_BASE}/{ds_a}/branches/0/documents:import",
            limiter_name="import_documents",
            json={
                "gcsSource": {
                    "inputUris": [bkt_b_uri],
                    "dataSchema": "content",
                },
                "reconciliationMode": "INCREMENTAL",
            },
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="search.cross_bucket_import_denied",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=f"{ds_a}/branches/0/documents:import<-{bkt_b_uri}",
                passed=confused_deputy_resp.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {confused_deputy_resp.status_code}",
                detail="Blocks Discovery Engine P4SA cross-bucket ImportDocuments confused deputy",
            )
        )

        return outcomes
