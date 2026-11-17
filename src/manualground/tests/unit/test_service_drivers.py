"""Unit tests for all 6 ManualGround ServiceDrivers against a stateful httpx.MockTransport."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import pytest

from tests.conftest import FakeClock
from tests.unit.test_rate_limiter import _make_mock_rest_client


ADMIN_TOKEN = "tok-admin"
STUDENT_A_TOKEN = "tok-student-a"
STUDENT_B_TOKEN = "tok-student-b"


class StatefulGcpMockBackend:
    """Deterministic in-memory simulator of GCP REST APIs across all 6 ManualGround services."""

    def __init__(
        self,
        project_id: str = "mg-ntu-01",
        project_number: str = "123456789012",
        region: str = "asia-southeast1",
        student_a_slug: str = "lsb-student1",
        student_b_slug: str = "lsb-student2",
        student_a_email: str = "lsb-student1@shankyram.altostrat.com",
        student_b_email: str = "lsb-student2@shankyram.altostrat.com",
        allow_cross_tenant_leak: bool = False,
    ) -> None:
        self.project_id = project_id
        self.project_number = project_number
        self.region = region
        self.student_a_slug = student_a_slug
        self.student_b_slug = student_b_slug
        self.student_a_email = student_a_email
        self.student_b_email = student_b_email
        self.allow_cross_tenant_leak = allow_cross_tenant_leak

        self.requests: list[httpx.Request] = []
        self.service_accounts: dict[str, dict[str, Any]] = {
            f"sa-run-auto-owner@{project_id}.iam.gserviceaccount.com": {"bindings": []},
            f"sa-eventarc-invoker@{project_id}.iam.gserviceaccount.com": {"bindings": []},
        }
        self.buckets: dict[str, dict[str, Any]] = {}
        self.gcs_objects: dict[tuple[str, str], bytes] = {}
        self.ar_repos: dict[str, dict[str, Any]] = {}
        self.run_services: dict[str, dict[str, Any]] = {
            "ntu-run-auto-owner": {
                "name": f"projects/{project_id}/locations/{region}/services/ntu-run-auto-owner",
                "uri": "https://ntu-run-auto-owner-xyz.a.run.app",
                "owner_slug": "system",
                "bindings": [],
            }
        }
        self.sql_databases: set[str] = {"postgres"}
        self.sql_users: set[str] = {"postgres"}
        self.firestore_dbs: set[str] = set()
        self.firestore_docs: dict[tuple[str, str], dict[str, Any]] = {}
        self.search_datastores: dict[str, dict[str, Any]] = {}
        self.search_engines: dict[str, dict[str, Any]] = {}
        self.acl_config_enabled: bool = True
        self.project_iam_policy: dict[str, Any] = {
            "version": 3,
            "etag": "BwMockProjEtag1==",
            "bindings": [],
        }

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def _caller_role(self, request: httpx.Request) -> str:
        auth = request.headers.get("authorization", "")
        if STUDENT_A_TOKEN in auth or f"sa-{self.student_a_slug}@" in auth:
            return "student_a"
        if STUDENT_B_TOKEN in auth or f"sa-{self.student_b_slug}@" in auth:
            return "student_b"
        return "admin"

    def _owner_slug_for_caller(self, caller: str) -> str:
        if caller == "student_a":
            return self.student_a_slug
        if caller == "student_b":
            return self.student_b_slug
        return "admin"

    def _can_access_slug(self, caller: str, target_slug: str) -> bool:
        if caller == "admin" or self.allow_cross_tenant_leak:
            return True
        return self._owner_slug_for_caller(caller) == target_slug

    @staticmethod
    def _json_body(request: httpx.Request) -> dict[str, Any]:
        raw = request.read()
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _resp(request: httpx.Request, status: int, payload: Any = None) -> httpx.Response:
        if payload is None:
            return httpx.Response(status_code=status, json={}, request=request)
        if isinstance(payload, (dict, list)):
            return httpx.Response(status_code=status, json=payload, request=request)
        return httpx.Response(status_code=status, text=str(payload), request=request)

    def _forbidden(self, request: httpx.Request, msg: str = "Permission denied") -> httpx.Response:
        return self._resp(
            request,
            403,
            {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": msg}},
        )

    def _already_exists(self, request: httpx.Request, msg: str = "Already exists") -> httpx.Response:
        return self._resp(
            request,
            409,
            {"error": {"code": 409, "status": "ALREADY_EXISTS", "message": msg}},
        )

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        caller = self._caller_role(request)
        parsed = urlparse(str(request.url))
        host = parsed.netloc
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        method = request.method.upper()

        # Generic LRO operation GET across services
        if method == "GET" and "/operations/" in path:
            return self._resp(
                request,
                200,
                {"name": path.lstrip("/"), "done": True, "status": "DONE", "response": {}},
            )

        # 0. Cloud Resource Manager / Service Usage
        if "cloudresourcemanager.googleapis.com" in host:
            if path.endswith(":getIamPolicy"):
                return self._resp(request, 200, self.project_iam_policy)
            if path.endswith(":setIamPolicy"):
                body = self._json_body(request)
                pol = body.get("policy", body)
                pol["etag"] = "BwMockProjEtag2=="
                self.project_iam_policy = pol
                return self._resp(request, 200, self.project_iam_policy)
            return self._resp(
                request,
                200,
                {"projectId": self.project_id, "projectNumber": self.project_number, "state": "ACTIVE"},
            )

        if "serviceusage.googleapis.com" in host:
            return self._resp(request, 200, {"state": "ENABLED", "services": []})

        # 1. IAM + IAM Credentials + Vertex AI Gemini
        if "iamcredentials.googleapis.com" in host:
            m = re.search(r"/serviceAccounts/([^/:]+):generateAccessToken", path)
            sa_email = m.group(1) if m else ""
            sa_slug = sa_email.split("@", 1)[0].removeprefix("sa-")
            if not self._can_access_slug(caller, sa_slug):
                return self._forbidden(request, "Cross-student SA impersonation denied")
            return self._resp(
                request,
                200,
                {"accessToken": f"impersonated-{sa_slug}", "expireTime": "2026-12-31T00:00:00Z"},
            )

        if "iam.googleapis.com" in host:
            if path.endswith("/keys") and method == "POST":
                return self._forbidden(request, "constraints/iam.disableServiceAccountKeyCreation")
            if ":getIamPolicy" in path:
                sa_email = path.split("/serviceAccounts/", 1)[1].split(":", 1)[0]
                info = self.service_accounts.setdefault(sa_email, {"bindings": []})
                return self._resp(request, 200, {"version": 1, "etag": "etag-sa", "bindings": info["bindings"]})
            if ":setIamPolicy" in path:
                if caller != "admin":
                    return self._forbidden(request)
                sa_email = path.split("/serviceAccounts/", 1)[1].split(":", 1)[0]
                body = self._json_body(request)
                pol = body.get("policy", body)
                self.service_accounts.setdefault(sa_email, {})["bindings"] = pol.get("bindings", [])
                return self._resp(request, 200, {"version": 1, "etag": "etag-sa2", "bindings": pol.get("bindings", [])})
            if path.endswith("/serviceAccounts") and method == "GET":
                accounts = [
                    {"name": f"projects/{self.project_id}/serviceAccounts/{e}", "email": e}
                    for e in self.service_accounts
                ]
                return self._resp(request, 200, {"accounts": accounts})
            if path.endswith("/serviceAccounts") and method == "POST":
                if caller != "admin":
                    return self._forbidden(request)
                body = self._json_body(request)
                account_id = body.get("accountId", "")
                sa_email = f"{account_id}@{self.project_id}.iam.gserviceaccount.com"
                if sa_email in self.service_accounts:
                    return self._already_exists(request, f"Service account {sa_email} already exists")
                self.service_accounts[sa_email] = {"bindings": []}
                return self._resp(
                    request,
                    200,
                    {"name": f"projects/{self.project_id}/serviceAccounts/{sa_email}", "email": sa_email},
                )
            if "/serviceAccounts/" in path and method == "GET":
                sa_email = path.split("/serviceAccounts/", 1)[1]
                if sa_email in self.service_accounts:
                    return self._resp(
                        request,
                        200,
                        {"name": f"projects/{self.project_id}/serviceAccounts/{sa_email}", "email": sa_email},
                    )
                return self._resp(request, 404, {"error": {"code": 404, "message": "Not found"}})
            if "/serviceAccounts/" in path and method == "DELETE":
                if caller != "admin":
                    return self._forbidden(request, "Folder IAM Deny serviceAccounts.delete")
                return self._resp(request, 200, {})

        if "aiplatform.googleapis.com" in host:
            if ":generateContent" in path or ":streamGenerateContent" in path or ":countTokens" in path:
                return self._resp(
                    request,
                    200,
                    {"candidates": [{"content": {"role": "model", "parts": [{"text": "Isolated Gemini OK"}]}}]},
                )
            if "/customJobs" in path or "/endpoints" in path or "/models:upload" in path or "/tuningJobs" in path:
                return self._forbidden(request, "Omitted from custom_ntu_gemini_caller")
            return self._resp(request, 200, {})

        # 2. Cloud Storage
        if "storage.googleapis.com" in host:
            # Object upload endpoint: /upload/storage/v1/b/{bucket}/o
            m_up = re.search(r"/upload/storage/v1/b/([^/]+)/o", path)
            if m_up:
                bkt = m_up.group(1)
                slug = bkt.removeprefix(f"bkt-{self.project_id}-")
                if not self._can_access_slug(caller, slug):
                    return self._forbidden(request, f"Cross-student upload to {bkt} blocked")
                obj_name = query.get("name", ["verify.txt"])[0]
                self.gcs_objects[(bkt, obj_name)] = request.read() or b"data"
                return self._resp(request, 200, {"bucket": bkt, "name": obj_name})

            # Bucket IAM: /storage/v1/b/{bucket}/iam
            m_iam = re.search(r"/storage/v1/b/([^/]+)/iam", path)
            if m_iam:
                bkt = m_iam.group(1)
                if bkt not in self.buckets:
                    return self._resp(request, 404, {"error": {"code": 404, "message": "Bucket not found"}})
                if method == "GET":
                    return self._resp(
                        request,
                        200,
                        {"version": 1, "etag": "CAE=", "bindings": self.buckets[bkt]["bindings"]},
                    )
                if method in ("PUT", "POST"):
                    if caller != "admin":
                        return self._forbidden(request, "Folder IAM Deny buckets.setIamPolicy")
                    body = self._json_body(request)
                    self.buckets[bkt]["bindings"] = body.get("bindings", [])
                    return self._resp(request, 200, {"version": 1, "etag": "CAF=", "bindings": body.get("bindings", [])})

            # Object operations: /storage/v1/b/{bucket}/o or /storage/v1/b/{bucket}/o/{object}
            m_obj = re.search(r"/storage/v1/b/([^/]+)/o(?:/(.+))?$", path)
            if m_obj:
                bkt = m_obj.group(1)
                obj_name = m_obj.group(2) or query.get("name", [""])[0]
                slug = bkt.removeprefix(f"bkt-{self.project_id}-")
                if not self._can_access_slug(caller, slug):
                    return self._forbidden(request, f"Cross-student object {method} on {bkt} blocked")
                if method == "POST":
                    self.gcs_objects[(bkt, obj_name or "verify.txt")] = b"data"
                    return self._resp(request, 200, {"bucket": bkt, "name": obj_name or "verify.txt"})
                if method == "GET":
                    if obj_name:
                        return self._resp(request, 200, {"bucket": bkt, "name": obj_name, "content": "ok"})
                    items = [{"name": k[1]} for k in self.gcs_objects if k[0] == bkt]
                    return self._resp(request, 200, {"items": items})
                if method == "DELETE":
                    self.gcs_objects.pop((bkt, obj_name), None)
                    return httpx.Response(status_code=204, request=request)

            # Bucket list / create: /storage/v1/b
            if path.rstrip("/") == "/storage/v1/b":
                if method == "GET":
                    return self._resp(request, 200, {"items": list(self.buckets.values())})
                if method == "POST":
                    if caller != "admin":
                        return self._forbidden(request, "Folder IAM Deny buckets.create")
                    body = self._json_body(request)
                    bkt = body.get("name", "")
                    if bkt in self.buckets:
                        return self._already_exists(request, f"Bucket {bkt} already exists")
                    self.buckets[bkt] = {
                        "name": bkt,
                        "location": body.get("location", self.region),
                        "iamConfiguration": body.get("iamConfiguration", {}),
                        "bindings": [],
                    }
                    return self._resp(request, 200, self.buckets[bkt])

            # Single bucket metadata / delete / patch: /storage/v1/b/{bucket}
            m_bkt = re.search(r"/storage/v1/b/([^/]+)$", path)
            if m_bkt:
                bkt = m_bkt.group(1)
                slug = bkt.removeprefix(f"bkt-{self.project_id}-")
                if method == "DELETE":
                    if caller != "admin":
                        return self._forbidden(request, "Folder IAM Deny buckets.delete")
                    self.buckets.pop(bkt, None)
                    return httpx.Response(status_code=204, request=request)
                if method in ("PATCH", "PUT"):
                    if caller != "admin":
                        return self._forbidden(request, "Folder IAM Deny buckets.update")
                if method == "GET":
                    if bkt not in self.buckets:
                        return self._resp(request, 404, {"error": {"code": 404, "message": "Not found"}})
                    if not self._can_access_slug(caller, slug):
                        return self._forbidden(request, f"Cross-student bucket.get on {bkt} blocked")
                    return self._resp(request, 200, self.buckets[bkt])

        # 3. Artifact Registry + Eventarc + Cloud Run
        if "artifactregistry.googleapis.com" in host:
            if ":getIamPolicy" in path:
                repo_id = path.split("/repositories/", 1)[1].split(":", 1)[0]
                repo = self.ar_repos.setdefault(repo_id, {"bindings": []})
                return self._resp(request, 200, {"version": 1, "etag": "ar-1", "bindings": repo["bindings"]})
            if ":setIamPolicy" in path:
                if caller != "admin":
                    return self._forbidden(request)
                repo_id = path.split("/repositories/", 1)[1].split(":", 1)[0]
                body = self._json_body(request)
                pol = body.get("policy", body)
                self.ar_repos.setdefault(repo_id, {})["bindings"] = pol.get("bindings", [])
                return self._resp(request, 200, pol)
            if path.endswith("/repositories") and method == "POST":
                repo_id = query.get("repositoryId", [""])[0]
                if repo_id in self.ar_repos:
                    return self._already_exists(request, f"Repo {repo_id} already exists")
                self.ar_repos[repo_id] = {"name": f"{path}/{repo_id}", "format": "DOCKER", "bindings": []}
                return self._resp(
                    request,
                    200,
                    {
                        "name": f"projects/{self.project_id}/locations/{self.region}/operations/op-{repo_id}",
                        "done": True,
                        "response": self.ar_repos[repo_id],
                    },
                )
            if path.endswith("/repositories") and method == "GET":
                return self._resp(request, 200, {"repositories": list(self.ar_repos.values())})
            if "/repositories/" in path and method == "GET":
                repo_id = path.split("/repositories/", 1)[1]
                if repo_id in self.ar_repos:
                    return self._resp(request, 200, self.ar_repos[repo_id])
                return self._resp(request, 404, {"error": {"code": 404, "message": "Repo not found"}})

        if "eventarc.googleapis.com" in host:
            return self._resp(
                request,
                200,
                {
                    "triggers": [
                        {
                            "name": f"projects/{self.project_id}/locations/{self.region}/triggers/ntu-run-create-v2",
                            "eventFilters": [
                                {"attribute": "methodName", "value": "google.cloud.run.v2.Services.CreateService"}
                            ],
                        },
                        {
                            "name": f"projects/{self.project_id}/locations/{self.region}/triggers/ntu-run-create-v1",
                            "eventFilters": [
                                {"attribute": "methodName", "value": "google.cloud.run.v1.Services.CreateService"}
                            ],
                        },
                    ]
                },
            )

        if "run.googleapis.com" in host:
            if ":getIamPolicy" in path:
                svc_id = path.split("/services/", 1)[1].split(":", 1)[0]
                svc = self.run_services.get(svc_id)
                if not svc:
                    return self._resp(request, 404, {"error": {"code": 404}})
                return self._resp(request, 200, {"version": 1, "etag": "run-etag", "bindings": svc["bindings"]})
            if ":setIamPolicy" in path:
                if caller != "admin":
                    return self._forbidden(request)
                svc_id = path.split("/services/", 1)[1].split(":", 1)[0]
                body = self._json_body(request)
                pol = body.get("policy", body)
                self.run_services.setdefault(svc_id, {"owner_slug": "admin"})["bindings"] = pol.get("bindings", [])
                return self._resp(request, 200, pol)
            if path.endswith("/services") and method == "GET":
                return self._resp(request, 200, {"services": list(self.run_services.values())})
            if path.endswith("/services") and method == "POST":
                svc_id = query.get("serviceId", ["svc-verify"])[0]
                body = self._json_body(request)
                body_str = json.dumps(body)
                # GPU guardrail check (nvidia-l4 / nodeSelector accelerator)
                if "nvidia" in body_str.lower() or "accelerator" in body_str.lower():
                    return self._forbidden(request, "GPU accelerators denied on Cloud Run")
                # Cross-student runtime SA actAs check!
                tmpl = body.get("template", {})
                runtime_sa = tmpl.get("serviceAccount") or tmpl.get("serviceAccountName") or ""
                if caller != "admin" and runtime_sa:
                    sa_slug = runtime_sa.split("@", 1)[0].removeprefix("sa-")
                    if not self._can_access_slug(caller, sa_slug):
                        return self._forbidden(request, f"iam.serviceAccounts.actAs denied on {runtime_sa}")
                owner_slug = self._owner_slug_for_caller(caller)
                owner_email = self.student_a_email if caller == "student_a" else self.student_b_email
                # Simulate Eventarc auto-owner binding custom_ntu_run_owner immediately on compliant create!
                svc_obj = {
                    "name": f"projects/{self.project_id}/locations/{self.region}/services/{svc_id}",
                    "uri": f"https://{svc_id}-xyz.a.run.app",
                    "owner_slug": owner_slug,
                    "template": tmpl,
                    "bindings": [
                        {
                            "role": f"projects/{self.project_id}/roles/custom_ntu_run_owner",
                            "members": [f"user:{owner_email}"],
                        },
                        {
                            "role": "roles/run.invoker",
                            "members": [
                                f"user:{owner_email}",
                                f"serviceAccount:sa-{owner_slug}@{self.project_id}.iam.gserviceaccount.com",
                            ],
                        },
                    ],
                }
                self.run_services[svc_id] = svc_obj
                return self._resp(
                    request,
                    200,
                    {
                        "name": f"projects/{self.project_id}/locations/{self.region}/operations/op-{svc_id}",
                        "done": True,
                        "response": svc_obj,
                    },
                )
            if "/services/" in path:
                svc_id = path.split("/services/", 1)[1]
                svc = self.run_services.get(svc_id)
                if method == "GET":
                    if not svc:
                        return self._resp(request, 404, {"error": {"code": 404}})
                    return self._resp(request, 200, svc)
                if method in ("PATCH", "PUT"):
                    if not svc:
                        return self._resp(request, 404, {"error": {"code": 404}})
                    body_str = json.dumps(self._json_body(request))
                    if "nvidia" in body_str.lower() or "accelerator" in body_str.lower():
                        return self._forbidden(request, "GPU accelerators denied")
                    if not self._can_access_slug(caller, svc["owner_slug"]):
                        return self._forbidden(request, f"Cross-student PATCH on {svc_id} denied")
                    return self._resp(request, 200, {"name": f"{path}/operations/op-upd", "done": True, "response": svc})
                if method == "DELETE":
                    if not svc:
                        return self._resp(request, 404, {"error": {"code": 404}})
                    if svc_id == "ntu-run-auto-owner" or not self._can_access_slug(caller, svc["owner_slug"]):
                        return self._forbidden(request, f"Cross-student DELETE on {svc_id} denied")
                    self.run_services.pop(svc_id, None)
                    return self._resp(request, 200, {"name": f"{path}/operations/op-del", "done": True})

        # 4. Cloud SQL Admin
        if "sqladmin.googleapis.com" in host:
            if "/operations/" in path and method == "GET":
                return self._resp(request, 200, {"name": "op-sql", "status": "DONE", "done": True})
            if path.endswith("/databases") and method == "GET":
                return self._resp(request, 200, {"items": [{"name": d} for d in sorted(self.sql_databases)]})
            if path.endswith("/databases") and method == "POST":
                if caller != "admin":
                    return self._forbidden(request, "Folder IAM Deny cloudsql.databases.create")
                body = self._json_body(request)
                db_name = body.get("name", "")
                if db_name in self.sql_databases:
                    return self._already_exists(request, f"Database {db_name} already exists")
                self.sql_databases.add(db_name)
                return self._resp(
                    request,
                    200,
                    {
                        "name": "op-sql-db",
                        "status": "DONE",
                        "done": True,
                        "targetLink": f"https://sqladmin.googleapis.com/v1/projects/{self.project_id}/operations/op-sql-db",
                    },
                )
            if "/databases/" in path:
                db_name = path.split("/databases/", 1)[1]
                if method == "DELETE":
                    if caller != "admin":
                        return self._forbidden(request, "Folder IAM Deny cloudsql.databases.delete")
                    self.sql_databases.discard(db_name)
                    return self._resp(request, 200, {"status": "DONE", "done": True})
                if method == "GET":
                    if db_name in self.sql_databases:
                        return self._resp(request, 200, {"name": db_name})
                    return self._resp(request, 404, {"error": {"code": 404}})
                if method in ("PATCH", "PUT"):
                    if caller != "admin":
                        return self._forbidden(request, "Folder IAM Deny cloudsql.databases.update")
            if path.endswith("/users") and method == "GET":
                return self._resp(request, 200, {"items": [{"name": u} for u in sorted(self.sql_users)]})
            if path.endswith("/users") and method in ("POST", "PUT"):
                if caller != "admin":
                    return self._forbidden(request, "Folder IAM Deny cloudsql.users.create")
                body = self._json_body(request)
                uname = body.get("name", "")
                if uname in self.sql_users and method == "POST":
                    return self._already_exists(request, f"SQL user {uname} already exists")
                self.sql_users.add(uname)
                return self._resp(request, 200, {"name": "op-sql-user", "status": "DONE", "done": True})
            if "/users" in path and method == "DELETE":
                if caller != "admin":
                    return self._forbidden(request, "Folder IAM Deny cloudsql.users.delete")
            if "/instances/" in path:
                if method in ("DELETE", "PATCH", "PUT") and caller != "admin":
                    return self._forbidden(request, "Folder IAM Deny cloudsql.instances.delete/update")
                if method == "GET":
                    return self._resp(
                        request,
                        200,
                        {
                            "name": f"sql-{self.project_id}",
                            "state": "RUNNABLE",
                            "databaseVersion": "POSTGRES_16",
                            "region": self.region,
                            "settings": {
                                "databaseFlags": [{"name": "cloudsql.iam_authentication", "value": "on"}],
                                "ipConfiguration": {"sslMode": "ENCRYPTED_ONLY"},
                            },
                        },
                    )

        # 5. Firestore
        if "firestore.googleapis.com" in host:
            # Document CRUD: /v1/projects/{p}/databases/{db}/documents/...
            m_doc = re.search(r"/databases/([^/]+)/documents(?:/(.*))?$", path)
            if m_doc:
                db_id = m_doc.group(1)
                doc_subpath = m_doc.group(2) or ""
                if db_id == "(default)":
                    return self._resp(request, 404, {"error": {"code": 404, "message": "(default) uncreated"}})
                slug = db_id.removeprefix("fs-")
                if not self._can_access_slug(caller, slug):
                    return self._forbidden(request, f"CEL condition blocked access to {db_id}")
                if method in ("POST", "PATCH"):
                    body = self._json_body(request)
                    key = (db_id, doc_subpath or query.get("documentId", ["doc-1"])[0])
                    self.firestore_docs[key] = body
                    return self._resp(
                        request,
                        200,
                        {"name": f"projects/{self.project_id}/databases/{db_id}/documents/{key[1]}", "fields": body.get("fields", {})},
                    )
                if method == "GET":
                    return self._resp(
                        request,
                        200,
                        {"name": f"projects/{self.project_id}/databases/{db_id}/documents/{doc_subpath}", "documents": []},
                    )
                if method == "DELETE":
                    return self._resp(request, 200, {})

            # Database admin endpoints
            if path.endswith("/databases") and method == "GET":
                dbs = [
                    {
                        "name": f"projects/{self.project_id}/databases/{d}",
                        "type": "FIRESTORE_NATIVE",
                        "locationId": self.region,
                    }
                    for d in sorted(self.firestore_dbs)
                ]
                return self._resp(request, 200, {"databases": dbs})
            if path.endswith("/databases") and method == "POST":
                if caller != "admin":
                    return self._forbidden(request, "Folder IAM Deny datastore.databases.create")
                db_id = query.get("databaseId", [""])[0]
                if db_id in self.firestore_dbs:
                    return self._already_exists(request, f"Database {db_id} already exists")
                self.firestore_dbs.add(db_id)
                return self._resp(
                    request,
                    200,
                    {
                        "name": f"projects/{self.project_id}/databases/{db_id}/operations/op-fs",
                        "done": True,
                        "response": {"name": f"projects/{self.project_id}/databases/{db_id}"},
                    },
                )
            m_db = re.search(r"/databases/([^/:]+)$", path)
            if m_db:
                db_id = m_db.group(1)
                if method in ("DELETE", "PATCH"):
                    if caller != "admin":
                        return self._forbidden(request, "Folder IAM Deny datastore.databases.delete/update")
                if method == "GET":
                    if db_id == "(default)" or db_id not in self.firestore_dbs:
                        return self._resp(request, 404, {"error": {"code": 404, "message": "Database not found"}})
                    slug = db_id.removeprefix("fs-")
                    if not self._can_access_slug(caller, slug):
                        return self._forbidden(request)
                    return self._resp(
                        request,
                        200,
                        {"name": f"projects/{self.project_id}/databases/{db_id}", "type": "FIRESTORE_NATIVE"},
                    )

        # 6. Vertex AI Search (Discovery Engine)
        if "discoveryengine.googleapis.com" in host:
            if path.endswith("/aclConfig"):
                if method in ("PATCH", "PUT", "POST") and caller != "admin":
                    return self._forbidden(request)
                return self._resp(
                    request,
                    200,
                    {"name": path.lstrip("/"), "idpConfig": {"idpType": "GSUITE"}},
                )
            if ":getIamPolicy" in path:
                return self._resp(request, 200, {"version": 1, "etag": "de-etag", "bindings": []})
            if ":setIamPolicy" in path:
                if caller != "admin":
                    return self._forbidden(request, "Folder IAM Deny setIamPolicy")
                body = self._json_body(request)
                return self._resp(request, 200, body.get("policy", body))
            if ":import" in path:
                if caller != "admin":
                    return self._forbidden(request, "Folder IAM Deny discoveryengine.documents.import")
                return self._resp(request, 200, {"name": f"{path.split(':import')[0]}/operations/op-imp", "done": True})
            if ":search" in path or ":answer" in path:
                m_eng = re.search(r"/engines/([^/]+)/", path)
                m_ds = re.search(r"/dataStores/([^/]+)/", path)
                target_id = m_eng.group(1) if m_eng else (m_ds.group(1) if m_ds else "")
                slug = target_id.removeprefix("eng-").removeprefix("ds-")
                if not self._can_access_slug(caller, slug):
                    return self._forbidden(request, f"Cross-student search on {target_id} denied")
                return self._resp(request, 200, {"results": [], "summary": {"summaryText": "Isolated RAG OK"}})
            if path.endswith("/dataStores") and method == "GET":
                return self._resp(request, 200, {"dataStores": list(self.search_datastores.values())})
            if path.endswith("/dataStores") and method == "POST":
                if caller != "admin":
                    return self._forbidden(request, "Folder IAM Deny dataStores.create")
                ds_id = query.get("dataStoreId", [""])[0]
                if ds_id in self.search_datastores:
                    return self._already_exists(request, f"DataStore {ds_id} already exists")
                self.search_datastores[ds_id] = {"name": f"{path}/{ds_id}", "displayName": ds_id}
                return self._resp(
                    request,
                    200,
                    {"name": f"{path}/operations/op-{ds_id}", "done": True, "response": self.search_datastores[ds_id]},
                )
            if "/dataStores/" in path:
                ds_id = path.split("/dataStores/", 1)[1].split("/", 1)[0]
                slug = ds_id.removeprefix("ds-")
                if method == "DELETE":
                    return self._forbidden(request, "Folder IAM Deny dataStores.delete")
                if method in ("PATCH", "PUT"):
                    if not self._can_access_slug(caller, slug):
                        return self._forbidden(request, f"Cross-student PATCH on {ds_id} denied")
                    return self._resp(request, 200, self.search_datastores.get(ds_id, {"name": ds_id}))
                if method == "GET":
                    if not self._can_access_slug(caller, slug):
                        return self._forbidden(request, f"Cross-student GET on {ds_id} denied")
                    if ds_id in self.search_datastores:
                        return self._resp(request, 200, self.search_datastores[ds_id])
                    return self._resp(request, 404, {"error": {"code": 404}})
            if path.endswith("/engines") and method == "GET":
                return self._resp(request, 200, {"engines": list(self.search_engines.values())})
            if path.endswith("/engines") and method == "POST":
                if caller != "admin":
                    return self._forbidden(request, "Folder IAM Deny engines.create")
                eng_id = query.get("engineId", [""])[0]
                if eng_id in self.search_engines:
                    return self._already_exists(request, f"Engine {eng_id} already exists")
                self.search_engines[eng_id] = {"name": f"{path}/{eng_id}", "displayName": eng_id}
                return self._resp(
                    request,
                    200,
                    {"name": f"{path}/operations/op-{eng_id}", "done": True, "response": self.search_engines[eng_id]},
                )
            if "/engines/" in path:
                eng_id = path.split("/engines/", 1)[1].split("/", 1)[0]
                slug = eng_id.removeprefix("eng-")
                if method == "DELETE":
                    return self._forbidden(request, "Folder IAM Deny engines.delete")
                if method in ("PATCH", "PUT"):
                    if not self._can_access_slug(caller, slug):
                        return self._forbidden(request, f"Cross-student PATCH on {eng_id} denied")
                    return self._resp(request, 200, self.search_engines.get(eng_id, {"name": eng_id}))
                if method == "GET":
                    if not self._can_access_slug(caller, slug):
                        return self._forbidden(request, f"Cross-student GET on {eng_id} denied")
                    if eng_id in self.search_engines:
                        return self._resp(request, 200, self.search_engines[eng_id])
                    return self._resp(request, 404, {"error": {"code": 404}})

        raise AssertionError(f"Unhandled mock GCP request: {method} {request.url}")


def _make_settings_and_students(tmp_path):
    from manualground.config import ShardSettings
    from manualground.core.models import StudentSpec

    settings = ShardSettings(
        quota_project="mg-ntu-quota",
        org_id="9876543210",
        billing_account_id="01ABCD-23EFGH-45IJKL",
        domain="shankyram.altostrat.com",
        parent_folder_id="folders/600433119916",
        playground_folder_id="folders/700433119917",
        project_id="mg-ntu-01",
        project_number="123456789012",
        region="asia-southeast1",
        student_group_email="ntu-students@shankyram.altostrat.com",
        it_admins_group="ntu-admins@shankyram.altostrat.com",
        preset="dev",
        enable_cloud_sql=True,
        sql_instance_name="sql-mg-ntu-01",
        max_run_services_per_student=3,
        state_dir=tmp_path / "state",
    )
    student_a = StudentSpec(
        email="lsb-student1@shankyram.altostrat.com",
        slug="lsb-student1",
        display_name="Student One",
    )
    student_b = StudentSpec(
        email="lsb-student2@shankyram.altostrat.com",
        slug="lsb-student2",
        display_name="Student Two",
    )
    return settings, student_a, student_b


def _instantiate_driver(service_key: str, admin_client):
    import inspect
    from manualground.core.models import ServiceName

    module_map = {
        "gemini": ("manualground.services.iam_gemini", ServiceName.GEMINI_SA),
        "gcs": ("manualground.services.gcs", ServiceName.GCS),
        "run": ("manualground.services.cloud_run", ServiceName.CLOUD_RUN),
        "sql": ("manualground.services.cloud_sql", ServiceName.CLOUD_SQL),
        "firestore": ("manualground.services.firestore", ServiceName.FIRESTORE),
        "search": ("manualground.services.vertex_search", ServiceName.VERTEX_SEARCH),
    }
    mod_name, svc_enum = module_map[service_key]
    mod = __import__(mod_name, fromlist=["*"])

    for _, obj in inspect.getmembers(mod, inspect.isclass):
        if obj.__module__ == mod_name and getattr(obj, "service", None) == svc_enum:
            return obj(admin_client)
    for _, obj in inspect.getmembers(mod, inspect.isclass):
        if obj.__module__ == mod_name and obj.__name__.endswith("Driver"):
            return obj(admin_client)
    raise AssertionError(f"Could not locate ServiceDriver class inside {mod_name}")


def _make_client_for_backend(backend: StatefulGcpMockBackend, fake_clock: FakeClock, token: str):
    from tests.conftest import MockGcpRouter

    router = MockGcpRouter()
    router.fallback = backend.handle
    return _make_mock_rest_client(router, fake_clock, quota_project="mg-ntu-quota", token=token)


@pytest.mark.parametrize(
    "service_key",
    ["gemini", "gcs", "run", "sql", "firestore", "search"],
)
def test_all_six_drivers_preflight_idempotent_provision_and_verify_isolation(
    service_key: str,
    fake_clock: FakeClock,
    tmp_path,
) -> None:
    settings, student_a, student_b = _make_settings_and_students(tmp_path)
    backend = StatefulGcpMockBackend(project_id=settings.project_id, project_number=settings.project_number)

    admin_client = _make_client_for_backend(backend, fake_clock, ADMIN_TOKEN)
    client_a = _make_client_for_backend(backend, fake_clock, STUDENT_A_TOKEN)
    client_b = _make_client_for_backend(backend, fake_clock, STUDENT_B_TOKEN)

    driver = _instantiate_driver(service_key, admin_client)

    # 1. Preflight must pass cleanly
    pre = driver.preflight(settings, [student_a, student_b])
    assert pre, f"{service_key} preflight returned empty list"
    assert all(c.passed for c in pre), f"{service_key} preflight failed: {[c for c in pre if not c.passed]}"

    # 2. First provision_student for Student A & Student B -> CREATED/UNCHANGED/SKIPPED with zero FAILED
    steps_a1 = driver.provision_student(settings, student_a)
    steps_b1 = driver.provision_student(settings, student_b)
    assert steps_a1, f"{service_key} provision_student returned empty list"
    assert all(s.status != "FAILED" for s in steps_a1), f"First provision failed: {steps_a1}"
    assert any(s.status == "CREATED" for s in steps_a1), f"Expected at least one CREATED step: {steps_a1}"
    assert all(s.status != "FAILED" for s in steps_b1), f"Student B provision failed: {steps_b1}"

    # 3. Second provision_student for Student A -> idempotent 409/existing handling (zero FAILED!)
    steps_a2 = driver.provision_student(settings, student_a)
    assert all(s.status in ("UNCHANGED", "SKIPPED", "CREATED") for s in steps_a2), (
        f"Idempotent re-run of {service_key}.provision_student failed on 409/existing resource: {steps_a2}"
    )

    # 4. verify_isolation -> proves positive 200 AND negative cross-student / guardrail 403 outcomes!
    outcomes = driver.verify_isolation(settings, student_a, student_b, client_a, client_b)
    assert outcomes, f"{service_key} verify_isolation returned empty outcomes"
    kinds = {c.kind for c in outcomes}
    if service_key != "sql":
        assert "POSITIVE" in kinds, f"{service_key} missing POSITIVE isolation outcome: {outcomes}"
    assert kinds & {"NEGATIVE_CROSS_STUDENT", "GUARDRAIL"}, (
        f"{service_key} missing NEGATIVE_CROSS_STUDENT/GUARDRAIL isolation outcome: {outcomes}"
    )
    failed_outcomes = [c for c in outcomes if not c.passed]
    assert not failed_outcomes, f"{service_key} verify_isolation had failures: {failed_outcomes}"


def test_cloud_sql_postgres16_isolation_ddl_revokes_public_and_strips_gserviceaccount(tmp_path) -> None:
    from manualground.services import cloud_sql

    settings, student_a, _ = _make_settings_and_students(tmp_path)

    builder = getattr(cloud_sql, "build_isolation_ddl", None)
    assert callable(builder), "cloud_sql.py must expose build_isolation_ddl(student, project_id)"

    ddl_raw = builder(student_a, settings.project_id)
    ddl = "\n".join(ddl_raw) if isinstance(ddl_raw, (list, tuple)) else str(ddl_raw)

    # Verify exact PostgreSQL 16 isolation invariants
    assert "role_lsb_student1" in ddl
    assert "db_lsb_student1" in ddl
    assert re.search(
        r'REVOKE\s+ALL(?:\s+PRIVILEGES)?\s+ON\s+DATABASE\s+"?db_lsb_student1"?\s+FROM\s+PUBLIC',
        ddl,
        flags=re.IGNORECASE,
    ), f"Missing REVOKE ALL ON DATABASE ... FROM PUBLIC in DDL:\n{ddl}"
    assert re.search(
        r"REVOKE\s+ALL(?:\s+PRIVILEGES)?\s+ON\s+SCHEMA\s+public\s+FROM\s+PUBLIC",
        ddl,
        flags=re.IGNORECASE,
    ), f"Missing REVOKE ALL ON SCHEMA public FROM PUBLIC in DDL:\n{ddl}"
    assert "CONNECTION LIMIT" in ddl.upper()
    assert "sa-lsb-student1@mg-ntu-01.iam" in ddl
    assert "sa-lsb-student1@mg-ntu-01.iam.gserviceaccount.com" not in ddl
    assert "vector" in ddl.lower()
    assert "pgcrypto" in ddl.lower()
    assert "ALTER DEFAULT PRIVILEGES" in ddl.upper()


def test_firestore_driver_emits_strict_equality_conditional_iam_binding(
    fake_clock: FakeClock,
    tmp_path,
) -> None:
    settings, student_a, _ = _make_settings_and_students(tmp_path)
    backend = StatefulGcpMockBackend(project_id=settings.project_id)
    admin_client = _make_client_for_backend(backend, fake_clock, ADMIN_TOKEN)

    fs_driver = _instantiate_driver("firestore", admin_client)
    bindings = fs_driver.project_iam_bindings(settings, student_a)
    assert len(bindings) >= 1

    db_binding = bindings[0]
    assert "custom_ntu_firestore_db_user" in db_binding.role
    assert f"user:{student_a.email}" in db_binding.members
    assert f"serviceAccount:{student_a.sa_email(settings.project_id)}" in db_binding.members
    assert 'resource.type == "firestore.googleapis.com/Database"' in db_binding.condition_expression
    assert (
        f'resource.name == "projects/{settings.project_id}/databases/{student_a.firestore_db_id()}"'
        in db_binding.condition_expression
    )
    assert "startsWith" not in db_binding.condition_expression


@pytest.mark.parametrize(
    "service_key",
    ["gemini", "gcs", "run", "firestore", "search"],
)
def test_drivers_detect_simulated_cross_tenant_leak(
    service_key: str,
    fake_clock: FakeClock,
    tmp_path,
) -> None:
    """Prove verify_isolation genuinely fails when cross-student RBAC is broken."""
    settings, student_a, student_b = _make_settings_and_students(tmp_path)
    leaky_backend = StatefulGcpMockBackend(
        project_id=settings.project_id,
        project_number=settings.project_number,
        allow_cross_tenant_leak=True,
    )

    admin_client = _make_client_for_backend(leaky_backend, fake_clock, ADMIN_TOKEN)
    client_a = _make_client_for_backend(leaky_backend, fake_clock, STUDENT_A_TOKEN)
    client_b = _make_client_for_backend(leaky_backend, fake_clock, STUDENT_B_TOKEN)

    driver = _instantiate_driver(service_key, admin_client)
    driver.provision_student(settings, student_a)
    driver.provision_student(settings, student_b)

    outcomes = driver.verify_isolation(settings, student_a, student_b, client_a, client_b)
    cross_failures = [
        c for c in outcomes if c.kind == "NEGATIVE_CROSS_STUDENT" and not c.passed
    ]
    assert cross_failures, (
        f"{service_key}.verify_isolation failed to catch simulated cross-student leak: {outcomes}"
    )


def test_cloud_sql_driver_connect_probe_detects_cross_student_connect_leak(
    fake_clock: FakeClock,
    tmp_path,
) -> None:
    from manualground.services.cloud_sql import CloudSqlDriver

    settings, student_a, student_b = _make_settings_and_students(tmp_path)
    backend = StatefulGcpMockBackend(project_id=settings.project_id)
    admin_client = _make_client_for_backend(backend, fake_clock, ADMIN_TOKEN)
    client_a = _make_client_for_backend(backend, fake_clock, STUDENT_A_TOKEN)
    client_b = _make_client_for_backend(backend, fake_clock, STUDENT_B_TOKEN)

    # Probe returns True even for Student B's DB -> simulates missing REVOKE ALL FROM PUBLIC!
    leaky_sql_driver = CloudSqlDriver(admin_client, sql_connect_probe=lambda _stu, _db: True)
    leaky_sql_driver.provision_student(settings, student_a)
    leaky_sql_driver.provision_student(settings, student_b)

    outcomes = leaky_sql_driver.verify_isolation(settings, student_a, student_b, client_a, client_b)
    assert any(c.kind == "NEGATIVE_CROSS_STUDENT" and not c.passed for c in outcomes)
