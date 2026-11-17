"""Configuration settings for a ManualGround shard project."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = PACKAGE_ROOT / "initialize.env"
DEFAULT_STATE_DIR = PACKAGE_ROOT / "state"

_VAR_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _parse_shell_env_file(env_file: Path) -> dict[str, str]:
    """Read KEY=VALUE pairs from initialize.env, expanding simple ${VAR} references."""
    if not env_file.is_file():
        return {}
    raw: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            continue
        key, val = stripped.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        elif " #" in val:
            val = val.split(" #", 1)[0].strip()
        raw[key] = val

    org_id_val = os.environ.get("ORG_ID", raw.get("ORG_ID", "")).strip()
    if org_id_val and "ORG_SUFFIX" not in raw and "ORG_SUFFIX" not in os.environ:
        raw["ORG_SUFFIX"] = hashlib.sha256(org_id_val.encode("utf-8")).hexdigest()[:3]

    resolved: dict[str, str] = {}
    for key, val in raw.items():
        def _replace(match: re.Match[str]) -> str:
            ref = match.group(1) or match.group(2) or ""
            return os.environ.get(ref, resolved.get(ref, raw.get(ref, "")))

        resolved[key] = _VAR_REF_RE.sub(_replace, val)
    return resolved


class ShardSettings(BaseSettings):
    """Runtime settings for one ManualGround shard project."""

    model_config = SettingsConfigDict(
        extra="ignore",
        populate_by_name=True,
    )

    quota_project: str = Field(
        default="",
        validation_alias=AliasChoices("quota_project", "QUOTA_PROJECT"),
    )
    org_id: str = Field(
        default="",
        validation_alias=AliasChoices("org_id", "ORG_ID"),
    )
    billing_account_id: str = Field(
        default="",
        validation_alias=AliasChoices("billing_account_id", "BILLING_ACCOUNT_ID"),
    )
    domain: str = Field(
        default="",
        validation_alias=AliasChoices("domain", "DOMAIN"),
    )
    parent_folder_id: str = Field(
        default="",
        validation_alias=AliasChoices("parent_folder_id", "MG_PARENT_FOLDER"),
    )
    playground_folder_id: str = Field(
        default="",
        validation_alias=AliasChoices("playground_folder_id", "MG_FOLDER_ID"),
    )
    project_id: str = Field(
        default="",
        validation_alias=AliasChoices("project_id", "MG_PROJECT_ID"),
    )
    project_number: str = Field(
        default="",
        validation_alias=AliasChoices("project_number", "MG_PROJECT_NUMBER"),
    )
    region: str = Field(
        default="asia-southeast1",
        validation_alias=AliasChoices("region", "REGION"),
    )
    student_group_email: str = Field(
        default="",
        validation_alias=AliasChoices("student_group_email", "STUDENT_GROUP_EMAIL"),
    )
    it_admins_group: str = Field(
        default="",
        validation_alias=AliasChoices("it_admins_group", "IT_ADMINS_GROUP"),
    )
    preset: Literal["dev", "prod"] = Field(
        default="dev",
        validation_alias=AliasChoices("preset", "MG_PRESET"),
    )
    enable_cloud_sql: bool = Field(
        default=True,
        validation_alias=AliasChoices("enable_cloud_sql", "ENABLE_CLOUD_SQL"),
    )
    sql_instance_name: str = Field(
        default="",
        validation_alias=AliasChoices("sql_instance_name", "MG_SQL_INSTANCE"),
    )
    max_run_services_per_student: int = Field(
        default=3,
        validation_alias=AliasChoices(
            "max_run_services_per_student",
            "MAX_SERVICES_PER_STUDENT",
        ),
    )
    state_dir: Path = Field(
        default=DEFAULT_STATE_DIR,
        validation_alias=AliasChoices("state_dir", "MG_STATE_DIR"),
    )

    @model_validator(mode="after")
    def _apply_derived_defaults(self) -> ShardSettings:
        if not self.sql_instance_name and self.project_id:
            self.sql_instance_name = f"sql-{self.project_id}"
        return self

    @property
    def effective_quota_project(self) -> str:
        """Return quota_project when configured, falling back to project_id."""
        return self.quota_project or self.project_id

    @classmethod
    def from_env_file(
        cls,
        env_file: Path | None = None,
        **overrides: Any,
    ) -> ShardSettings:
        """Load settings from initialize.env + process environment + explicit overrides."""
        target = env_file if env_file is not None else DEFAULT_ENV_FILE
        file_values = _parse_shell_env_file(target)
        merged: dict[str, Any] = {}
        for k, v in file_values.items():
            if k not in os.environ and v != "":
                merged[k] = v
        for k, v in overrides.items():
            if v is not None:
                merged[k] = v
        return cls(**merged)
