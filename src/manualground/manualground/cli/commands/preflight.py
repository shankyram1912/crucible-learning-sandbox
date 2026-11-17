"""mg preflight: validate shard readiness, quotas, and optional student roster."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from manualground.cli import app as cli_app
from manualground.cli.display import emit_json, print_error, render_checks_table
from manualground.core.http_client import GcpError
from manualground.core.models import CheckOutcome, ServiceName, StudentSpec
from manualground.core.naming import RosterValidationError, load_roster_csv
from manualground.services import (
    DriverUnavailableError,
    get_driver,
    parse_service_selection,
)

MAX_RECOMMENDED_STUDENTS_PER_SHARD = 80


def preflight_cmd(
    roster: Annotated[
        Path | None,
        typer.Option(
            "--roster",
            "-r",
            help="Optional student roster CSV to validate alongside shard quotas.",
        ),
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
            help="Filter roster checks to specific student slug(s) or email(s).",
        ),
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
    """Verify shard configuration, API/quota budgets, guardrails, and optional roster bounds."""
    use_json = cli_app.state.json or json_out
    settings = cli_app.resolve_settings(env_file=env_file, project_id=project_id)

    if not settings.project_id:
        msg = "MG_PROJECT_ID is not set. Configure initialize.env or pass --project-id."
        if use_json:
            emit_json({"ok": False, "error": msg, "checks": []})
        else:
            print_error(msg)
        raise typer.Exit(2)

    try:
        selected_services = parse_service_selection(services, settings=settings)
    except ValueError as exc:
        if use_json:
            emit_json({"ok": False, "error": str(exc), "checks": []})
        else:
            print_error(str(exc))
        raise typer.Exit(2) from exc

    students: list[StudentSpec] = []
    checks: list[CheckOutcome] = []

    if roster is not None:
        try:
            students = cli_app.filter_students(load_roster_csv(roster), student)
        except (RosterValidationError, ValueError) as exc:
            if use_json:
                emit_json({"ok": False, "error": str(exc), "checks": []})
            else:
                print_error(str(exc))
            raise typer.Exit(2) from exc

        within_cap = len(students) <= MAX_RECOMMENDED_STUDENTS_PER_SHARD
        checks.append(
            CheckOutcome(
                service=ServiceName.GEMINI_SA,
                check_id="preflight.shard_roster_headcount",
                kind="GUARDRAIL",
                actor="preflight",
                target=settings.project_id,
                passed=within_cap,
                expected=f"<= {MAX_RECOMMENDED_STUDENTS_PER_SHARD} students",
                actual=f"{len(students)} students",
                detail=f"Roster file: {roster}",
            )
        )

    admin_client = cli_app.build_admin_client(settings)
    try:
        for svc in selected_services:
            try:
                driver = get_driver(svc, admin_client)
                drv_checks = driver.preflight(settings, students)
                checks.extend(drv_checks)
            except DriverUnavailableError as exc:
                checks.append(
                    CheckOutcome(
                        service=svc,
                        check_id=f"preflight.{svc.value}.driver_available",
                        kind="GUARDRAIL",
                        actor="preflight",
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
                        check_id=f"preflight.{svc.value}.api_reachable",
                        kind="GUARDRAIL",
                        actor="preflight",
                        target=settings.project_id,
                        passed=False,
                        expected="HTTP 200",
                        actual="GcpError",
                        detail=str(exc),
                    )
                )
    finally:
        admin_client.close()

    all_passed = bool(checks) and all(c.passed for c in checks) if checks else True
    if use_json:
        emit_json(
            {
                "ok": all_passed,
                "project_id": settings.project_id,
                "services": [s.value for s in selected_services],
                "roster_count": len(students),
                "checks": [c.model_dump(mode="json") for c in checks],
            }
        )
    else:
        render_checks_table(
            checks,
            title=f"Preflight Readiness Checks ({settings.project_id})",
        )

    raise typer.Exit(0 if all_passed else 1)
