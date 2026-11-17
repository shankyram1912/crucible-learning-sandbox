"""mg status: offline-safe overview of shard settings, drivers, Layer 1, and ledger state."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from manualground.cli import app as cli_app
from manualground.cli.commands.baseline import read_layer1_status
from manualground.cli.display import emit_json, print_error, render_status_dashboard
from manualground.core.ledger import ProvisioningLedger
from manualground.core.naming import email_to_slug, normalize_slug
from manualground.core.rate_limiter import DEFAULT_LIMITER_RPMS
from manualground.services import (
    DRIVER_CATALOG,
    available_drivers,
    parse_service_selection,
)


def status_cmd(
    services: Annotated[
        list[str] | None,
        typer.Option(
            "--services",
            "-S",
            help="Filter checkpoint summary to specific services (gemini,gcs,run,sql,firestore,search).",
        ),
    ] = None,
    student: Annotated[
        list[str] | None,
        typer.Option("--student", "-s", help="Filter checkpoint summary to student slug(s) or email(s)."),
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
    """Display shard settings, driver availability, rate budgets, Layer 1 status, and ledger."""
    use_json = cli_app.state.json or json_out
    settings = cli_app.resolve_settings(env_file=env_file, project_id=project_id)

    try:
        selected_services = (
            set(parse_service_selection(services, settings=settings))
            if services
            else None
        )
    except ValueError as exc:
        if use_json:
            emit_json({"ok": False, "error": str(exc)})
        else:
            print_error(str(exc))
        raise typer.Exit(2) from exc

    student_slugs: set[str] | None = None
    if student:
        student_slugs = set()
        for item in student:
            for tok in item.split(","):
                cleaned = tok.strip()
                if not cleaned:
                    continue
                student_slugs.add(
                    email_to_slug(cleaned) if "@" in cleaned else normalize_slug(cleaned)
                )

    availability = available_drivers()
    layer1_ops = read_layer1_status()
    ledger = ProvisioningLedger(settings.state_dir, settings.project_id)
    ledger_summary = ledger.summary(
        student_filter=student_slugs,
        service_filter=selected_services,
    )

    if use_json:
        emit_json(
            {
                "ok": True,
                "settings": {
                    "project_id": settings.project_id,
                    "project_number": settings.project_number,
                    "quota_project": settings.effective_quota_project,
                    "org_id": settings.org_id,
                    "domain": settings.domain,
                    "parent_folder_id": settings.parent_folder_id,
                    "playground_folder_id": settings.playground_folder_id,
                    "region": settings.region,
                    "preset": settings.preset,
                    "enable_cloud_sql": settings.enable_cloud_sql,
                    "sql_instance_name": settings.sql_instance_name,
                    "max_run_services_per_student": settings.max_run_services_per_student,
                    "state_dir": str(settings.state_dir),
                },
                "drivers": [
                    {
                        "service": desc.service.value,
                        "module": desc.module_path,
                        "available": availability[desc.service],
                        "limiter_name": desc.limiter_name,
                        "rpm": DEFAULT_LIMITER_RPMS.get(desc.limiter_name, 60.0),
                        "summary": desc.summary,
                    }
                    for desc in DRIVER_CATALOG
                ],
                "layer1_operations": layer1_ops,
                "ledger": ledger_summary,
            }
        )
        return

    render_status_dashboard(settings, availability, layer1_ops, ledger_summary)
