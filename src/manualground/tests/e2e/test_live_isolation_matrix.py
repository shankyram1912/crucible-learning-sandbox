"""Live GCP Student-A-vs-Student-B cross-tenant verification suite across all 6 services.

Skipped automatically unless ``MG_LIVE_E2E=1`` is set in the environment.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest


MG_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("MG_LIVE_E2E") != "1",
        reason="Live GCP isolation matrix skipped unless MG_LIVE_E2E=1 is set",
    ),
]


def _load_live_settings():
    from manualground.config import ShardSettings

    env_file = os.environ.get("MG_ENV_FILE")
    default_env = MG_ROOT / "initialize.env"
    if env_file and Path(env_file).is_file():
        return ShardSettings(_env_file=env_file)
    if default_env.is_file():
        return ShardSettings(_env_file=str(default_env))
    return ShardSettings()


def _load_two_students():
    from manualground.core.models import StudentSpec
    from manualground.core import naming

    roster_path = Path(
        os.environ.get("MG_E2E_ROSTER", str(MG_ROOT / "rosters" / "sample-2students.csv"))
    )
    if hasattr(naming, "load_roster_csv") and roster_path.is_file():
        students = naming.load_roster_csv(roster_path)
    else:
        assert roster_path.is_file(), f"E2E roster CSV not found at {roster_path}"
        students = []
        with roster_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                email = (row.get("email") or "").strip().lower()
                if not email:
                    continue
                slug = (row.get("slug") or "").strip() or naming.email_to_slug(email)
                display_name = (row.get("display_name") or row.get("name") or "").strip()
                students.append(StudentSpec(email=email, slug=slug, display_name=display_name))

    assert len(students) >= 2, (
        f"Live E2E isolation matrix requires at least 2 students in {roster_path}; got {len(students)}"
    )
    return students[0], students[1]


def _build_student_client(admin_client, student, project_id: str, token_env_var: str):
    explicit_token = os.environ.get(token_env_var, "").strip()
    if explicit_token:
        return admin_client.with_token(explicit_token)
    return admin_client.for_impersonated_sa(student.sa_email(project_id))


def _enabled_service_names() -> list[str]:
    raw = os.environ.get("MG_E2E_SERVICES", "").strip()
    if raw:
        return [item.strip().lower() for item in raw.split(",") if item.strip()]
    return ["gemini", "gcs", "run", "sql", "firestore", "search"]


def _resolve_driver(service_value: str, admin_client):
    from manualground.core.models import ServiceName
    from manualground import services as svc_pkg

    svc_enum = ServiceName(service_value)
    if hasattr(svc_pkg, "get_driver"):
        return svc_pkg.get_driver(svc_enum, admin_client)
    if hasattr(svc_pkg, "build_drivers"):
        drivers = svc_pkg.build_drivers(admin_client, services=[svc_enum])
        if isinstance(drivers, dict):
            return drivers[svc_enum]
        return drivers[0]

    mapping = {
        ServiceName.GEMINI_SA: ("manualground.services.iam_gemini", "IamGeminiDriver"),
        ServiceName.GCS: ("manualground.services.gcs", "GcsDriver"),
        ServiceName.CLOUD_RUN: ("manualground.services.cloud_run", "CloudRunDriver"),
        ServiceName.CLOUD_SQL: ("manualground.services.cloud_sql", "CloudSqlDriver"),
        ServiceName.FIRESTORE: ("manualground.services.firestore", "FirestoreDriver"),
        ServiceName.VERTEX_SEARCH: ("manualground.services.vertex_search", "VertexSearchDriver"),
    }
    mod_name, cls_name = mapping[svc_enum]
    mod = __import__(mod_name, fromlist=[cls_name])
    cls = getattr(mod, cls_name)
    return cls(admin_client)


@pytest.mark.parametrize(
    "service_value",
    ["gemini", "gcs", "run", "sql", "firestore", "search"],
)
def test_live_student_a_vs_student_b_isolation(service_value: str) -> None:
    if service_value not in _enabled_service_names():
        pytest.skip(f"Service {service_value!r} excluded via MG_E2E_SERVICES")

    from manualground.core.http_client import GcpRestClient

    settings = _load_live_settings()
    if service_value == "sql" and not settings.enable_cloud_sql:
        pytest.skip("ENABLE_CLOUD_SQL is false in ShardSettings")

    student_a, student_b = _load_two_students()
    admin_client = GcpRestClient(quota_project=settings.quota_project)
    client_a = _build_student_client(admin_client, student_a, settings.project_id, "MG_STUDENT_A_TOKEN")
    client_b = _build_student_client(admin_client, student_b, settings.project_id, "MG_STUDENT_B_TOKEN")

    driver = _resolve_driver(service_value, admin_client)

    preflight_outcomes = driver.preflight(settings, [student_a, student_b])
    failed_preflight = [c for c in preflight_outcomes if not c.passed]
    assert not failed_preflight, (
        f"Live preflight failed for {service_value}:\n"
        + "\n".join(
            f"  - [{c.check_id}] actor={c.actor} target={c.target} expected={c.expected} actual={c.actual} {c.detail}"
            for c in failed_preflight
        )
    )

    outcomes = driver.verify_isolation(settings, student_a, student_b, client_a, client_b)
    assert outcomes, f"Driver {service_value} returned zero CheckOutcome items in verify_isolation"

    kinds = {c.kind for c in outcomes}
    assert "POSITIVE" in kinds, f"Driver {service_value} did not execute any POSITIVE check: {kinds}"
    assert kinds & {"NEGATIVE_CROSS_STUDENT", "GUARDRAIL"}, (
        f"Driver {service_value} did not execute any adversarial cross-student or guardrail check: {kinds}"
    )

    failures = [c for c in outcomes if not c.passed]
    assert not failures, (
        f"Live isolation failure(s) for {service_value}:\n"
        + "\n".join(
            f"  - [{c.kind}:{c.check_id}] actor={c.actor} target={c.target} "
            f"expected={c.expected} actual={c.actual} detail={c.detail}"
            for c in failures
        )
    )
