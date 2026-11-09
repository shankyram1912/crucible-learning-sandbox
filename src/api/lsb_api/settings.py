"""Settings for the Self Service APIs (specs/tdd-apis/tdd-apis-common-config.md).

The only place that reads environment variables. Loaded once at startup and validated;
the API refuses to start if a required setting is missing or invalid.
"""

from functools import lru_cache

from pydantic import Field, field_validator, model_validator

from lsb_api.models.common import Persona
from pydantic_settings import BaseSettings, SettingsConfigDict

# Public OAuth client IDs that `gcloud` uses to sign in. The `aud` of an ADC ID token is one of them:
# older ADC logins used the gcloud CLI client, current `gcloud auth application-default login` uses
# the dedicated ADC client.
GCLOUD_CLI_CLIENT_ID = "32555940559.apps.googleusercontent.com"
GCLOUD_ADC_CLIENT_ID = "764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com"
DEFAULT_ALLOWED_AUDIENCES = f"{GCLOUD_ADC_CLIENT_ID},{GCLOUD_CLI_CLIENT_ID}"


# Access control list (specs/tdd-apis/tdd-apis-common-acl.md): every operation mapped to 1..N roles.
# Override with LSB_ACL as JSON, for example LSB_ACL='{"health.api": ["IT_ADMIN"], ...}' (the whole map).
DEFAULT_ACL: dict[str, list[str]] = {
    "health.api": ["IT_ADMIN", "BU_ADMIN"],
    "health.db": ["IT_ADMIN"],
    "health.service": ["USER"],
    "platform_users.role": ["USER"],                         # own role
    "platform_users.role.other": ["IT_ADMIN", "BU_ADMIN"],   # someone else's role (?email=)
}


def _split(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return [v.strip() for v in value if v.strip()]
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    # Platform keys (same names as initialize.env)
    CT_PROJECT_ID: str
    REGION: str = "asia-southeast1"
    DOMAIN: str
    ORG_ID: str | None = None
    FIRESTORE_CONFIG_DATABASE: str
    FIRESTORE_DATABASE: str
    IT_ADMINS_GROUP: str
    BU_ADMINS_GROUP: str

    # API keys
    LSB_PLATFORM_ADMIN_GROUPS: str = ""  # PLATFORM_ADMIN persona, reserved for future use; empty means BU_ADMINS_GROUP
    LSB_ALLOWED_AUDIENCES: str = DEFAULT_ALLOWED_AUDIENCES
    LSB_API_VERSION: str = "unknown"
    LSB_API_PORT: int = 8080
    LSB_LOG_LEVEL: str = "INFO"
    LSB_HEALTH_DB_READ_TIMEOUT_SECONDS: float = Field(2.0, gt=0)
    LSB_HEALTH_DB_TOTAL_TIMEOUT_SECONDS: float = Field(5.0, gt=0)
    LSB_HEALTH_SERVICE_CACHE_SECONDS: float = Field(10.0, ge=0)
    LSB_ADMIN_ROSTER_REFRESH_SECONDS: float = Field(300.0, gt=0)
    LSB_ACL: dict[str, list[str]] = Field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_ACL.items()})

    @field_validator("DOMAIN")
    @classmethod
    def _lower_domain(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("LSB_ACL")
    @classmethod
    def _acl(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        valid = {p.value for p in Persona}
        for op, roles in v.items():
            if not roles:
                raise ValueError(f"LSB_ACL: operation {op} must list at least one role")
            bad = [r for r in roles if r not in valid]
            if bad:
                raise ValueError(f"LSB_ACL: operation {op} has unknown role(s) {bad}; valid: {sorted(valid)}")
        return v

    @field_validator("LSB_LOG_LEVEL")
    @classmethod
    def _log_level(cls, v: str) -> str:
        v = v.upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError("LSB_LOG_LEVEL must be DEBUG, INFO, WARNING or ERROR")
        return v

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if self.FIRESTORE_CONFIG_DATABASE == self.FIRESTORE_DATABASE:
            raise ValueError("FIRESTORE_CONFIG_DATABASE and FIRESTORE_DATABASE must differ")
        if not self.allowed_audiences:
            raise ValueError("LSB_ALLOWED_AUDIENCES must list at least one audience")
        return self

    @property
    def allowed_audiences(self) -> list[str]:
        return _split(self.LSB_ALLOWED_AUDIENCES)

    @property
    def acl(self) -> dict[str, frozenset[Persona]]:
        return {op: frozenset(Persona(r) for r in roles) for op, roles in self.LSB_ACL.items()}

    @property
    def it_admins_group(self) -> str:
        return self.IT_ADMINS_GROUP.strip().lower()

    @property
    def bu_admins_group(self) -> str:
        return self.BU_ADMINS_GROUP.strip().lower()

    @property
    def platform_admin_groups(self) -> list[str]:
        groups = _split(self.LSB_PLATFORM_ADMIN_GROUPS)
        return [g.lower() for g in (groups or [self.BU_ADMINS_GROUP])]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
