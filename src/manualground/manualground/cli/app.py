"""Main Typer CLI entrypoint for ManualGround (./mg)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from manualground import __version__
from manualground.config import ShardSettings
from manualground.core.http_client import GcpRestClient
from manualground.core.models import StudentSpec
from manualground.core.naming import RosterValidationError, email_to_slug, normalize_slug


@dataclass
class CliState:
    """Per-invocation global CLI flags."""

    json: bool = False
    env_file: Path | None = None
    project_id: str | None = None


state = CliState()

CLIENT_FACTORY: Callable[[ShardSettings], GcpRestClient] | None = None


def resolve_settings(
    *,
    env_file: Path | None = None,
    project_id: str | None = None,
) -> ShardSettings:
    """Resolve ShardSettings combining initialize.env, environment variables, and CLI flags."""
    chosen_env = env_file or state.env_file
    chosen_project = project_id or state.project_id
    overrides = {}
    if chosen_project:
        overrides["project_id"] = chosen_project
    return ShardSettings.from_env_file(env_file=chosen_env, **overrides)


def build_admin_client(settings: ShardSettings) -> GcpRestClient:
    """Construct the Layer 2 provisioner GcpRestClient (monkeypatchable for unit tests)."""
    if CLIENT_FACTORY is not None:
        return CLIENT_FACTORY(settings)
    return GcpRestClient(quota_project=settings.effective_quota_project)


def build_student_client(
    settings: ShardSettings,
    student: StudentSpec,
    admin_client: GcpRestClient,
    *,
    bearer_token: str | None = None,
) -> GcpRestClient:
    """Construct a student-scoped GcpRestClient via bearer token or SA impersonation."""
    if bearer_token:
        return admin_client.with_token(
            bearer_token,
            quota_project=settings.effective_quota_project,
        )
    sa_email = student.sa_email(settings.project_id)
    return admin_client.for_impersonated_sa(
        sa_email,
        quota_project=settings.effective_quota_project,
    )


def filter_students(
    students: Sequence[StudentSpec],
    raw_filters: Sequence[str] | None,
) -> list[StudentSpec]:
    """Filter a validated roster by student slug(s) or email(s) while preserving order."""
    if not raw_filters:
        return list(students)

    wanted_slugs: set[str] = set()
    wanted_emails: set[str] = set()
    for entry in raw_filters:
        for token in entry.split(","):
            cleaned = token.strip().lower()
            if not cleaned:
                continue
            if "@" in cleaned:
                wanted_emails.add(cleaned)
                wanted_slugs.add(email_to_slug(cleaned))
            else:
                wanted_slugs.add(normalize_slug(cleaned))

    matched = [
        s
        for s in students
        if s.slug in wanted_slugs or s.email in wanted_emails
    ]
    if not matched:
        raise RosterValidationError(
            f"No students in roster matched filter: {', '.join(raw_filters)}"
        )
    return matched


APP_HELP = """NTU ManualGround: Layer 2 rate-paced bulk provisioner and isolation verifier.

Services (--services / -S):
  gemini     Per-student service account (sa-<student>) + Vertex AI Gemini access
  gcs        Dedicated Cloud Storage bucket (bkt-<project>-<student>) with UBLA/PAP
  run        Artifact Registry repo (ar-<student>) + Eventarc Auto-Owner Cloud Run
  sql        PostgreSQL 16 database (db_<student>), IAM users, and REVOKE PUBLIC DDL
  firestore  Named Native database (fs-<student>) + conditional v3 project IAM
  search     Vertex AI Search DataStore (ds-<student>) + Engine (eng-<student>)

Common Workflows:
  ./mg status
  ./mg baseline status
  ./mg preflight --roster rosters/sample-2students.csv
  ./mg roster validate rosters/sample-2students.csv
  ./mg roster apply rosters/sample-2students.csv --services gemini,gcs,run
  ./mg verify rosters/sample-2students.csv
"""

app = typer.Typer(
    name="mg",
    help=APP_HELP,
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"manualground {__version__}")
        raise typer.Exit(0)


@app.callback()
def main_callback(
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON output."),
    ] = False,
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", "-e", help="Path to initialize.env file."),
    ] = None,
    project_id: Annotated[
        str | None,
        typer.Option("--project-id", help="Override MG_PROJECT_ID across commands."),
    ] = None,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Show ManualGround CLI version and exit.",
        ),
    ] = False,
) -> None:
    """Configure global ManualGround CLI flags."""
    state.json = json_out
    state.env_file = env_file
    state.project_id = project_id


from manualground.cli.commands.baseline import baseline_app  # noqa: E402
from manualground.cli.commands.preflight import preflight_cmd  # noqa: E402
from manualground.cli.commands.roster import roster_app  # noqa: E402
from manualground.cli.commands.status import status_cmd  # noqa: E402
from manualground.cli.commands.verify import verify_cmd  # noqa: E402

app.command("preflight")(preflight_cmd)
app.add_typer(baseline_app, name="baseline")
app.add_typer(roster_app, name="roster")
app.command("verify")(verify_cmd)
app.command("status")(status_cmd)


if __name__ == "__main__":
    app()
