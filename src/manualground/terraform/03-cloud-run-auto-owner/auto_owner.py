"""Pure-stdlib Cloud Run v2 Eventarc CloudEvent receiver (`ntu-run-auto-owner`).

Triggered by Cloud Audit Logs (`google.cloud.run.v1.Services.CreateService` and
`google.cloud.run.v2.Services.CreateService`) when a student creates a Cloud Run
service on-demand via Cloud Console ClickOps or `gcloud run deploy`.

Zero third-party dependencies (`<250ms` Python 3.12 cold start):
1. Parses CloudEvent (`v1` & `v2` `CreateService` Admin Activity log entries).
2. Protects `ntu-run-auto-owner` itself and ignores system/admin/workload service accounts.
3. Enforces runtime identity isolation: the newly created service MUST run as the
   creator's own unified workload identity `sa-<slug>@<project>.iam.gserviceaccount.com`
   (deletes services running as peer `sa-<b>@...` or default Compute SA immediately).
4. Enforces `MAX_SERVICES_PER_STUDENT` (default `3`): counts existing regional services
   owned by the creator and immediately deletes any service exceeding the per-student cap.
5. Idempotently merges `projects/<p>/roles/custom_ntu_run_owner` for `user:<creator_email>`
   and `roles/run.invoker` for `user:<creator_email>` + `serviceAccount:sa-<slug>@...`
   via `services:getIamPolicy` -> `services:setIamPolicy` with jittered ETag `409`/`429` retry.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import random
import re
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

LOGGER = logging.getLogger("ntu_run_auto_owner")

SUPPORTED_CREATE_METHODS = frozenset(
    {
        "google.cloud.run.v1.Services.CreateService",
        "google.cloud.run.v2.Services.CreateService",
    }
)

METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
RUN_API_BASE = "https://run.googleapis.com/v2"

_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")
_V2_RESOURCE_RE = re.compile(
    r"^projects/(?P<project>[^/]+)/locations/(?P<location>[^/]+)/services/(?P<service>[^/]+)$"
)
_V2_PARENT_RE = re.compile(
    r"^projects/(?P<project>[^/]+)/locations/(?P<location>[^/]+)$"
)
_V1_NAMESPACE_SVC_RE = re.compile(
    r"^namespaces/(?P<project>[^/]+)/services/(?P<service>[^/]+)$"
)
_V1_NAMESPACE_ONLY_RE = re.compile(r"^namespaces/(?P<project>[^/]+)$")


class CloudRunApiError(RuntimeError):
    """HTTP error returned by the Cloud Run Admin v2 REST API."""

    def __init__(self, status_code: int, message: str, body: dict[str, Any] | None = None) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.body = body or {}


@dataclass(frozen=True)
class AuditServiceEvent:
    """Normalized Cloud Run `CreateService` audit event extracted from a CloudEvent."""

    method_name: str
    principal_email: str
    project_id: str
    location: str
    service_name: str
    attached_service_account: str = ""

    @property
    def resource_name(self) -> str:
        return f"projects/{self.project_id}/locations/{self.location}/services/{self.service_name}"


@dataclass(frozen=True)
class AutoOwnerConfig:
    """Runtime configuration for `ntu-run-auto-owner`."""

    project_id: str = ""
    default_region: str = "asia-southeast1"
    auto_owner_service_name: str = "ntu-run-auto-owner"
    max_services_per_student: int = 3
    ignored_principals: frozenset[str] = field(default_factory=frozenset)
    custom_owner_role_id: str = "custom_ntu_run_owner"
    max_retries: int = 5
    base_backoff_seconds: float = 0.2

    @classmethod
    def from_env(cls) -> AutoOwnerConfig:
        raw_ignored = os.environ.get("IGNORED_PRINCIPALS", "")
        ignored = frozenset(
            p.strip().lower() for p in raw_ignored.split(",") if p.strip()
        )
        return cls(
            project_id=os.environ.get("MG_PROJECT_ID", "").strip(),
            default_region=os.environ.get("DEFAULT_REGION", "asia-southeast1").strip(),
            auto_owner_service_name=os.environ.get(
                "AUTO_OWNER_SERVICE_NAME", "ntu-run-auto-owner"
            ).strip(),
            max_services_per_student=int(os.environ.get("MAX_SERVICES_PER_STUDENT", "3")),
            ignored_principals=ignored,
            custom_owner_role_id=os.environ.get(
                "CUSTOM_OWNER_ROLE_ID", "custom_ntu_run_owner"
            ).strip(),
        )


@dataclass(frozen=True)
class ReconcileResult:
    """Deterministic outcome of processing one CloudEvent."""

    action: str
    resource_name: str = ""
    principal_email: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "action": self.action,
            "resource_name": self.resource_name,
            "principal_email": self.principal_email,
            "detail": self.detail,
        }


def email_to_slug(email: str, max_length: int = 80) -> str:
    """Normalize a student email local-part into the canonical ManualGround slug."""
    cleaned_email = email.strip().lower()
    if "@" not in cleaned_email:
        raise ValueError(f"Invalid email address: {email!r}")
    local_part, _ = cleaned_email.split("@", 1)
    slug = _NON_SLUG_RE.sub("-", local_part).strip("-")
    if max_length > 0:
        slug = slug[:max_length].rstrip("-")
    if not slug:
        raise ValueError(f"Cannot derive student slug from email: {email!r}")
    return slug


def student_sa_id(slug: str) -> str:
    """Return the 30-char bounded unified student service account ID (`sa-<slug>`)."""
    return f"sa-{slug}"[:30].rstrip("-")


def expected_student_sa(email: str, project_id: str) -> str:
    """Return the creator's sole permitted Cloud Run runtime service account email."""
    slug = email_to_slug(email)
    return f"{student_sa_id(slug)}@{project_id}.iam.gserviceaccount.com"


def is_ignored_principal(principal_email: str, config: AutoOwnerConfig) -> bool:
    """Return True for empty, Google/project service account, or admin-exempted principals."""
    normalized = principal_email.strip().lower()
    if not normalized or "@" not in normalized:
        return True
    if normalized.endswith(".gserviceaccount.com"):
        return True
    if normalized in config.ignored_principals:
        return True
    return False


def _extract_service_account_from_proto(proto: dict[str, Any]) -> str:
    """Extract attached runtime serviceAccount from v1 or v2 request/response payload if present."""
    for container_key in ("response", "request"):
        block = proto.get(container_key)
        if not isinstance(block, dict):
            continue
        # Cloud Run v2 Service or request.service
        svc_obj = block.get("service") if isinstance(block.get("service"), dict) else block
        if isinstance(svc_obj, dict):
            tmpl = svc_obj.get("template")
            if isinstance(tmpl, dict):
                # v2: template.serviceAccount
                sa = tmpl.get("serviceAccount") or tmpl.get("service_account")
                if isinstance(sa, str) and sa.strip():
                    return sa.strip()
            # v1 Knative: spec.template.spec.serviceAccountName
            spec = svc_obj.get("spec")
            if isinstance(spec, dict):
                t_spec = spec.get("template", {})
                if isinstance(t_spec, dict):
                    inner_spec = t_spec.get("spec", {})
                    if isinstance(inner_spec, dict):
                        sa_v1 = inner_spec.get("serviceAccountName")
                        if isinstance(sa_v1, str) and sa_v1.strip():
                            return sa_v1.strip()
    return ""


def parse_audit_cloudevent(
    payload: dict[str, Any],
    default_project_id: str = "",
    default_region: str = "asia-southeast1",
) -> AuditServiceEvent | None:
    """Parse a CloudEvent JSON payload (structured or binary mode) for Run v1/v2 CreateService.

    Returns `None` when the event is not a successful `CreateService` audit entry.
    """
    if not isinstance(payload, dict):
        return None

    data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    proto = data_obj.get("protoPayload")
    if not isinstance(proto, dict):
        return None

    method_name = str(proto.get("methodName", "")).strip()
    if method_name not in SUPPORTED_CREATE_METHODS:
        return None

    # Ignore failed API attempts that GCP already rejected (non-zero RPC status code).
    status_obj = proto.get("status")
    if isinstance(status_obj, dict):
        code = status_obj.get("code", 0)
        if code not in (0, None, "0"):
            return None

    auth_info = proto.get("authenticationInfo")
    principal_email = ""
    if isinstance(auth_info, dict):
        principal_email = str(auth_info.get("principalEmail", "")).strip().lower()

    resource_obj = data_obj.get("resource") if isinstance(data_obj.get("resource"), dict) else {}
    labels = resource_obj.get("labels") if isinstance(resource_obj.get("labels"), dict) else {}

    raw_resource_name = str(proto.get("resourceName", "")).strip()
    req = proto.get("request") if isinstance(proto.get("request"), dict) else {}
    resp = proto.get("response") if isinstance(proto.get("response"), dict) else {}

    project_id = str(labels.get("project_id", "")).strip() or default_project_id
    location = str(labels.get("location", "")).strip() or default_region
    service_name = str(labels.get("service_name", "")).strip()

    # 1. Match v2 full service path: projects/<p>/locations/<l>/services/<s>
    m_v2 = _V2_RESOURCE_RE.match(raw_resource_name)
    if m_v2:
        project_id = m_v2.group("project")
        location = m_v2.group("location")
        service_name = m_v2.group("service")
    else:
        # 2. Match v2 parent path: projects/<p>/locations/<l> + request.serviceId / response.name
        m_v2_parent = _V2_PARENT_RE.match(raw_resource_name)
        if m_v2_parent:
            project_id = m_v2_parent.group("project")
            location = m_v2_parent.group("location")

        # 3. Match v1 Knative path: namespaces/<p>/services/<s> or namespaces/<p>
        m_v1 = _V1_NAMESPACE_SVC_RE.match(raw_resource_name)
        if m_v1:
            project_id = m_v1.group("project")
            service_name = m_v1.group("service")
        else:
            m_v1_ns = _V1_NAMESPACE_ONLY_RE.match(raw_resource_name)
            if m_v1_ns:
                project_id = m_v1_ns.group("project")

    # Fallback extraction from response.name / request.serviceId / v1 metadata.name
    if not service_name:
        resp_name = str(resp.get("name", "")).strip()
        m_resp = _V2_RESOURCE_RE.match(resp_name)
        if m_resp:
            project_id = project_id or m_resp.group("project")
            location = m_resp.group("location")
            service_name = m_resp.group("service")

    if not service_name:
        service_name = str(req.get("serviceId") or req.get("service_id") or "").strip()

    if not service_name:
        for obj in (resp, req.get("service") if isinstance(req.get("service"), dict) else {}):
            if isinstance(obj, dict):
                meta = obj.get("metadata")
                if isinstance(meta, dict) and meta.get("name"):
                    service_name = str(meta["name"]).strip()
                    if meta.get("namespace") and not project_id:
                        project_id = str(meta["namespace"]).strip()
                    break

    if not (project_id and location and service_name):
        return None

    attached_sa = _extract_service_account_from_proto(proto)
    return AuditServiceEvent(
        method_name=method_name,
        principal_email=principal_email,
        project_id=project_id,
        location=location,
        service_name=service_name,
        attached_service_account=attached_sa,
    )


def merge_owner_iam_policy(
    policy: dict[str, Any],
    *,
    project_id: str,
    principal_email: str,
    student_sa_email: str,
    custom_owner_role_id: str = "custom_ntu_run_owner",
) -> tuple[dict[str, Any], bool]:
    """Idempotently merge `custom_ntu_run_owner` and `roles/run.invoker` into a policy dict.

    Returns `(updated_policy, changed)`. Preserves existing bindings, conditions, and ETag.
    """
    owner_role = f"projects/{project_id}/roles/{custom_owner_role_id}"
    invoker_role = "roles/run.invoker"
    user_member = f"user:{principal_email.strip().lower()}"
    sa_member = f"serviceAccount:{student_sa_email.strip().lower()}"

    desired: dict[str, list[str]] = {
        owner_role: [user_member],
        invoker_role: [user_member, sa_member],
    }

    existing_bindings = policy.get("bindings", [])
    new_bindings: list[dict[str, Any]] = []
    for b in existing_bindings:
        if isinstance(b, dict):
            copied = dict(b)
            copied["members"] = list(b.get("members", []))
            new_bindings.append(copied)

    changed = False
    for role, required_members in desired.items():
        # Match unconditional binding for this role
        target_binding: dict[str, Any] | None = None
        for b in new_bindings:
            if b.get("role") == role and not b.get("condition"):
                target_binding = b
                break
        if target_binding is None:
            target_binding = {"role": role, "members": []}
            new_bindings.append(target_binding)

        existing_lower = {m.lower(): m for m in target_binding["members"]}
        for req_member in required_members:
            if req_member.lower() not in existing_lower:
                target_binding["members"].append(req_member)
                existing_lower[req_member.lower()] = req_member
                changed = True

    updated: dict[str, Any] = dict(policy)
    updated["version"] = max(int(policy.get("version", 1) or 1), 3)
    updated["bindings"] = new_bindings
    return updated, changed


def fetch_metadata_access_token(timeout_s: float = 5.0) -> str:
    """Fetch an OAuth2 access token from the Cloud Run compute metadata server."""
    req = urllib.request.Request(
        METADATA_TOKEN_URL,
        headers={"Metadata-Flavor": "Google"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return str(data["access_token"])


HttpRequester = Callable[[str, str, dict[str, Any] | None], tuple[int, dict[str, Any]]]


class CloudRunAdminClient:
    """Minimal pure-stdlib REST client for Cloud Run v2 Service & IAM endpoints."""

    def __init__(
        self,
        *,
        token_provider: Callable[[], str] = fetch_metadata_access_token,
        requester: HttpRequester | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        self._token_provider = token_provider
        self._requester = requester
        self._timeout_s = timeout_s

    def request(
        self,
        method: str,
        url: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._requester is not None:
            status, payload = self._requester(method, url, json_body)
            if status >= 400:
                msg = str(payload.get("error", {}).get("message", payload))
                raise CloudRunApiError(status, msg, payload)
            return payload

        token = self._token_provider()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        raw_data: bytes | None = None
        if json_body is not None:
            raw_data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=raw_data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            err_raw = exc.read().decode("utf-8", errors="replace")
            try:
                err_json = json.loads(err_raw) if err_raw.strip() else {}
            except json.JSONDecodeError:
                err_json = {"raw": err_raw}
            msg = str(err_json.get("error", {}).get("message", err_raw or exc.reason))
            raise CloudRunApiError(exc.code, msg, err_json) from exc

    def get_service(self, resource_name: str) -> dict[str, Any] | None:
        url = f"{RUN_API_BASE}/{resource_name}"
        try:
            return self.request("GET", url)
        except CloudRunApiError as exc:
            if exc.status_code == 404:
                return None
            raise

    def list_services(self, project_id: str, location: str) -> list[dict[str, Any]]:
        services: list[dict[str, Any]] = []
        page_token = ""
        while True:
            query = {"pageSize": "100"}
            if page_token:
                query["pageToken"] = page_token
            qs = urllib.parse.urlencode(query)
            url = f"{RUN_API_BASE}/projects/{project_id}/locations/{location}/services?{qs}"
            resp = self.request("GET", url)
            batch = resp.get("services", [])
            if isinstance(batch, list):
                services.extend(s for s in batch if isinstance(s, dict))
            page_token = str(resp.get("nextPageToken", "")).strip()
            if not page_token:
                break
        return services

    def delete_service(self, resource_name: str) -> bool:
        url = f"{RUN_API_BASE}/{resource_name}"
        try:
            self.request("DELETE", url)
            return True
        except CloudRunApiError as exc:
            if exc.status_code == 404:
                return False
            raise

    def get_iam_policy(self, resource_name: str) -> dict[str, Any]:
        url = f"{RUN_API_BASE}/{resource_name}:getIamPolicy?options.requestedPolicyVersion=3"
        return self.request("GET", url)

    def set_iam_policy(self, resource_name: str, policy: dict[str, Any]) -> dict[str, Any]:
        url = f"{RUN_API_BASE}/{resource_name}:setIamPolicy"
        return self.request("POST", url, {"policy": policy})


def _extract_service_short_name(svc: dict[str, Any]) -> str:
    full_name = str(svc.get("name", "")).strip()
    if "/services/" in full_name:
        return full_name.rsplit("/services/", 1)[-1]
    return full_name


def _is_service_owned_by_student(
    svc: dict[str, Any],
    *,
    principal_email: str,
    expected_sa: str,
    slug: str,
) -> bool:
    """Determine if a Cloud Run v2 Service belongs to `principal_email`."""
    tmpl = svc.get("template")
    if isinstance(tmpl, dict):
        svc_sa = str(tmpl.get("serviceAccount") or tmpl.get("service_account") or "").strip().lower()
        if svc_sa and svc_sa == expected_sa.lower():
            return True

    creator = str(svc.get("creator", "")).strip().lower()
    if creator and creator == principal_email.lower():
        return True

    labels = svc.get("labels")
    if isinstance(labels, dict):
        if str(labels.get("mg-owner-slug", "")).strip().lower() == slug.lower():
            return True

    return False


def reconcile_cloudevent(
    payload: dict[str, Any],
    *,
    client: CloudRunAdminClient,
    config: AutoOwnerConfig | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> ReconcileResult:
    """Process a CloudEvent payload and enforce ManualGround Cloud Run ownership & guardrails."""
    cfg = config or AutoOwnerConfig.from_env()
    event = parse_audit_cloudevent(
        payload,
        default_project_id=cfg.project_id,
        default_region=cfg.default_region,
    )
    if event is None:
        return ReconcileResult(
            action="IGNORED_UNRECOGNIZED_EVENT",
            detail="Event is not a successful Cloud Run v1/v2 CreateService audit entry.",
        )

    # 1. Self-protection: never alter or delete ntu-run-auto-owner itself.
    if event.service_name == cfg.auto_owner_service_name:
        return ReconcileResult(
            action="IGNORED_PROTECTED_SERVICE",
            resource_name=event.resource_name,
            principal_email=event.principal_email,
            detail=f"Protected infrastructure service {cfg.auto_owner_service_name}.",
        )

    # 2. Ignore system, Google service agent, automation, or workload service account principals.
    if is_ignored_principal(event.principal_email, cfg):
        return ReconcileResult(
            action="IGNORED_SYSTEM_PRINCIPAL",
            resource_name=event.resource_name,
            principal_email=event.principal_email,
            detail="Creator is a service account or exempted admin principal.",
        )

    slug = email_to_slug(event.principal_email)
    student_sa = expected_student_sa(event.principal_email, event.project_id)

    # 3. Fetch live service state (handle race if student or admin already deleted it).
    live_service = client.get_service(event.resource_name)
    if live_service is None:
        return ReconcileResult(
            action="IGNORED_NOT_FOUND",
            resource_name=event.resource_name,
            principal_email=event.principal_email,
            detail="Service no longer exists (404).",
        )

    live_tmpl = live_service.get("template") if isinstance(live_service.get("template"), dict) else {}
    attached_sa = (
        str(live_tmpl.get("serviceAccount") or live_tmpl.get("service_account") or "").strip()
        or event.attached_service_account
    )

    # 4. Enforce runtime service account: must match creator's unified sa-<slug>@<project>.iam.gserviceaccount.com.
    if attached_sa.lower() != student_sa.lower():
        client.delete_service(event.resource_name)
        return ReconcileResult(
            action="DELETED_UNAUTHORIZED_SA",
            resource_name=event.resource_name,
            principal_email=event.principal_email,
            detail=(
                f"Deleted service with unauthorized serviceAccount={attached_sa!r} "
                f"(expected {student_sa!r})."
            ),
        )

    # 5. Enforce per-student regional service cap (MAX_SERVICES_PER_STUDENT, default 3).
    if cfg.max_services_per_student > 0:
        all_services = client.list_services(event.project_id, event.location)
        prior_owned = [
            svc
            for svc in all_services
            if _extract_service_short_name(svc) != event.service_name
            and _extract_service_short_name(svc) != cfg.auto_owner_service_name
            and _is_service_owned_by_student(
                svc,
                principal_email=event.principal_email,
                expected_sa=student_sa,
                slug=slug,
            )
        ]
        if len(prior_owned) >= cfg.max_services_per_student:
            client.delete_service(event.resource_name)
            return ReconcileResult(
                action="DELETED_QUOTA_EXCEEDED",
                resource_name=event.resource_name,
                principal_email=event.principal_email,
                detail=(
                    f"Deleted service exceeding MAX_SERVICES_PER_STUDENT="
                    f"{cfg.max_services_per_student} (already owns {len(prior_owned)})."
                ),
            )

    # 6. Idempotent getIamPolicy -> merge custom_ntu_run_owner + roles/run.invoker -> setIamPolicy with retry.
    last_err: Exception | None = None
    for attempt in range(cfg.max_retries):
        try:
            current_policy = client.get_iam_policy(event.resource_name)
            merged_policy, changed = merge_owner_iam_policy(
                current_policy,
                project_id=event.project_id,
                principal_email=event.principal_email,
                student_sa_email=student_sa,
                custom_owner_role_id=cfg.custom_owner_role_id,
            )
            if not changed:
                return ReconcileResult(
                    action="UNCHANGED",
                    resource_name=event.resource_name,
                    principal_email=event.principal_email,
                    detail="Per-service owner and invoker IAM bindings already present.",
                )
            client.set_iam_policy(event.resource_name, merged_policy)
            return ReconcileResult(
                action="BOUND_OWNER",
                resource_name=event.resource_name,
                principal_email=event.principal_email,
                detail=(
                    f"Bound {cfg.custom_owner_role_id} and roles/run.invoker "
                    f"for {event.principal_email} and {student_sa}."
                ),
            )
        except CloudRunApiError as exc:
            last_err = exc
            if exc.status_code in (409, 429, 500, 502, 503, 504) and attempt + 1 < cfg.max_retries:
                delay = cfg.base_backoff_seconds * (2**attempt) + random.uniform(0.0, 0.05)
                sleep_fn(delay)
                continue
            raise

    assert last_err is not None
    raise last_err


def make_http_handler(
    client: CloudRunAdminClient,
    config: AutoOwnerConfig,
) -> type[BaseHTTPRequestHandler]:
    """Create a thread-safe BaseHTTPRequestHandler class bound to `client` and `config`."""

    class AutoOwnerHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            LOGGER.info(fmt, *args)

        def _write_json(self, status: int, body: dict[str, Any]) -> None:
            encoded = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/healthz", "/readyz"):
                self._write_json(200, {"status": "ok", "service": config.auto_owner_service_name})
            else:
                self._write_json(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            content_len = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(content_len) if content_len > 0 else b"{}"
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError:
                self._write_json(400, {"error": "invalid_json"})
                return

            try:
                result = reconcile_cloudevent(payload, client=client, config=config)
                LOGGER.info("Reconciled CloudEvent: %s", json.dumps(result.to_dict()))
                self._write_json(200, result.to_dict())
            except CloudRunApiError as exc:
                LOGGER.exception("Cloud Run API error while reconciling CloudEvent")
                status = 500 if exc.status_code in (409, 429, 500, 502, 503, 504) else 200
                self._write_json(status, {"error": str(exc), "status_code": exc.status_code})
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Unexpected error in ntu-run-auto-owner")
                self._write_json(500, {"error": str(exc)})

    return AutoOwnerHandler


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = AutoOwnerConfig.from_env()
    client = CloudRunAdminClient()
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), make_http_handler(client, config))
    LOGGER.info(
        "Starting %s on 0.0.0.0:%d (project=%s, region=%s, max_services=%d)",
        config.auto_owner_service_name,
        port,
        config.project_id,
        config.default_region,
        config.max_services_per_student,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
