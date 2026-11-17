"""Lazy service driver registry for ManualGround's six sandbox services."""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from manualground.config import ShardSettings
from manualground.core.http_client import GcpRestClient
from manualground.core.models import ServiceName
from manualground.services.base import BaseServiceDriver, ServiceDriver


class DriverUnavailableError(RuntimeError):
    """Raised when a requested service driver module has not been installed or failed to load."""


@dataclass(frozen=True)
class DriverDescriptor:
    """Metadata describing one registered ManualGround service driver."""

    service: ServiceName
    module_path: str
    preferred_classes: tuple[str, ...]
    limiter_name: str
    summary: str


DRIVER_CATALOG: tuple[DriverDescriptor, ...] = (
    DriverDescriptor(
        service=ServiceName.GEMINI_SA,
        module_path="manualground.services.iam_gemini",
        preferred_classes=("IamGeminiDriver", "GeminiSaDriver", "IamGeminiServiceDriver"),
        limiter_name="iam",
        summary="Per-student service account sa-<student>, impersonation IAM, and Vertex AI Gemini",
    ),
    DriverDescriptor(
        service=ServiceName.GCS,
        module_path="manualground.services.gcs",
        preferred_classes=("GcsDriver", "GCSDriver", "GcsServiceDriver"),
        limiter_name="storage_bucket",
        summary="Dedicated Cloud Storage bucket bkt-<project>-<student> with UBLA and PAP",
    ),
    DriverDescriptor(
        service=ServiceName.CLOUD_RUN,
        module_path="manualground.services.cloud_run",
        preferred_classes=("CloudRunDriver", "RunDriver", "CloudRunServiceDriver"),
        limiter_name="artifact_registry",
        summary="Artifact Registry repo ar-<student> + On-Demand ClickOps Eventarc Auto-Owner",
    ),
    DriverDescriptor(
        service=ServiceName.CLOUD_SQL,
        module_path="manualground.services.cloud_sql",
        preferred_classes=("CloudSqlDriver", "CloudSQLDriver", "CloudSqlServiceDriver"),
        limiter_name="sql_admin",
        summary="PostgreSQL 16 logical database db_<student>, IAM users, and REVOKE PUBLIC DDL",
    ),
    DriverDescriptor(
        service=ServiceName.FIRESTORE,
        module_path="manualground.services.firestore",
        preferred_classes=("FirestoreDriver", "FirestoreServiceDriver"),
        limiter_name="firestore_admin",
        summary="Named Native database fs-<student> + conditional custom_ntu_firestore_db_user IAM",
    ),
    DriverDescriptor(
        service=ServiceName.VERTEX_SEARCH,
        module_path="manualground.services.vertex_search",
        preferred_classes=(
            "VertexSearchDriver",
            "DiscoveryEngineDriver",
            "VertexSearchServiceDriver",
        ),
        limiter_name="discovery_engine",
        summary="Unstructured GCS DataStore ds-<student> and Search Engine eng-<student> with ACLs",
    ),
)

DESCRIPTOR_BY_SERVICE: dict[ServiceName, DriverDescriptor] = {
    d.service: d for d in DRIVER_CATALOG
}

ORDERED_SERVICES: tuple[ServiceName, ...] = tuple(d.service for d in DRIVER_CATALOG)

SERVICE_ALIASES: dict[str, ServiceName] = {
    "gemini": ServiceName.GEMINI_SA,
    "iam": ServiceName.GEMINI_SA,
    "iam_gemini": ServiceName.GEMINI_SA,
    "sa": ServiceName.GEMINI_SA,
    "gcs": ServiceName.GCS,
    "storage": ServiceName.GCS,
    "run": ServiceName.CLOUD_RUN,
    "cloud_run": ServiceName.CLOUD_RUN,
    "cloud-run": ServiceName.CLOUD_RUN,
    "sql": ServiceName.CLOUD_SQL,
    "cloud_sql": ServiceName.CLOUD_SQL,
    "cloud-sql": ServiceName.CLOUD_SQL,
    "firestore": ServiceName.FIRESTORE,
    "fs": ServiceName.FIRESTORE,
    "search": ServiceName.VERTEX_SEARCH,
    "vertex_search": ServiceName.VERTEX_SEARCH,
    "vertex-search": ServiceName.VERTEX_SEARCH,
    "discovery": ServiceName.VERTEX_SEARCH,
}


def parse_service_selection(
    raw_services: Sequence[str] | str | None,
    *,
    settings: ShardSettings | None = None,
) -> list[ServiceName]:
    """Parse --services tokens (comma-separated or repeated) in canonical execution order."""
    if not raw_services:
        selected = list(ORDERED_SERVICES)
        if settings is not None and not settings.enable_cloud_sql:
            selected = [s for s in selected if s != ServiceName.CLOUD_SQL]
        return selected

    items = [raw_services] if isinstance(raw_services, str) else list(raw_services)
    requested: set[ServiceName] = set()
    for item in items:
        for token in item.split(","):
            key = token.strip().lower()
            if not key:
                continue
            if key == "all":
                requested.update(ORDERED_SERVICES)
                continue
            svc = SERVICE_ALIASES.get(key)
            if svc is None:
                valid = ", ".join(s.value for s in ORDERED_SERVICES)
                raise ValueError(
                    f"Unknown service {token!r}. Valid services: {valid}"
                )
            requested.add(svc)

    return [s for s in ORDERED_SERVICES if s in requested]


def load_driver_class(service: ServiceName) -> type[ServiceDriver]:
    """Lazily import and locate the concrete ServiceDriver class for service."""
    desc = DESCRIPTOR_BY_SERVICE[service]
    try:
        module = importlib.import_module(desc.module_path)
    except ModuleNotFoundError as exc:
        raise DriverUnavailableError(
            f"Driver module {desc.module_path!r} for service {service.value!r} "
            f"is not available yet ({exc})."
        ) from exc

    for cls_name in desc.preferred_classes:
        candidate = getattr(module, cls_name, None)
        if inspect.isclass(candidate):
            return candidate

    for obj in vars(module).values():
        if (
            inspect.isclass(obj)
            and obj.__module__ == module.__name__
            and obj is not BaseServiceDriver
            and (
                getattr(obj, "service", None) == service
                or (
                    hasattr(obj, "provision_student")
                    and hasattr(obj, "verify_isolation")
                )
            )
        ):
            return obj

    raise DriverUnavailableError(
        f"Module {desc.module_path!r} does not define a ServiceDriver class "
        f"for {service.value!r}."
    )


def is_driver_available(service: ServiceName) -> bool:
    """Return True if the driver module can be imported cleanly."""
    try:
        load_driver_class(service)
        return True
    except DriverUnavailableError:
        return False


def available_drivers() -> dict[ServiceName, bool]:
    """Map every ServiceName in canonical order to its import availability."""
    return {svc: is_driver_available(svc) for svc in ORDERED_SERVICES}


def get_driver(service: ServiceName, admin_client: GcpRestClient) -> ServiceDriver:
    """Instantiate the ServiceDriver for service with the injected admin_client."""
    driver_cls = load_driver_class(service)
    return driver_cls(admin_client)


def build_drivers(
    services: Iterable[ServiceName],
    admin_client: GcpRestClient,
) -> list[ServiceDriver]:
    """Instantiate drivers in the given order."""
    return [get_driver(svc, admin_client) for svc in services]


__all__ = [
    "BaseServiceDriver",
    "DESCRIPTOR_BY_SERVICE",
    "DRIVER_CATALOG",
    "DriverDescriptor",
    "DriverUnavailableError",
    "ORDERED_SERVICES",
    "SERVICE_ALIASES",
    "ServiceDriver",
    "available_drivers",
    "build_drivers",
    "get_driver",
    "is_driver_available",
    "load_driver_class",
    "parse_service_selection",
]
