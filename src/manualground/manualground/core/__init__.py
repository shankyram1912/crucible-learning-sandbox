"""Decoupled ManualGround core primitives reusable by both CLI and Crucible."""

from manualground.core.http_client import (
    GcpError,
    GcpHttpError,
    GcpLroError,
    GcpLroTimeoutError,
    GcpRestClient,
)
from manualground.core.iam_coalescer import (
    MAX_SAFE_CONDITIONAL_BINDINGS,
    MAX_SAFE_PRINCIPALS,
    CoalesceStats,
    ProjectIamCoalescer,
    QuotaBudgetExceededError,
    count_policy_usage,
    merge_policy_bindings,
)
from manualground.core.ledger import (
    IamCoalesceCheckpoint,
    LedgerData,
    ProvisioningLedger,
    ServiceCheckpoint,
)
from manualground.core.models import (
    CheckOutcome,
    ConditionalBindingSpec,
    ServiceName,
    StepResult,
    StudentSpec,
)
from manualground.core.naming import (
    RosterValidationError,
    email_to_slug,
    load_roster_csv,
    normalize_slug,
    parse_roster_csv,
    sa_email_to_slug,
    validate_email,
    validate_roster,
)
from manualground.core.rate_limiter import (
    DEFAULT_LIMITER_RPMS,
    TokenBucketLimiter,
    build_default_limiters,
)

__all__ = [
    "CheckOutcome",
    "CoalesceStats",
    "ConditionalBindingSpec",
    "DEFAULT_LIMITER_RPMS",
    "GcpError",
    "GcpHttpError",
    "GcpLroError",
    "GcpLroTimeoutError",
    "GcpRestClient",
    "IamCoalesceCheckpoint",
    "LedgerData",
    "MAX_SAFE_CONDITIONAL_BINDINGS",
    "MAX_SAFE_PRINCIPALS",
    "ProjectIamCoalescer",
    "ProvisioningLedger",
    "QuotaBudgetExceededError",
    "RosterValidationError",
    "ServiceCheckpoint",
    "ServiceName",
    "StepResult",
    "StudentSpec",
    "TokenBucketLimiter",
    "build_default_limiters",
    "count_policy_usage",
    "email_to_slug",
    "load_roster_csv",
    "merge_policy_bindings",
    "normalize_slug",
    "parse_roster_csv",
    "sa_email_to_slug",
    "validate_email",
    "validate_roster",
]
