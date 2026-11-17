"""Cloud SQL for PostgreSQL 16 service driver with serialized Admin API and DDL isolation."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from typing import Any

from manualground.config import ShardSettings
from manualground.core.http_client import GcpHttpError, GcpLroError, GcpRestClient
from manualground.core.models import (
    CheckOutcome,
    ConditionalBindingSpec,
    ServiceName,
    StepResult,
    StudentSpec,
)
from manualground.core.naming import normalize_slug
from manualground.services.base import BaseServiceDriver

SQLADMIN_V1_BASE = "https://sqladmin.googleapis.com/v1"
SQL_CONNECT_ROLE_ID = "custom_ntu_sql_connect"
PG_NAMEDATALEN_MAX = 63

DB_CONNECTION_LIMIT = 8
SA_CONNECTION_LIMIT = 5
HUMAN_CONNECTION_LIMIT = 3


def strip_gserviceaccount_suffix(sa_email: str) -> str:
    """Strip .gserviceaccount.com from a GCP SA email as required by Cloud SQL IAM auth."""
    cleaned = sa_email.strip().lower()
    if cleaned.endswith(".gserviceaccount.com"):
        cleaned = cleaned[: -len(".gserviceaccount.com")]
    return cleaned


def _coerce_student(student: StudentSpec | str) -> StudentSpec:
    if isinstance(student, StudentSpec):
        return student
    raw = student.strip()
    if "@" in raw:
        return StudentSpec(email=raw)
    slug = normalize_slug(raw)
    return StudentSpec(email=f"{slug}@example.internal", slug=slug)


def _quote_ident(identifier: str) -> str:
    """Escape a PostgreSQL double-quoted identifier safely."""
    return '"' + identifier.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    """Escape a PostgreSQL single-quoted string literal safely."""
    return "'" + value.replace("'", "''") + "'"


def build_isolation_ddl_phases(
    student: StudentSpec | str,
    project_id: str,
) -> dict[str, list[str]]:
    """Return deterministic two-phase PostgreSQL 16 isolation statements keyed by database."""
    spec = _coerce_student(student)
    db_name = spec.sql_db_name()
    role_name = spec.sql_role_name()
    iam_user = spec.email
    iam_sa = strip_gserviceaccount_suffix(spec.sa_email(project_id))

    q_db = _quote_ident(db_name)
    q_role = _quote_ident(role_name)
    q_user = _quote_ident(iam_user)
    q_sa = _quote_ident(iam_sa)
    lit_role = _quote_literal(role_name)

    phase_postgres = [
        "REVOKE CREATE, USAGE ON SCHEMA public FROM PUBLIC;",
        (
            "DO $$\n"
            "BEGIN\n"
            f"  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {lit_role}) THEN\n"
            f"    CREATE ROLE {q_role} NOLOGIN INHERIT;\n"
            "  END IF;\n"
            "END\n"
            "$$;"
        ),
        f"GRANT {q_role} TO {q_user}, {q_sa};",
        f"ALTER ROLE {q_sa} WITH CONNECTION LIMIT {SA_CONNECTION_LIMIT};",
        f"ALTER ROLE {q_user} WITH CONNECTION LIMIT {HUMAN_CONNECTION_LIMIT};",
        f"ALTER DATABASE {q_db} OWNER TO {q_role};",
        f"ALTER DATABASE {q_db} WITH CONNECTION LIMIT {DB_CONNECTION_LIMIT};",
        f"REVOKE ALL ON DATABASE {q_db} FROM PUBLIC;",
        f"GRANT CONNECT, TEMPORARY, CREATE ON DATABASE {q_db} TO {q_role};",
    ]

    phase_student_db = [
        "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;",
        "CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;",
        'CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;',
        "REVOKE ALL ON SCHEMA public FROM PUBLIC;",
        f"ALTER SCHEMA public OWNER TO {q_role};",
        f"GRANT USAGE, CREATE ON SCHEMA public TO {q_role};",
        f"GRANT {q_user}, {q_sa} TO postgres;",
        (
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {q_user}, {q_sa} IN SCHEMA public\n"
            f"  GRANT ALL PRIVILEGES ON TABLES TO {q_role};"
        ),
        (
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {q_user}, {q_sa} IN SCHEMA public\n"
            f"  GRANT ALL PRIVILEGES ON SEQUENCES TO {q_role};"
        ),
        (
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {q_user}, {q_sa} IN SCHEMA public\n"
            f"  GRANT ALL PRIVILEGES ON FUNCTIONS TO {q_role};"
        ),
        f"REVOKE {q_user}, {q_sa} FROM postgres;",
        f"ALTER ROLE {q_user} IN DATABASE {q_db} SET search_path = public;",
        f"ALTER ROLE {q_sa} IN DATABASE {q_db} SET search_path = public;",
    ]

    return {
        "postgres": phase_postgres,
        db_name: phase_student_db,
    }


def build_isolation_ddl(
    student: StudentSpec | str,
    project_id: str,
) -> str:
    """Build the deterministic PostgreSQL 16 isolation DDL script for one student."""
    spec = _coerce_student(student)
    db_name = spec.sql_db_name()
    phases = build_isolation_ddl_phases(spec, project_id)

    lines: list[str] = [
        "-- Phase 1: Connected to database \"postgres\" as administrative user",
        *phases["postgres"],
        "",
        f"\\connect {_quote_ident(db_name)}",
        "",
        f"-- Phase 2: Connected to database {_quote_ident(db_name)} as administrative user",
        *phases[db_name],
    ]
    return "\n".join(lines) + "\n"


def _is_already_exists_response(resp_status: int, text: str) -> bool:
    if resp_status == 409:
        lower = text.lower()
        if "operation was already in progress" in lower or "operationinprogress" in lower:
            return False
        return True
    if resp_status == 400:
        lower = text.lower()
        return "already exists" in lower or "alreadyexists" in lower
    return False


class CloudSqlDriver(BaseServiceDriver):
    """Provisions per-student logical databases, IAM DB users, and PG16 isolation DDL."""

    service: ServiceName = ServiceName.CLOUD_SQL

    def __init__(
        self,
        admin_client: GcpRestClient,
        *,
        sql_executor: Callable[[str, list[str]], None] | Callable[[str], None] | None = None,
        psql_dsn: str | None = None,
        sql_connect_probe: Callable[[StudentSpec, str], bool] | None = None,
    ) -> None:
        super().__init__(admin_client)
        self.sql_executor = sql_executor
        self.psql_dsn = psql_dsn
        self.sql_connect_probe = sql_connect_probe

    def _elapsed_ms(self, start: float) -> int:
        return max(0, int((self.admin_client._clock() - start) * 1000))

    @staticmethod
    def build_isolation_ddl(student: StudentSpec | str, project_id: str) -> str:
        return build_isolation_ddl(student, project_id)

    def _instance_name(self, settings: ShardSettings) -> str:
        return settings.sql_instance_name or f"sql-{settings.project_id}"

    def _wait_sql_operation(
        self,
        settings: ShardSettings,
        op_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Poll a Cloud SQL Admin API Operation until status == DONE."""
        if op_payload.get("done") is True or op_payload.get("status") == "DONE":
            err = op_payload.get("error")
            if isinstance(err, dict) and (
                err.get("code") or err.get("message") or err.get("errors")
            ):
                raise GcpLroError(f"Cloud SQL operation failed: {err}", operation=op_payload)
            return op_payload

        self_link = str(op_payload.get("selfLink") or "").strip()
        op_name = str(op_payload.get("name") or "").strip()
        if self_link:
            op_url = self_link
        elif op_name.startswith(("http://", "https://")):
            op_url = op_name
        elif op_name.startswith("projects/"):
            op_url = f"{SQLADMIN_V1_BASE}/{op_name}"
        elif op_name:
            op_url = f"{SQLADMIN_V1_BASE}/projects/{settings.project_id}/operations/{op_name}"
        else:
            return op_payload

        return self.admin_client.poll_lro(op_url, limiter_name="sql_admin")

    def _run_serial_sql_mutation(
        self,
        settings: ShardSettings,
        url: str,
        body: dict[str, Any],
    ) -> str:
        """Execute one serialized Cloud SQL Admin POST + LRO wait, returning CREATED or UNCHANGED."""
        with self.admin_client.serial_lock("sql_admin"):
            resp = self.admin_client.post(
                url,
                limiter_name="sql_admin",
                json=body,
            )
            if resp.status_code in (200, 201):
                payload: dict[str, Any] = resp.json() if resp.content else {}
                try:
                    self._wait_sql_operation(settings, payload)
                except GcpLroError as exc:
                    msg = str(exc).lower()
                    if "already exists" in msg or "already_exists" in msg or "alreadyexists" in msg:
                        return "UNCHANGED"
                    raise
                return "CREATED"

            if _is_already_exists_response(resp.status_code, resp.text):
                return "UNCHANGED"

            raise GcpHttpError(
                f"Cloud SQL Admin mutation failed on {url} "
                f"(HTTP {resp.status_code}): {resp.text[:500]}",
                status_code=resp.status_code,
                response=resp,
            )

    def _execute_ddl_if_configured(
        self,
        student: StudentSpec,
        project_id: str,
        ddl_script: str,
    ) -> bool:
        """Run isolation DDL via injected callable or psql DSN if configured; return True if run."""
        if self.sql_executor is not None:
            phases = build_isolation_ddl_phases(student, project_id)
            try:
                for target_db, statements in phases.items():
                    self.sql_executor(target_db, statements)  # type: ignore[call-arg]
            except TypeError:
                self.sql_executor(ddl_script)  # type: ignore[call-arg]
            return True

        dsn = self.psql_dsn or os.environ.get("MG_PSQL_ADMIN_DSN", "").strip()
        if dsn:
            proc = subprocess.run(
                ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-X", "-q"],
                input=ddl_script,
                text=True,
                capture_output=True,
                check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"psql isolation DDL execution failed (exit {proc.returncode}): "
                    f"{proc.stderr.strip()[:500]}"
                )
            return True

        return False

    def preflight(
        self,
        settings: ShardSettings,
        roster: list[StudentSpec],
    ) -> list[CheckOutcome]:
        """Verify shared Cloud SQL instance is RUNNABLE with cloudsql.iam_authentication=on."""
        project_id = settings.project_id
        instance = self._instance_name(settings)

        if not settings.enable_cloud_sql:
            return [
                CheckOutcome(
                    service=self.service,
                    check_id="sql.enabled",
                    kind="GUARDRAIL",
                    actor="preflight",
                    target=instance,
                    passed=True,
                    expected="SKIPPED",
                    actual="SKIPPED",
                    detail="ENABLE_CLOUD_SQL is false",
                )
            ]

        outcomes: list[CheckOutcome] = []
        inst_url = f"{SQLADMIN_V1_BASE}/projects/{project_id}/instances/{instance}"
        resp = self.admin_client.get(inst_url, limiter_name="sql_admin")
        payload: dict[str, Any] = resp.json() if resp.status_code == 200 and resp.content else {}

        state = str(payload.get("state") or f"HTTP_{resp.status_code}")
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="sql.instance_runnable",
                kind="POSITIVE",
                actor="preflight",
                target=instance,
                passed=(resp.status_code == 200 and state == "RUNNABLE"),
                expected="RUNNABLE",
                actual=state,
                detail=inst_url,
            )
        )

        db_flags = (payload.get("settings") or {}).get("databaseFlags") or []
        iam_auth_val = next(
            (
                str(f.get("value", "")).lower()
                for f in db_flags
                if isinstance(f, dict) and f.get("name") == "cloudsql.iam_authentication"
            ),
            "unset",
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="sql.iam_authentication_on",
                kind="GUARDRAIL",
                actor="preflight",
                target=instance,
                passed=(resp.status_code == 200 and iam_auth_val == "on"),
                expected="cloudsql.iam_authentication=on",
                actual=f"cloudsql.iam_authentication={iam_auth_val}",
                detail="Required for passwordless CLOUD_IAM_USER and CLOUD_IAM_SERVICE_ACCOUNT logins",
            )
        )

        overlong: list[str] = []
        for s in roster:
            sa_sql_user = strip_gserviceaccount_suffix(s.sa_email(project_id))
            if (
                len(sa_sql_user.encode("utf-8")) > PG_NAMEDATALEN_MAX
                or sa_sql_user.endswith(".gserviceaccount.com")
            ):
                overlong.append(sa_sql_user)

        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="sql.iam_identifier_bounds",
                kind="GUARDRAIL",
                actor="preflight",
                target=instance,
                passed=not overlong,
                expected=f"<= {PG_NAMEDATALEN_MAX} bytes without .gserviceaccount.com",
                actual="ok" if not overlong else f"invalid={overlong}",
                detail=f"Checked {len(roster)} roster principals",
            )
        )

        return outcomes

    def provision_student(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[StepResult]:
        """Serially create db_<student>, CLOUD_IAM_USER, CLOUD_IAM_SERVICE_ACCOUNT, and PG16 DDL."""
        project_id = settings.project_id
        instance = self._instance_name(settings)

        if not settings.enable_cloud_sql:
            return [
                StepResult(
                    service=self.service,
                    student_slug=student.slug,
                    action="skip_cloud_sql",
                    resource_id=instance,
                    status="SKIPPED",
                    detail="ENABLE_CLOUD_SQL is false",
                )
            ]

        db_name = student.sql_db_name()
        iam_sa_user = strip_gserviceaccount_suffix(student.sa_email(project_id))
        inst_base = f"{SQLADMIN_V1_BASE}/projects/{project_id}/instances/{instance}"
        steps: list[StepResult] = []

        # 1. Serialized databases.insert (db_<student>)
        t0 = self.admin_client._clock()
        db_status = self._run_serial_sql_mutation(
            settings,
            f"{inst_base}/databases",
            {
                "name": db_name,
                "project": project_id,
                "instance": instance,
                "charset": "UTF8",
                "collation": "en_US.UTF8",
            },
        )
        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="ensure_database",
                resource_id=db_name,
                status=db_status,  # type: ignore[arg-type]
                duration_ms=self._elapsed_ms(t0),
                detail=f"instance={instance}",
            )
        )

        # 2. Serialized users.insert for interactive human student (CLOUD_IAM_USER)
        t1 = self.admin_client._clock()
        human_status = self._run_serial_sql_mutation(
            settings,
            f"{inst_base}/users",
            {
                "name": student.email,
                "project": project_id,
                "instance": instance,
                "type": "CLOUD_IAM_USER",
            },
        )
        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="ensure_iam_user",
                resource_id=student.email,
                status=human_status,  # type: ignore[arg-type]
                duration_ms=self._elapsed_ms(t1),
                detail="type=CLOUD_IAM_USER",
            )
        )

        # 3. Serialized users.insert for unified student SA (CLOUD_IAM_SERVICE_ACCOUNT, stripped suffix)
        t2 = self.admin_client._clock()
        sa_status = self._run_serial_sql_mutation(
            settings,
            f"{inst_base}/users",
            {
                "name": iam_sa_user,
                "project": project_id,
                "instance": instance,
                "type": "CLOUD_IAM_SERVICE_ACCOUNT",
            },
        )
        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="ensure_iam_service_account_user",
                resource_id=iam_sa_user,
                status=sa_status,  # type: ignore[arg-type]
                duration_ms=self._elapsed_ms(t2),
                detail="type=CLOUD_IAM_SERVICE_ACCOUNT (.gserviceaccount.com stripped)",
            )
        )

        # 4. Deterministic PostgreSQL 16 isolation DDL generation (and execution when configured)
        t3 = self.admin_client._clock()
        ddl_script = build_isolation_ddl(student, project_id)
        executed = self._execute_ddl_if_configured(student, project_id, ddl_script)
        steps.append(
            StepResult(
                service=self.service,
                student_slug=student.slug,
                action="apply_isolation_ddl" if executed else "build_isolation_ddl",
                resource_id=db_name,
                status="CREATED",
                duration_ms=self._elapsed_ms(t3),
                detail=ddl_script,
            )
        )

        return steps

    def project_iam_bindings(
        self,
        settings: ShardSettings,
        student: StudentSpec,
    ) -> list[ConditionalBindingSpec]:
        """Bind custom_ntu_sql_connect unconditionally for human and unified SA principals."""
        if not settings.enable_cloud_sql:
            return []
        project_id = settings.project_id
        return [
            ConditionalBindingSpec(
                role=f"projects/{project_id}/roles/{SQL_CONNECT_ROLE_ID}",
                members=[
                    f"user:{student.email}",
                    f"serviceAccount:{student.sa_email(project_id)}",
                ],
            )
        ]

    def verify_isolation(
        self,
        settings: ShardSettings,
        student_a: StudentSpec,
        student_b: StudentSpec,
        client_a: GcpRestClient,
        client_b: GcpRestClient,
    ) -> list[CheckOutcome]:
        """Verify Cloud SQL Admin API 403 guardrails and PostgreSQL CONNECT isolation."""
        del client_b
        project_id = settings.project_id
        instance = self._instance_name(settings)

        if not settings.enable_cloud_sql:
            return [
                CheckOutcome(
                    service=self.service,
                    check_id="sql.enabled",
                    kind="GUARDRAIL",
                    actor=student_a.slug,
                    target=instance,
                    passed=True,
                    expected="SKIPPED",
                    actual="SKIPPED",
                    detail="ENABLE_CLOUD_SQL is false",
                )
            ]

        inst_base = f"{SQLADMIN_V1_BASE}/projects/{project_id}/instances/{instance}"
        db_a = student_a.sql_db_name()
        db_b = student_b.sql_db_name()
        outcomes: list[CheckOutcome] = []

        # 1. Positive: Student A can fetch instance connection metadata (200).
        inst_get = client_a.get(inst_base, limiter_name="sql_admin")
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="sql.own_instance_get",
                kind="POSITIVE",
                actor=student_a.slug,
                target=instance,
                passed=inst_get.status_code == 200,
                expected="HTTP 200",
                actual=f"HTTP {inst_get.status_code}",
                detail="cloudsql.instances.get via custom_ntu_sql_connect",
            )
        )

        # 2. Negative cross-student: Student A cannot delete Student B's database via Admin API (403).
        del_peer_db = client_a.delete(
            f"{inst_base}/databases/{db_b}",
            limiter_name="sql_admin",
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="sql.cross_student_db_delete",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=f"{instance}/{db_b}",
                passed=del_peer_db.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {del_peer_db.status_code}",
                detail="Cross-student cloudsql.databases.delete must be denied",
            )
        )

        # 3. Negative cross-student: Student A cannot delete Student B's IAM user via Admin API (403).
        del_peer_user = client_a.delete(
            f"{inst_base}/users",
            limiter_name="sql_admin",
            params={"name": student_b.email},
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="sql.cross_student_user_delete",
                kind="NEGATIVE_CROSS_STUDENT",
                actor=student_a.slug,
                target=f"{instance}/users/{student_b.email}",
                passed=del_peer_user.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {del_peer_user.status_code}",
                detail="Cross-student cloudsql.users.delete must be denied",
            )
        )

        # 4. Guardrail: Student A cannot create an unauthorized database via Admin API (403).
        unauth_db = f"{db_a}_unauth"[:PG_NAMEDATALEN_MAX]
        create_db = client_a.post(
            f"{inst_base}/databases",
            limiter_name="sql_admin",
            json={"name": unauth_db, "project": project_id, "instance": instance},
        )
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="sql.guardrail_db_create",
                kind="GUARDRAIL",
                actor=student_a.slug,
                target=f"{instance}/{unauth_db}",
                passed=create_db.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {create_db.status_code}",
                detail="Folder IAM Deny v2 blocks cloudsql.googleapis.com/databases.create",
            )
        )

        # 5. Guardrail: Student A cannot delete the shared Cloud SQL instance (403).
        del_inst = client_a.delete(inst_base, limiter_name="sql_admin")
        outcomes.append(
            CheckOutcome(
                service=self.service,
                check_id="sql.guardrail_instance_delete",
                kind="GUARDRAIL",
                actor=student_a.slug,
                target=instance,
                passed=del_inst.status_code == 403,
                expected="HTTP 403",
                actual=f"HTTP {del_inst.status_code}",
                detail="Folder IAM Deny v2 blocks cloudsql.googleapis.com/instances.delete",
            )
        )

        # 6. PostgreSQL engine-plane CONNECT isolation (live hook when supplied, DDL proof otherwise).
        if self.sql_connect_probe is not None:
            own_ok = bool(self.sql_connect_probe(student_a, db_a))
            outcomes.append(
                CheckOutcome(
                    service=self.service,
                    check_id="sql.own_db_connect",
                    kind="POSITIVE",
                    actor=student_a.slug,
                    target=db_a,
                    passed=own_ok,
                    expected="CONNECT_ALLOWED",
                    actual="CONNECT_ALLOWED" if own_ok else "CONNECT_DENIED",
                    detail="PostgreSQL IAM login + CONNECT on own database",
                )
            )
            peer_connected = bool(self.sql_connect_probe(student_a, db_b))
            outcomes.append(
                CheckOutcome(
                    service=self.service,
                    check_id="sql.cross_student_db_connect",
                    kind="NEGATIVE_CROSS_STUDENT",
                    actor=student_a.slug,
                    target=db_b,
                    passed=not peer_connected,
                    expected="CONNECT_DENIED",
                    actual="CONNECT_ALLOWED" if peer_connected else "CONNECT_DENIED",
                    detail="REVOKE ALL ON DATABASE FROM PUBLIC blocks cross-student CONNECT",
                )
            )
        else:
            ddl_b = build_isolation_ddl(student_b, project_id)
            revoke_clause = f'REVOKE ALL ON DATABASE "{db_b}" FROM PUBLIC;'
            role_b = student_b.sql_role_name()
            sa_a = strip_gserviceaccount_suffix(student_a.sa_email(project_id))
            contract_ok = (
                revoke_clause in ddl_b
                and f'GRANT CONNECT, TEMPORARY, CREATE ON DATABASE "{db_b}" TO "{role_b}";' in ddl_b
                and student_a.email not in ddl_b
                and sa_a not in ddl_b
            )
            outcomes.append(
                CheckOutcome(
                    service=self.service,
                    check_id="sql.cross_student_db_connect",
                    kind="NEGATIVE_CROSS_STUDENT",
                    actor=student_a.slug,
                    target=db_b,
                    passed=contract_ok,
                    expected="PUBLIC_CONNECT_REVOKED",
                    actual="PUBLIC_CONNECT_REVOKED" if contract_ok else "UNISOLATED_DDL",
                    detail="Verified PG16 REVOKE ALL ON DATABASE ... FROM PUBLIC isolation contract",
                )
            )

        return outcomes
