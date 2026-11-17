"""mg roster: validate student CSV rosters and apply rate-paced Layer 2 slices."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

import typer

from manualground.cli import app as cli_app
from manualground.cli.display import (
    console,
    emit_json,
    print_error,
    render_roster_table,
    render_steps_table,
)
from manualground.config import PACKAGE_ROOT
from manualground.core.http_client import GcpError
from manualground.core.iam_coalescer import (
    CoalesceStats,
    ProjectIamCoalescer,
    QuotaBudgetExceededError,
)
from manualground.core.ledger import ProvisioningLedger
from manualground.core.models import (
    ConditionalBindingSpec,
    ServiceName,
    StepResult,
    StudentSpec,
)
from manualground.core.naming import RosterValidationError, load_roster_csv
from manualground.services import (
    DriverUnavailableError,
    get_driver,
    parse_service_selection,
)

DEFAULT_SAMPLE_ROSTER = PACKAGE_ROOT / "rosters" / "sample-2students.csv"

roster_app = typer.Typer(
    help="Validate student CSV rosters, apply rate-paced Layer 2 slices, or manage checkpoints.",
    no_args_is_help=True,
)


def _resolve_roster_path(pos_path: Path | None, opt_path: Path | None) -> Path:
    if pos_path is not None and opt_path is not None and pos_path != opt_path:
        raise RosterValidationError(
            f"Conflicting roster paths provided: {pos_path} vs {opt_path}"
        )
    chosen = opt_path or pos_path
    if chosen is not None:
        return chosen
    if DEFAULT_SAMPLE_ROSTER.is_file():
        return DEFAULT_SAMPLE_ROSTER
    raise RosterValidationError(
        "No roster CSV specified. Pass a path or --roster <file.csv>."
    )


@roster_app.command("validate")
def roster_validate(
    roster_csv: Annotated[
        Path | None,
        typer.Argument(help="Path to student roster CSV (defaults to rosters/sample-2students.csv)."),
    ] = None,
    roster: Annotated[
        Path | None,
        typer.Option("--roster", "-r", help="Path to student roster CSV."),
    ] = None,
    student: Annotated[
        list[str] | None,
        typer.Option("--student", "-s", help="Filter to specific student slug(s) or email(s)."),
    ] = None,
    project_id: Annotated[
        str | None,
        typer.Option("--project-id", help="Override MG_PROJECT_ID for bucket/SA previews."),
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
    """Validate CSV formatting, slug normalization, 30/63-char bounds, and uniqueness."""
    use_json = cli_app.state.json or json_out
    settings = cli_app.resolve_settings(env_file=env_file, project_id=project_id)

    try:
        csv_path = _resolve_roster_path(roster_csv, roster)
        students = cli_app.filter_students(load_roster_csv(csv_path), student)
    except (RosterValidationError, ValueError) as exc:
        if use_json:
            emit_json({"ok": False, "error": str(exc), "students": []})
        else:
            print_error(str(exc))
        raise typer.Exit(2) from exc

    proj = settings.project_id or "ntu-shard-preview"
    if use_json:
        emit_json(
            {
                "ok": True,
                "roster_path": str(csv_path),
                "count": len(students),
                "students": [
                    {
                        "email": s.email,
                        "slug": s.slug,
                        "display_name": s.display_name,
                        "sa_id": s.sa_id(),
                        "sa_email": s.sa_email(proj),
                        "sql_iam_sa_user": s.sql_iam_sa_user(proj),
                        "bucket_name": s.bucket_name(proj),
                        "ar_repo_id": s.ar_repo_id(),
                        "sql_db_name": s.sql_db_name(),
                        "sql_role_name": s.sql_role_name(),
                        "firestore_db_id": s.firestore_db_id(),
                        "search_datastore_id": s.search_datastore_id(),
                        "search_engine_id": s.search_engine_id(),
                    }
                    for s in students
                ],
            }
        )
        return

    render_roster_table(students, proj)


@roster_app.command("apply")
def roster_apply(
    roster_csv: Annotated[
        Path | None,
        typer.Argument(help="Path to student roster CSV (defaults to rosters/sample-2students.csv)."),
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
        typer.Option("--student", "-s", help="Filter to specific student slug(s) or email(s)."),
    ] = None,
    resume: Annotated[
        bool,
        typer.Option(
            "--resume/--no-resume",
            help="Skip (student, service) slices already marked COMPLETED in the ledger.",
        ),
    ] = True,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview planned slices without mutating GCP."),
    ] = False,
    propagation_wait: Annotated[
        float | None,
        typer.Option(
            "--propagation-wait",
            help="Seconds to pause after Stage A creates new SAs (default 15s live, 0s mocked).",
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
    """Execute Stage A identity barrier, Stage B rate-paced drivers, and Stage C IAM coalesce."""
    use_json = cli_app.state.json or json_out
    settings = cli_app.resolve_settings(env_file=env_file, project_id=project_id)

    if not settings.project_id:
        msg = "MG_PROJECT_ID is not set. Configure initialize.env or pass --project-id."
        if use_json:
            emit_json({"ok": False, "error": msg, "steps": []})
        else:
            print_error(msg)
        raise typer.Exit(2)

    try:
        csv_path = _resolve_roster_path(roster_csv, roster)
        full_roster = load_roster_csv(csv_path)
        target_students = cli_app.filter_students(full_roster, student)
        selected_services = parse_service_selection(services, settings=settings)
    except (RosterValidationError, ValueError) as exc:
        if use_json:
            emit_json({"ok": False, "error": str(exc), "steps": []})
        else:
            print_error(str(exc))
        raise typer.Exit(2) from exc

    ledger = ProvisioningLedger(settings.state_dir, settings.project_id)
    all_steps: list[StepResult] = []

    if dry_run:
        for stu in target_students:
            for svc in selected_services:
                already_done = resume and ledger.is_completed(stu.slug, svc)
                all_steps.append(
                    StepResult(
                        service=svc,
                        student_slug=stu.slug,
                        action="dry_run",
                        resource_id= _preview_resource_id(stu, svc, settings.project_id),
                        status="SKIPPED",
                        detail="resumed from checkpoint" if already_done else "planned (dry-run)",
                    )
                )
        if use_json:
            emit_json(
                {
                    "ok": True,
                    "dry_run": True,
                    "project_id": settings.project_id,
                    "steps": [s.model_dump(mode="json") for s in all_steps],
                }
            )
        else:
            render_steps_table(all_steps, ledger_path=ledger.path, dry_run=True)
        return

    admin_client = cli_app.build_admin_client(settings)
    iam_stats: CoalesceStats | None = None
    stage_c_error = ""

    try:
        drivers = {}
        for svc in selected_services:
            try:
                drivers[svc] = get_driver(svc, admin_client)
            except DriverUnavailableError as exc:
                for stu in target_students:
                    all_steps.append(
                        StepResult(
                            service=svc,
                            student_slug=stu.slug,
                            action="load_driver",
                            resource_id=svc.value,
                            status="FAILED",
                            detail=str(exc),
                        )
                    )

        # Stage A: Prerequisite Service Account Identity Barrier
        if ServiceName.GEMINI_SA in drivers:
            sa_driver = drivers[ServiceName.GEMINI_SA]
            newly_created_sa = False
            for stu in target_students:
                if resume and ledger.is_completed(stu.slug, ServiceName.GEMINI_SA):
                    all_steps.append(
                        StepResult(
                            service=ServiceName.GEMINI_SA,
                            student_slug=stu.slug,
                            action="checkpoint",
                            resource_id=stu.sa_id(),
                            status="SKIPPED",
                            detail="resumed from ledger checkpoint",
                        )
                    )
                    continue
                stu_steps = _execute_student_slice(
                    sa_driver, settings, stu, ledger
                )
                all_steps.extend(stu_steps)
                if any(st.status == "CREATED" for st in stu_steps):
                    newly_created_sa = True

            effective_wait = (
                (0.0 if admin_client._transport is not None else 15.0)
                if propagation_wait is None
                else propagation_wait
            )
            if newly_created_sa and effective_wait > 0:
                admin_client._sleep(effective_wait)

        # Stage B: Rate-Paced Service Drivers
        for svc in selected_services:
            if svc == ServiceName.GEMINI_SA or svc not in drivers:
                continue
            drv = drivers[svc]
            for stu in target_students:
                if resume and ledger.is_completed(stu.slug, svc):
                    all_steps.append(
                        StepResult(
                            service=svc,
                            student_slug=stu.slug,
                            action="checkpoint",
                            resource_id=_preview_resource_id(stu, svc, settings.project_id),
                            status="SKIPPED",
                            detail="resumed from ledger checkpoint",
                        )
                    )
                    continue
                stu_steps = _execute_student_slice(drv, settings, stu, ledger)
                all_steps.extend(stu_steps)

        # Stage C: Single-Shot Coalesced Project IAM Policy Commit (version=3)
        coalesced_specs: list[ConditionalBindingSpec] = []
        roster_for_iam = full_roster if student is None else target_students
        for svc in selected_services:
            if svc not in drivers:
                continue
            drv = drivers[svc]
            for stu in roster_for_iam:
                coalesced_specs.extend(drv.project_iam_bindings(settings, stu))

        if coalesced_specs:
            coalescer = ProjectIamCoalescer(admin_client, settings.project_id)
            coalescer.add_many(coalesced_specs)
            try:
                coalescer.commit()
                iam_stats = coalescer.last_stats
                if iam_stats is not None:
                    ledger.record_iam_coalesce(
                        total_principals=iam_stats.total_principals,
                        conditional_bindings=iam_stats.conditional_bindings,
                        attempts=iam_stats.attempts,
                    )
            except (QuotaBudgetExceededError, GcpError) as exc:
                stage_c_error = str(exc)
                all_steps.append(
                    StepResult(
                        service=ServiceName.FIRESTORE,
                        student_slug="*",
                        action="project_iam_coalesce",
                        resource_id=f"projects/{settings.project_id}",
                        status="FAILED",
                        detail=stage_c_error,
                    )
                )
    finally:
        admin_client.close()

    ok = not stage_c_error and not any(s.status == "FAILED" for s in all_steps)
    if use_json:
        emit_json(
            {
                "ok": ok,
                "project_id": settings.project_id,
                "ledger_path": str(ledger.path),
                "steps": [s.model_dump(mode="json") for s in all_steps],
                "iam_coalesce": (
                    {
                        "total_principals": iam_stats.total_principals,
                        "conditional_bindings": iam_stats.conditional_bindings,
                        "attempts": iam_stats.attempts,
                        "changed": iam_stats.changed,
                    }
                    if iam_stats is not None
                    else None
                ),
                "error": stage_c_error or None,
            }
        )
    else:
        render_steps_table(
            all_steps,
            ledger_path=ledger.path,
            iam_stats=iam_stats,
        )

    raise typer.Exit(0 if ok else 1)


@roster_app.command("reset")
def roster_reset(
    services: Annotated[
        list[str] | None,
        typer.Option("--services", "-S", help="Reset only specific service checkpoints."),
    ] = None,
    student: Annotated[
        str | None,
        typer.Option("--student", "-s", help="Reset only one student slug."),
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
    """Clear resumable ledger checkpoints for a shard, student, or service subset."""
    use_json = cli_app.state.json or json_out
    settings = cli_app.resolve_settings(env_file=env_file, project_id=project_id)
    svc_list = parse_service_selection(services, settings=settings) if services else None
    ledger = ProvisioningLedger(settings.state_dir, settings.project_id)
    ledger.reset(student_slug=student, services=svc_list)
    if use_json:
        emit_json({"ok": True, "ledger_path": str(ledger.path)})
    else:
        console.print(f"\n  [green]✔[/green] Reset ledger checkpoints in {ledger.path}\n")


def _execute_student_slice(
    driver: object,
    settings: object,
    student: StudentSpec,
    ledger: ProvisioningLedger,
) -> list[StepResult]:
    t0 = time.monotonic()
    svc: ServiceName = getattr(driver, "service")
    try:
        steps: list[StepResult] = driver.provision_student(settings, student)  # type: ignore[attr-defined]
        ledger.record_service_outcome(student, svc, steps)
        return steps
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        fail_step = StepResult(
            service=svc,
            student_slug=student.slug,
            action="provision_student",
            resource_id=_preview_resource_id(student, svc, getattr(settings, "project_id", "")),
            status="FAILED",
            duration_ms=elapsed_ms,
            detail=str(exc),
        )
        ledger.record_service_outcome(student, svc, [fail_step], error=str(exc))
        return [fail_step]


def _preview_resource_id(student: StudentSpec, svc: ServiceName, project_id: str) -> str:
    if svc == ServiceName.GEMINI_SA:
        return student.sa_id()
    if svc == ServiceName.GCS:
        return student.bucket_name(project_id or "project")
    if svc == ServiceName.CLOUD_RUN:
        return student.ar_repo_id()
    if svc == ServiceName.CLOUD_SQL:
        return student.sql_db_name()
    if svc == ServiceName.FIRESTORE:
        return student.firestore_db_id()
    return student.search_engine_id()
