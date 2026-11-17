"""mg verify: positive, adversarial cross-student (A vs B), and guardrail verification."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from manualground.cli import app as cli_app
from manualground.cli.display import emit_json, print_error, render_checks_table
from manualground.config import PACKAGE_ROOT, ShardSettings
from manualground.core.http_client import GcpError
from manualground.core.models import CheckOutcome, StudentSpec
from manualground.core.naming import RosterValidationError, load_roster_csv
from manualground.services import (
    DriverUnavailableError,
    get_driver,
    parse_service_selection,
)

DEFAULT_SAMPLE_ROSTER = PACKAGE_ROOT / "rosters" / "sample-2students.csv"


def _select_student_pair(
    roster_csv: Path | None,
    roster_opt: Path | None,
    student_a_arg: str | None,
    student_b_arg: str | None,
    student_filter: list[str] | None,
) -> tuple[StudentSpec, StudentSpec]:
    csv_path = roster_opt or roster_csv
    if csv_path is None and DEFAULT_SAMPLE_ROSTER.is_file():
        csv_path = DEFAULT_SAMPLE_ROSTER

    roster_students: list[StudentSpec] = (
        load_roster_csv(csv_path) if csv_path is not None else []
    )
    by_key: dict[str, StudentSpec] = {}
    for s in roster_students:
        by_key[s.slug] = s
        by_key[s.email] = s

    def _resolve_one(spec_or_key: str) -> StudentSpec:
        cleaned = spec_or_key.strip().lower()
        if cleaned in by_key:
            return by_key[cleaned]
        if "@" in cleaned:
            return StudentSpec(email=cleaned)
        raise RosterValidationError(
            f"Student {spec_or_key!r} not found in roster; pass full email or --roster."
        )

    if student_a_arg and student_b_arg:
        sa = _resolve_one(student_a_arg)
        sb = _resolve_one(student_b_arg)
    elif student_filter:
        filtered = cli_app.filter_students(roster_students, student_filter)
        if len(filtered) >= 2:
            sa, sb = filtered[0], filtered[1]
        elif len(filtered) == 1:
            sa = filtered[0]
            peer = next((s for s in roster_students if s.slug != sa.slug), None)
            if peer is None:
                raise RosterValidationError(
                    "Cross-student isolation verification requires at least 2 distinct students."
                )
            sb = peer
        else:
            raise RosterValidationError("No matching students found for --student.")
    else:
        if len(roster_students) < 2:
            raise RosterValidationError(
                "Cross-student verification requires at least 2 students in the roster "
                "(or pass --student-a and --student-b)."
            )
        sa, sb = roster_students[0], roster_students[1]

    if sa.slug == sb.slug:
        raise RosterValidationError(
            f"student_a and student_b must be distinct students (both resolved to {sa.slug!r})."
        )
    return sa, sb


def verify_cmd(
    roster_csv: Annotated[
        Path | None,
        typer.Argument(help="Optional roster CSV (defaults to rosters/sample-2students.csv)."),
    ] = None,
    roster: Annotated[
        Path | None,
        typer.Option("--roster", "-r", help="Path to student roster CSV."),
    ] = None,
    services: Annotated[
        list[str] | None,
        typer.Option(
            "--services",
            "-S",
            help="Comma-separated or repeated services (gemini,gcs,run,sql,firestore,search).",
        ),
    ] = None,
    student: Annotated[
        list[str] | None,
        typer.Option(
            "--student",
            "-s",
            help="Select primary student(s) by slug or email (paired automatically with a peer).",
        ),
    ] = None,
    student_a: Annotated[
        str | None,
        typer.Option("--student-a", help="Explicit Student A email or slug."),
    ] = None,
    student_b: Annotated[
        str | None,
        typer.Option("--student-b", help="Explicit Student B email or slug."),
    ] = None,
    token_a: Annotated[
        str | None,
        typer.Option("--token-a", help="Optional explicit bearer token for Student A."),
    ] = None,
    token_b: Annotated[
        str | None,
        typer.Option("--token-b", help="Optional explicit bearer token for Student B."),
    ] = None,
    project_id: Annotated[
        str | None,
        typer.Option("--project-id", help="Override MG_PROJECT_ID."),
    ] = None,
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", "-e", help="Path to initialize.env file."),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON output."),
    ] = False,
) -> None:
    """Run positive own-resource and negative cross-student isolation proofs across services."""
    use_json = cli_app.state.json or json_out
    settings: ShardSettings = cli_app.resolve_settings(
        env_file=env_file,
        project_id=project_id,
    )

    if not settings.project_id:
        msg = "MG_PROJECT_ID is not set. Configure initialize.env or pass --project-id."
        if use_json:
            emit_json({"ok": False, "error": msg, "checks": []})
        else:
            print_error(msg)
        raise typer.Exit(2)

    try:
        selected_services = parse_service_selection(services, settings=settings)
        stu_a, stu_b = _select_student_pair(
            roster_csv, roster, student_a, student_b, student
        )
    except (RosterValidationError, ValueError) as exc:
        if use_json:
            emit_json({"ok": False, "error": str(exc), "checks": []})
        else:
            print_error(str(exc))
        raise typer.Exit(2) from exc

    admin_client = cli_app.build_admin_client(settings)
    client_a = cli_app.build_student_client(
        settings, stu_a, admin_client, bearer_token=token_a
    )
    client_b = cli_app.build_student_client(
        settings, stu_b, admin_client, bearer_token=token_b
    )

    checks: list[CheckOutcome] = []
    try:
        for svc in selected_services:
            try:
                driver = get_driver(svc, admin_client)
                outcomes = driver.verify_isolation(
                    settings, stu_a, stu_b, client_a, client_b
                )
                checks.extend(outcomes)
            except DriverUnavailableError as exc:
                checks.append(
                    CheckOutcome(
                        service=svc,
                        check_id=f"verify.{svc.value}.driver_available",
                        kind="GUARDRAIL",
                        actor="verify",
                        target=svc.value,
                        passed=False,
                        expected="driver installed",
                        actual="missing",
                        detail=str(exc),
                    )
                )
            except GcpError as exc:
                checks.append(
                    CheckOutcome(
                        service=svc,
                        check_id=f"verify.{svc.value}.execution",
                        kind="GUARDRAIL",
                        actor=stu_a.slug,
                        target=settings.project_id,
                        passed=False,
                        expected="completed",
                        actual="GcpError",
                        detail=str(exc),
                    )
                )
    finally:
        client_a.close()
        client_b.close()
        admin_client.close()

    all_passed = bool(checks) and all(c.passed for c in checks)
    if use_json:
        emit_json(
            {
                "ok": all_passed,
                "project_id": settings.project_id,
                "student_a": stu_a.model_dump(mode="json"),
                "student_b": stu_b.model_dump(mode="json"),
                "services": [s.value for s in selected_services],
                "checks": [c.model_dump(mode="json") for c in checks],
            }
        )
    else:
        render_checks_table(
            checks,
            title=f"Cross-Student Isolation Matrix ({stu_a.slug} vs {stu_b.slug})",
        )

    raise typer.Exit(0 if all_passed else 1)
