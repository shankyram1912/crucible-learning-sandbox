"""Resumable per-student, per-service checkpoint ledger for Layer 2 provisioning."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from manualground.core.models import ServiceName, StepResult, StudentSpec


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ServiceCheckpoint(BaseModel):
    """Persisted checkpoint for a single (student, service) provisioning slice."""

    service: ServiceName
    student_slug: str
    student_email: str
    state: Literal["COMPLETED", "FAILED"]
    updated_at: str
    steps: list[StepResult] = Field(default_factory=list)
    error: str = ""


class IamCoalesceCheckpoint(BaseModel):
    """Persisted summary of the most recent Stage C coalesced IAM commit."""

    updated_at: str
    total_principals: int
    conditional_bindings: int
    attempts: int = 1


class LedgerData(BaseModel):
    """Root JSON document persisted to <state_dir>/<project_id>-ledger.json."""

    project_id: str
    updated_at: str = Field(default_factory=_utc_now_iso)
    students: dict[str, dict[str, ServiceCheckpoint]] = Field(default_factory=dict)
    iam_coalesce: IamCoalesceCheckpoint | None = None


class ProvisioningLedger:
    """Thread-safe JSON checkpoint store enabling resumable roster provisioning."""

    def __init__(self, state_dir: Path, project_id: str) -> None:
        self.state_dir = Path(state_dir)
        self.project_id = project_id or "unconfigured"
        self.path = self.state_dir / f"{self.project_id}-ledger.json"
        self._lock = threading.Lock()
        self._data: LedgerData | None = None

    def load(self) -> LedgerData:
        with self._lock:
            return self._load_unlocked()

    def _load_unlocked(self) -> LedgerData:
        if self._data is not None:
            return self._data
        if self.path.is_file():
            raw = self.path.read_text(encoding="utf-8")
            self._data = LedgerData.model_validate_json(raw)
        else:
            self._data = LedgerData(project_id=self.project_id)
        return self._data

    def _save_unlocked(self, data: LedgerData) -> None:
        data.updated_at = _utc_now_iso()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_dir / f".{self.path.name}.{os.getpid()}.tmp"
        tmp_path.write_text(data.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_path, self.path)
        self._data = data

    def is_completed(self, student_slug: str, service: ServiceName) -> bool:
        with self._lock:
            data = self._load_unlocked()
            entry = data.students.get(student_slug, {}).get(service.value)
            return entry is not None and entry.state == "COMPLETED"

    def get_checkpoint(
        self,
        student_slug: str,
        service: ServiceName,
    ) -> ServiceCheckpoint | None:
        with self._lock:
            data = self._load_unlocked()
            return data.students.get(student_slug, {}).get(service.value)

    def record_service_outcome(
        self,
        student: StudentSpec,
        service: ServiceName,
        steps: list[StepResult],
        error: str = "",
    ) -> ServiceCheckpoint:
        failed = bool(error) or any(step.status == "FAILED" for step in steps)
        checkpoint = ServiceCheckpoint(
            service=service,
            student_slug=student.slug,
            student_email=student.email,
            state="FAILED" if failed else "COMPLETED",
            updated_at=_utc_now_iso(),
            steps=list(steps),
            error=error,
        )
        with self._lock:
            data = self._load_unlocked()
            student_map = data.students.setdefault(student.slug, {})
            student_map[service.value] = checkpoint
            self._save_unlocked(data)
        return checkpoint

    def record_iam_coalesce(
        self,
        *,
        total_principals: int,
        conditional_bindings: int,
        attempts: int = 1,
    ) -> None:
        with self._lock:
            data = self._load_unlocked()
            data.iam_coalesce = IamCoalesceCheckpoint(
                updated_at=_utc_now_iso(),
                total_principals=total_principals,
                conditional_bindings=conditional_bindings,
                attempts=attempts,
            )
            self._save_unlocked(data)

    def reset(
        self,
        student_slug: str | None = None,
        services: Iterable[ServiceName] | None = None,
    ) -> None:
        svc_keys = {s.value for s in services} if services is not None else None
        with self._lock:
            data = self._load_unlocked()
            if student_slug is None and svc_keys is None:
                data.students.clear()
                data.iam_coalesce = None
            else:
                targets = (
                    [student_slug]
                    if student_slug is not None
                    else list(data.students.keys())
                )
                for slug in targets:
                    if slug not in data.students:
                        continue
                    if svc_keys is None:
                        del data.students[slug]
                    else:
                        for key in svc_keys:
                            data.students[slug].pop(key, None)
                        if not data.students[slug]:
                            del data.students[slug]
            self._save_unlocked(data)

    def summary(
        self,
        *,
        student_filter: set[str] | None = None,
        service_filter: set[ServiceName] | None = None,
    ) -> dict[str, Any]:
        """Compute aggregate counts per service and student for status reporting."""
        with self._lock:
            exists = self.path.is_file()
            data = self._load_unlocked()

        allowed_svcs = (
            {s.value for s in service_filter} if service_filter is not None else None
        )
        by_service: dict[str, dict[str, int]] = {}
        completed_total = 0
        failed_total = 0
        student_rows: list[dict[str, Any]] = []

        for slug in sorted(data.students.keys()):
            if student_filter is not None and slug not in student_filter:
                continue
            svc_map = data.students[slug]
            completed_svcs: list[str] = []
            failed_svcs: list[str] = []
            email = ""
            for svc_key, cp in sorted(svc_map.items()):
                if allowed_svcs is not None and svc_key not in allowed_svcs:
                    continue
                email = email or cp.student_email
                counts = by_service.setdefault(svc_key, {"completed": 0, "failed": 0})
                if cp.state == "COMPLETED":
                    counts["completed"] += 1
                    completed_total += 1
                    completed_svcs.append(svc_key)
                else:
                    counts["failed"] += 1
                    failed_total += 1
                    failed_svcs.append(svc_key)
            if completed_svcs or failed_svcs:
                student_rows.append(
                    {
                        "slug": slug,
                        "email": email,
                        "completed": completed_svcs,
                        "failed": failed_svcs,
                    }
                )

        return {
            "exists": exists,
            "path": str(self.path),
            "project_id": data.project_id,
            "updated_at": data.updated_at if exists else None,
            "students_tracked": len(student_rows),
            "completed_slices": completed_total,
            "failed_slices": failed_total,
            "by_service": by_service,
            "students": student_rows,
            "iam_coalesce": (
                data.iam_coalesce.model_dump() if data.iam_coalesce is not None else None
            ),
        }
