"""Settings for the Self Service APIs (specs/tdd-apis/tdd-apis-common-config.md).

The only place that reads environment variables. Loaded once at startup and validated;
the API refuses to start if a required setting is missing or invalid.
"""

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ADC_GCLOUD_CLIENT_ID = "32555940559.apps.googleusercontent.com"


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
    LSB_PLATFORM_ADMIN_GROUPS: str = ""  # empty means BU_ADMINS_GROUP
    LSB_ALLOWED_AUDIENCES: str = ADC_GCLOUD_CLIENT_ID
    LSB_API_VERSION: str = "unknown"
    LSB_API_PORT: int = 8080
    LSB_LOG_LEVEL: str = "INFO"
    LSB_HEALTH_DB_READ_TIMEOUT_SECONDS: float = Field(2.0, gt=0)
    LSB_HEALTH_DB_TOTAL_TIMEOUT_SECONDS: float = Field(5.0, gt=0)
    LSB_HEALTH_SERVICE_CACHE_SECONDS: float = Field(10.0, ge=0)

    @field_validator("DOMAIN")
    @classmethod
    def _lower_domain(cls, v: str) -> str:
        return v.strip().lower()

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
    def platform_admin_groups(self) -> list[str]:
        groups = _split(self.LSB_PLATFORM_ADMIN_GROUPS)
        return [g.lower() for g in (groups or [self.BU_ADMINS_GROUP])]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
