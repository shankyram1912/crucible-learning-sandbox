"""Protocol and optional base class for ManualGround per-service drivers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from manualground.config import ShardSettings
from manualground.core.http_client import GcpRestClient
from manualground.core.models import (
    CheckOutcome,
    ConditionalBindingSpec,
    ServiceName,
    StepResult,
    StudentSpec,
)


@runtime_checkable
class ServiceDriver(Protocol):
    """Contract implemented by all six ManualGround service drivers."""

    service: ServiceName

    def __init__(self, admin_client: GcpRestClient) -> None: ...

    def preflight(
        self,
        settings: ShardSettings,
        roster: list[StudentSpec],
    ) -> list[CheckOutcome]: ...

    def provision_student(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[StepResult]: ...

    def project_iam_bindings(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[ConditionalBindingSpec]: ...

    def verify_isolation(
        self,
        settings: ShardSettings,
        student_a: StudentSpec,
        student_b: StudentSpec,
        client_a: GcpRestClient,
        client_b: GcpRestClient,
    ) -> list[CheckOutcome]: ...


class BaseServiceDriver:
    """Optional convenience base class storing admin_client and empty project IAM bindings."""

    service: ServiceName

    def __init__(self, admin_client: GcpRestClient) -> None:
        self.admin_client = admin_client
        self.client = admin_client

    def preflight(
        self,
        settings: ShardSettings,
        roster: list[StudentSpec],
    ) -> list[CheckOutcome]:
        return []

    def provision_student(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[StepResult]:
        raise NotImplementedError

    def project_iam_bindings(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[ConditionalBindingSpec]:
        return []

    def verify_isolation(
        self,
        settings: ShardSettings,
        student_a: StudentSpec,
        student_b: StudentSpec,
        client_a: GcpRestClient,
        client_b: GcpRestClient,
    ) -> list[CheckOutcome]:
        raise NotImplementedError
