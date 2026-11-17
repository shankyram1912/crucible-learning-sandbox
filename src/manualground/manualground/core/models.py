"""Core data models for ManualGround provisioning and isolation verification."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, model_validator

from manualground.core.naming import email_to_slug, normalize_slug, validate_email


class ServiceName(str, Enum):
    """Supported multi-tenant sandbox services inside a ManualGround shard."""

    GEMINI_SA = "gemini"
    GCS = "gcs"
    CLOUD_RUN = "run"
    CLOUD_SQL = "sql"
    FIRESTORE = "firestore"
    VERTEX_SEARCH = "search"


class StudentSpec(BaseModel):
    """Normalized identity and deterministic per-service resource names for one student."""

    email: str
    slug: str = ""
    display_name: str = ""

    @model_validator(mode="after")
    def _normalize_fields(self) -> StudentSpec:
        self.email = validate_email(self.email)
        if self.slug:
            self.slug = normalize_slug(self.slug)
        else:
            self.slug = email_to_slug(self.email)
        self.display_name = self.display_name.strip()
        return self

    def sa_id(self) -> str:
        return f"sa-{self.slug}"[:30].rstrip("-")

    def sa_email(self, project_id: str) -> str:
        return f"{self.sa_id()}@{project_id}.iam.gserviceaccount.com"

    def sql_iam_sa_user(self, project_id: str) -> str:
        return f"{self.sa_id()}@{project_id}.iam"

    def bucket_name(self, project_id: str) -> str:
        return f"bkt-{project_id}-{self.slug}"[:63].rstrip("-")

    def ar_repo_id(self) -> str:
        return f"ar-{self.slug}"[:63].rstrip("-")

    def sql_db_name(self) -> str:
        return f"db_{self.slug.replace('-', '_')}"[:63].rstrip("_")

    def sql_role_name(self) -> str:
        return f"role_{self.slug.replace('-', '_')}"[:63].rstrip("_")

    def firestore_db_id(self) -> str:
        return f"fs-{self.slug}"[:63].rstrip("-")

    def search_datastore_id(self) -> str:
        return f"ds-{self.slug}"[:63].rstrip("-")

    def search_engine_id(self) -> str:
        return f"eng-{self.slug}"[:63].rstrip("-")


class ConditionalBindingSpec(BaseModel):
    """Project-level IAM binding (conditional or unconditional) queued for coalesced commit."""

    role: str
    members: list[str]
    condition_title: str = ""
    condition_expression: str = ""
    condition_description: str = ""


class StepResult(BaseModel):
    """Outcome of one idempotent provisioning step for a student and service."""

    service: ServiceName
    student_slug: str
    action: str
    resource_id: str
    status: Literal["CREATED", "UNCHANGED", "SKIPPED", "FAILED"]
    duration_ms: int = 0
    detail: str = ""


class CheckOutcome(BaseModel):
    """Outcome of a preflight, positive access, cross-student negative, or guardrail check."""

    service: ServiceName
    check_id: str
    kind: Literal["POSITIVE", "NEGATIVE_CROSS_STUDENT", "GUARDRAIL"]
    actor: str
    target: str
    passed: bool
    expected: str
    actual: str
    detail: str = ""
