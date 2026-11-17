"""Rich table and panel formatters for ManualGround CLI output."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from manualground.config import ShardSettings
from manualground.core.iam_coalescer import CoalesceStats
from manualground.core.models import (
    CheckOutcome,
    ServiceName,
    StepResult,
    StudentSpec,
)
from manualground.core.rate_limiter import DEFAULT_LIMITER_RPMS
from manualground.services import DRIVER_CATALOG

console = Console()
err_console = Console(stderr=True)


def emit_json(payload: Any) -> None:
    """Print structured JSON output with Rich formatting disabled."""
    console.print_json(data=payload)


def print_error(message: str) -> None:
    """Print an actionable error line to stderr."""
    err_console.print(f"  [red]✖[/red] {message}")


def render_roster_table(students: Sequence[StudentSpec], project_id: str) -> None:
    """Render validated student identities and derived per-service resource names."""
    proj = project_id or "<project>"
    table = Table(
        title=f"Validated Student Roster ({len(students)} student(s))",
        box=box.SIMPLE_HEAVY,
        header_style="bold cyan",
    )
    table.add_column("Slug", style="bold magenta")
    table.add_column("Email")
    table.add_column("Service Account")
    table.add_column("Bucket")
    table.add_column("SQL DB / Role")
    table.add_column("Firestore / AR / Search")

    for s in students:
        table.add_row(
            s.slug,
            s.email,
            s.sa_id(),
            s.bucket_name(proj),
            f"{s.sql_db_name()} ({s.sql_role_name()})",
            f"{s.firestore_db_id()} | {s.ar_repo_id()} | {s.search_engine_id()}",
        )
    console.print()
    console.print(table)
    console.print()


def render_steps_table(
    steps: Sequence[StepResult],
    *,
    ledger_path: Path | None = None,
    iam_stats: CoalesceStats | None = None,
    dry_run: bool = False,
) -> None:
    """Render Layer 2 per-student provisioning step outcomes."""
    title = "Layer 2 Provisioning Plan (Dry Run)" if dry_run else "Layer 2 Provisioning Results"
    table = Table(title=title, box=box.SIMPLE_HEAVY, header_style="bold cyan")
    table.add_column("Student", style="bold magenta")
    table.add_column("Service", style="cyan")
    table.add_column("Action")
    table.add_column("Resource")
    table.add_column("Status")
    table.add_column("Time", justify="right")
    table.add_column("Detail", style="dim")

    status_styles = {
        "CREATED": "[green]CREATED[/green]",
        "UNCHANGED": "[blue]UNCHANGED[/blue]",
        "SKIPPED": "[yellow]SKIPPED[/yellow]",
        "FAILED": "[bold red]FAILED[/bold red]",
    }

    for step in steps:
        table.add_row(
            step.student_slug,
            step.service.value,
            step.action,
            step.resource_id,
            status_styles.get(step.status, step.status),
            f"{step.duration_ms}ms" if step.duration_ms else "-",
            step.detail,
        )

    console.print()
    console.print(table)

    created = sum(1 for s in steps if s.status == "CREATED")
    unchanged = sum(1 for s in steps if s.status == "UNCHANGED")
    skipped = sum(1 for s in steps if s.status == "SKIPPED")
    failed = sum(1 for s in steps if s.status == "FAILED")

    summary_parts = [
        f"[green]{created} created[/green]",
        f"[blue]{unchanged} unchanged[/blue]",
        f"[yellow]{skipped} skipped[/yellow]",
        f"[red]{failed} failed[/red]" if failed else "0 failed",
    ]
    console.print("  Summary: " + "  |  ".join(summary_parts))

    if iam_stats is not None:
        console.print(
            f"  Stage C IAM Coalesce: [bold]{iam_stats.total_principals}[/bold]/1400 principals, "
            f"[bold]{iam_stats.conditional_bindings}[/bold]/95 conditional bindings "
            f"({iam_stats.attempts} attempt(s))"
        )
    if ledger_path is not None:
        console.print(f"  Ledger checkpoint: [dim]{ledger_path}[/dim]")
    console.print()


def render_checks_table(
    checks: Sequence[CheckOutcome],
    *,
    title: str = "Isolation and Guardrail Verification",
) -> None:
    """Render preflight or cross-student isolation CheckOutcome rows."""
    table = Table(title=title, box=box.SIMPLE_HEAVY, header_style="bold cyan")
    table.add_column("Result")
    table.add_column("Service", style="cyan")
    table.add_column("Kind")
    table.add_column("Check ID", style="bold")
    table.add_column("Actor", style="magenta")
    table.add_column("Target")
    table.add_column("Expected")
    table.add_column("Actual")
    table.add_column("Detail", style="dim")

    for chk in checks:
        badge = "[green]✔ PASS[/green]" if chk.passed else "[bold red]✖ FAIL[/bold red]"
        table.add_row(
            badge,
            chk.service.value,
            chk.kind,
            chk.check_id,
            chk.actor,
            chk.target,
            chk.expected,
            chk.actual,
            chk.detail,
        )

    passed = sum(1 for c in checks if c.passed)
    total = len(checks)
    console.print()
    console.print(table)
    if total == 0:
        console.print("  [yellow]! No checks were executed.[/yellow]\n")
    elif passed == total:
        console.print(f"  [green]✔ All {total}/{total} checks passed.[/green]\n")
    else:
        console.print(
            f"  [bold red]✖ {total - passed} of {total} checks failed "
            f"({passed}/{total} passed).[/bold red]\n"
        )


def render_status_dashboard(
    settings: ShardSettings,
    availability: dict[ServiceName, bool],
    layer1_ops: Sequence[dict[str, str]],
    ledger_summary: dict[str, Any],
) -> None:
    """Render unified shard configuration, driver rate budgets, Layer 1, and Layer 2 ledger."""
    console.print()
    cfg_lines = [
        f"[bold]Project ID:[/bold]      {settings.project_id or '[yellow](not set: MG_PROJECT_ID)[/yellow]'}",
        f"[bold]Project Number:[/bold]  {settings.project_number or '[dim](not set)[/dim]'}",
        f"[bold]Quota Project:[/bold]   {settings.effective_quota_project or '[dim](not set)[/dim]'}",
        f"[bold]Region / Preset:[/bold] {settings.region}  |  preset={settings.preset}  |  enable_cloud_sql={settings.enable_cloud_sql}",
        f"[bold]SQL Instance:[/bold]    {settings.sql_instance_name or '[dim](derived once project_id is set)[/dim]'}",
        f"[bold]Cloud Run Cap:[/bold]   {settings.max_run_services_per_student} services/student (On-Demand ClickOps + Eventarc Auto-Owner)",
        f"[bold]Ledger Dir:[/bold]      {settings.state_dir}",
    ]
    console.print(
        Panel(
            "\n".join(cfg_lines),
            title="ManualGround Shard Configuration",
            border_style="cyan",
        )
    )

    drv_table = Table(
        title="Layer 2 Service Drivers and Token-Bucket Pacing",
        box=box.SIMPLE_HEAVY,
        header_style="bold cyan",
    )
    drv_table.add_column("Service", style="bold magenta")
    drv_table.add_column("Driver Status")
    drv_table.add_column("Limiter (RPM)", justify="right")
    drv_table.add_column("Checkpoint Slices", justify="right")
    drv_table.add_column("Scope")

    by_svc = ledger_summary.get("by_service", {})
    for desc in DRIVER_CATALOG:
        ready = availability.get(desc.service, False)
        enabled_note = (
            "[dim]DISABLED (ENABLE_CLOUD_SQL=false)[/dim]"
            if desc.service == ServiceName.CLOUD_SQL and not settings.enable_cloud_sql
            else ("[green]✔ READY[/green]" if ready else "[yellow]… PENDING[/yellow]")
        )
        rpm = DEFAULT_LIMITER_RPMS.get(desc.limiter_name, 60.0)
        counts = by_svc.get(desc.service.value, {"completed": 0, "failed": 0})
        cp_text = f"{counts['completed']} ok" + (
            f", [red]{counts['failed']} failed[/red]" if counts["failed"] else ""
        )
        drv_table.add_row(
            desc.service.value,
            enabled_note,
            f"{desc.limiter_name}: {rpm:g} RPM",
            cp_text,
            desc.summary,
        )
    console.print(drv_table)

    if layer1_ops:
        l1_table = Table(
            title="Layer 1 Terraform Baseline Operations",
            box=box.SIMPLE_HEAVY,
            header_style="bold cyan",
        )
        l1_table.add_column("Order", justify="right")
        l1_table.add_column("Operation", style="bold")
        l1_table.add_column("Directory")
        l1_table.add_column("Status")
        l1_table.add_column("Typical Runtime")
        for row in layer1_ops:
            st = row["status"]
            st_fmt = (
                "[green]DONE[/green]"
                if st == "DONE"
                else ("[red]FAILED[/red]" if st == "FAILED" else f"[dim]{st}[/dim]")
            )
            l1_table.add_row(
                row["order"],
                row["operation"],
                row["directory"],
                st_fmt,
                row["duration"],
            )
        console.print(l1_table)

    console.print(
        f"  Ledger: [bold]{ledger_summary['students_tracked']}[/bold] student(s) tracked, "
        f"[green]{ledger_summary['completed_slices']}[/green] completed slice(s), "
        f"{ledger_summary['failed_slices']} failed slice(s)  "
        f"[dim]({ledger_summary['path']})[/dim]\n"
    )
