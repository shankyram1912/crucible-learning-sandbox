"""Coalesced single-shot Project IAM batching with version=3, budget checks, and ETag retry."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from manualground.core.http_client import GcpHttpError, GcpRestClient
from manualground.core.models import ConditionalBindingSpec

CRM_PROJECTS_BASE = "https://cloudresourcemanager.googleapis.com/v3/projects"
MAX_SAFE_PRINCIPALS = 1400
MAX_SAFE_CONDITIONAL_BINDINGS = 95


class QuotaBudgetExceededError(RuntimeError):
    """Raised when a merged project IAM policy exceeds safe principal or condition budgets."""

    def __init__(
        self,
        message: str,
        *,
        total_principals: int = 0,
        conditional_bindings: int = 0,
    ) -> None:
        super().__init__(message)
        self.total_principals = total_principals
        self.conditional_bindings = conditional_bindings


@dataclass(frozen=True)
class CoalesceStats:
    """Telemetry from the most recent coalesced project IAM policy commit."""

    total_principals: int
    conditional_bindings: int
    attempts: int
    changed: bool


def count_policy_usage(policy: dict[str, Any]) -> tuple[int, int]:
    """Return (total_principals, conditional_bindings) across all policy bindings."""
    bindings = policy.get("bindings") or []
    total_principals = sum(len(b.get("members") or []) for b in bindings)
    conditional_bindings = sum(1 for b in bindings if b.get("condition"))
    return total_principals, conditional_bindings


def merge_policy_bindings(
    policy: dict[str, Any],
    specs: Sequence[ConditionalBindingSpec],
) -> tuple[dict[str, Any], bool]:
    """Idempotently merge ConditionalBindingSpec entries into a version=3 IAM policy copy."""
    merged = copy.deepcopy(policy)
    original_bindings = copy.deepcopy(merged.get("bindings") or [])
    bindings: list[dict[str, Any]] = [
        {
            **b,
            "members": list(b.get("members") or []),
        }
        for b in original_bindings
    ]

    for spec in specs:
        clean_members = [m.strip() for m in spec.members if m and m.strip()]
        if not clean_members:
            continue

        is_conditional = bool(spec.condition_expression.strip())
        if not is_conditional:
            existing = next(
                (
                    b
                    for b in bindings
                    if b.get("role") == spec.role and not b.get("condition")
                ),
                None,
            )
            if existing is not None:
                existing["members"] = sorted(
                    set(existing.get("members") or []) | set(clean_members)
                )
            else:
                bindings.append(
                    {
                        "role": spec.role,
                        "members": sorted(set(clean_members)),
                    }
                )
        else:
            cond_dict: dict[str, str] = {
                "title": spec.condition_title,
                "expression": spec.condition_expression,
            }
            if spec.condition_description:
                cond_dict["description"] = spec.condition_description

            existing_cond = next(
                (
                    b
                    for b in bindings
                    if b.get("role") == spec.role
                    and isinstance(b.get("condition"), dict)
                    and (
                        (
                            b["condition"].get("title") == spec.condition_title
                            and b["condition"].get("expression") == spec.condition_expression
                        )
                        or (
                            bool(spec.condition_title)
                            and b["condition"].get("title") == spec.condition_title
                        )
                    )
                ),
                None,
            )
            if existing_cond is not None:
                existing_cond["members"] = sorted(
                    set(existing_cond.get("members") or []) | set(clean_members)
                )
                existing_cond["condition"] = cond_dict
            else:
                bindings.append(
                    {
                        "role": spec.role,
                        "members": sorted(set(clean_members)),
                        "condition": cond_dict,
                    }
                )

    changed = merged.get("version") != 3 or bindings != original_bindings
    merged["version"] = 3
    merged["bindings"] = bindings
    return merged, changed


class ProjectIamCoalescer:
    """Collects project IAM bindings across students/services and commits atomically."""

    def __init__(
        self,
        client: GcpRestClient,
        project_id: str = "",
        *,
        max_principals: int = MAX_SAFE_PRINCIPALS,
        max_conditional_bindings: int = MAX_SAFE_CONDITIONAL_BINDINGS,
        max_conflict_retries: int = 6,
    ) -> None:
        self.client = client
        self.project_id = project_id
        self.max_principals = max_principals
        self.max_conditional_bindings = max_conditional_bindings
        self.max_conflict_retries = max_conflict_retries
        self._specs: list[ConditionalBindingSpec] = []
        self.last_stats: CoalesceStats | None = None

    @property
    def pending_specs(self) -> list[ConditionalBindingSpec]:
        return list(self._specs)

    def add(self, spec: ConditionalBindingSpec) -> None:
        self._specs.append(spec)

    def add_many(self, specs: Iterable[ConditionalBindingSpec]) -> None:
        self._specs.extend(specs)

    extend = add_many

    def clear(self) -> None:
        self._specs.clear()

    def fetch_policy(self, project_id: str | None = None) -> dict[str, Any]:
        target_project = project_id or self.project_id
        if not target_project:
            raise ValueError("project_id is required to fetch project IAM policy.")
        url = f"{CRM_PROJECTS_BASE}/{target_project}:getIamPolicy"
        resp = self.client.post(
            url,
            limiter_name="crm_iam",
            json={"options": {"requestedPolicyVersion": 3}},
            raise_for_status=True,
        )
        return resp.json() if resp.content else {"version": 3, "bindings": []}

    def check_budget(self, policy: dict[str, Any]) -> tuple[int, int]:
        total_principals, conditional_bindings = count_policy_usage(policy)
        if total_principals > self.max_principals:
            raise QuotaBudgetExceededError(
                f"Project IAM policy principal count {total_principals} exceeds safe "
                f"budget of {self.max_principals} (GCP hard cap is 1,500).",
                total_principals=total_principals,
                conditional_bindings=conditional_bindings,
            )
        if conditional_bindings > self.max_conditional_bindings:
            raise QuotaBudgetExceededError(
                f"Project IAM policy conditional binding count {conditional_bindings} "
                f"exceeds safe budget of {self.max_conditional_bindings} (cap is 100).",
                total_principals=total_principals,
                conditional_bindings=conditional_bindings,
            )
        return total_principals, conditional_bindings

    def commit(
        self,
        project_id: str | None = None,
        specs: Sequence[ConditionalBindingSpec] | None = None,
        *,
        skip_if_unchanged: bool = False,
    ) -> dict[str, Any]:
        """Fetch version=3 policy, merge bindings, enforce budget, and setIamPolicy with 409 retry."""
        target_project = project_id or self.project_id
        if not target_project:
            raise ValueError("project_id is required to commit project IAM policy.")
        active_specs = list(specs) if specs is not None else list(self._specs)

        set_url = f"{CRM_PROJECTS_BASE}/{target_project}:setIamPolicy"

        for attempt in range(self.max_conflict_retries + 1):
            current_policy = self.fetch_policy(target_project)
            merged_policy, changed = merge_policy_bindings(current_policy, active_specs)
            total_principals, conditional_bindings = self.check_budget(merged_policy)

            if skip_if_unchanged and not changed:
                self.last_stats = CoalesceStats(
                    total_principals=total_principals,
                    conditional_bindings=conditional_bindings,
                    attempts=attempt + 1,
                    changed=False,
                )
                return merged_policy

            resp = self.client.post(
                set_url,
                limiter_name="crm_iam",
                json={"policy": merged_policy},
            )
            if resp.status_code == 200:
                committed: dict[str, Any] = (
                    resp.json() if resp.content else merged_policy
                )
                self.last_stats = CoalesceStats(
                    total_principals=total_principals,
                    conditional_bindings=conditional_bindings,
                    attempts=attempt + 1,
                    changed=changed,
                )
                return committed

            if resp.status_code == 409 and attempt < self.max_conflict_retries:
                backoff = self.client._compute_backoff(attempt, response=resp)
                self.client._sleep(backoff)
                continue

            raise GcpHttpError(
                f"Failed setting project IAM policy on {target_project} "
                f"(HTTP {resp.status_code}): {resp.text[:500]}",
                status_code=resp.status_code,
                response=resp,
            )

        raise GcpHttpError(
            f"Exhausted {self.max_conflict_retries} ETag conflict retries on {target_project}."
        )

    apply = commit
