"""mg baseline: inspect and invoke Layer 1 Terraform shard baseline operations."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from manualground.cli import app as cli_app
from manualground.cli.display import console, emit_json, print_error
from manualground.config import PACKAGE_ROOT

TERRAFORM_DIR = PACKAGE_ROOT / "terraform"
SANDBOX_TERRAFORM_BIN = Path(
    "/usr/local/google/home/shankyram/workspace/code-sandbox/tools/terraform-1.17.1/terraform"
)

LAYER1_OPERATIONS: tuple[dict[str, str], ...] = (
    {
        "order": "1",
        "operation": "FolderGuardrailsCreate",
        "directory": "01-folder-guardrails",
        "duration": "1-3 min",
        "long_running": "false",
        "watch_hint": "gcloud resource-manager org-policies list --folder=<MG_FOLDER_ID>",
    },
    {
        "order": "2",
        "operation": "ShardProjectCreate",
        "directory": "02-shard-project-baseline",
        "duration": "2-5 min",
        "long_running": "false",
        "watch_hint": "gcloud services list --enabled --project=<MG_PROJECT_ID>",
    },
    {
        "order": "3",
        "operation": "CloudRunAutoOwnerCreate",
        "directory": "03-cloud-run-auto-owner",
        "duration": "LONG-RUNNING: 5-12 min (20m timeout)",
        "long_running": "true",
        "watch_hint": "gcloud eventarc triggers list --location=<REGION> --project=<MG_PROJECT_ID>",
    },
    {
        "order": "4",
        "operation": "SharedCloudSqlCreate",
        "directory": "04-shared-cloud-sql",
        "duration": "LONG-RUNNING: 10-20 min (45m timeout)",
        "long_running": "true",
        "watch_hint": "gcloud sql operations list --instance=<MG_SQL_INSTANCE> --project=<MG_PROJECT_ID> --limit=5",
    },
)

baseline_app = typer.Typer(
    help="Inspect or run Layer 1 Terraform baseline operations (01 through 04).",
    invoke_without_command=True,
)


def read_layer1_status() -> list[dict[str, str]]:
    """Combine static Layer 1 catalog metadata with terraform/manualground.status if present."""
    status_values: dict[str, str] = {}
    for candidate in (
        TERRAFORM_DIR / "manualground.status",
        PACKAGE_ROOT / "manualground.status",
    ):
        if candidate.is_file():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                k, v = stripped.split("=", 1)
                status_values[k.strip()] = v.strip().strip('"').strip("'")
            break

    rows: list[dict[str, str]] = []
    for item in LAYER1_OPERATIONS:
        op_name = item["operation"]
        st = status_values.get(f"{op_name}_STATUS", "NOT_STARTED")
        rows.append({**item, "status": st})
    return rows


def detect_terraform_binary() -> str | None:
    """Locate Terraform binary across local tool paths and PATH."""
    local_bin = Path.home() / ".local" / "bin" / "terraform"
    for candidate in (SANDBOX_TERRAFORM_BIN, local_bin):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("terraform")


@baseline_app.callback()
def baseline_default(
    ctx: typer.Context,
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON output."),
    ] = False,
) -> None:
    """Show Layer 1 Terraform operation status when invoked without a subcommand."""
    if ctx.invoked_subcommand is None:
        baseline_status(json_out=json_out)


@baseline_app.command("status")
def baseline_status(
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON output."),
    ] = False,
) -> None:
    """Show Layer 1 Terraform operations, LONG-RUNNING durations, and watch commands."""
    use_json = cli_app.state.json or json_out
    rows = read_layer1_status()
    tf_bin = detect_terraform_binary()
    run_sh = TERRAFORM_DIR / "run.sh"

    if use_json:
        emit_json(
            {
                "terraform_binary": tf_bin,
                "runner_script": str(run_sh),
                "runner_exists": run_sh.is_file(),
                "operations": rows,
            }
        )
        return

    table = Table(
        title="Layer 1 Terraform Baseline Operations",
        box=box.SIMPLE_HEAVY,
        header_style="bold cyan",
    )
    table.add_column("#", justify="right")
    table.add_column("Operation", style="bold magenta")
    table.add_column("Directory")
    table.add_column("Status")
    table.add_column("Typical Duration")
    table.add_column("Live Watch Command", style="dim")

    for r in rows:
        st = r["status"]
        st_fmt = (
            "[green]DONE[/green]"
            if st == "DONE"
            else ("[red]FAILED[/red]" if st == "FAILED" else f"[dim]{st}[/dim]")
        )
        dur_fmt = (
            f"[yellow]{r['duration']}[/yellow]"
            if r["long_running"] == "true"
            else r["duration"]
        )
        table.add_row(
            r["order"],
            r["operation"],
            r["directory"],
            st_fmt,
            dur_fmt,
            r["watch_hint"],
        )

    console.print()
    console.print(table)
    console.print(f"  Terraform binary: {tf_bin or '[yellow]not found on PATH[/yellow]'}")
    console.print(f"  Layer 1 runner:   ./terraform/run.sh --operation=RunAll\n")


@baseline_app.command("run")
def baseline_run(
    operation: Annotated[
        str,
        typer.Option(
            "--operation",
            "-o",
            help="Operation name (Status, RunAll, FolderGuardrailsCreate, ShardProjectCreate, CloudRunAutoOwnerCreate, SharedCloudSqlCreate).",
        ),
    ] = "Status",
    validate_only: Annotated[
        bool,
        typer.Option("--validate-only", help="Run pre-apply validation checks only."),
    ] = False,
    describe: Annotated[
        bool,
        typer.Option("--describe", help="Print operation description and stop."),
    ] = False,
    auto_approve: Annotated[
        bool,
        typer.Option("--auto-approve", help="Approve Terraform plan non-interactively."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Run even if the preceding operation is not DONE."),
    ] = False,
    no_tmux: Annotated[
        bool,
        typer.Option("--no-tmux", help="Run in current terminal without tmux."),
    ] = True,
) -> None:
    """Delegate to terraform/run.sh for Layer 1 shard foundation provisioning."""
    run_sh = TERRAFORM_DIR / "run.sh"
    if not run_sh.is_file():
        print_error(f"Layer 1 runner script not found at {run_sh}")
        raise typer.Exit(2)

    cmd = ["bash", str(run_sh), f"--operation={operation}"]
    if validate_only:
        cmd.append("--validate-only")
    if describe:
        cmd.append("--describe")
    if auto_approve:
        cmd.append("--auto-approve")
    if force:
        cmd.append("--force")
    if no_tmux:
        cmd.append("--no-tmux")

    result = subprocess.run(cmd, check=False)
    raise typer.Exit(result.returncode)
