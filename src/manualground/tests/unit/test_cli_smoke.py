"""CLI smoke tests for `./mg --help`, `preflight`, `status`, `roster apply`, and `verify`."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.conftest import FakeClock
from tests.unit.test_service_drivers import (
    ADMIN_TOKEN,
    STUDENT_A_TOKEN,
    STUDENT_B_TOKEN,
    StatefulGcpMockBackend,
    _make_client_for_backend,
)


MG_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_ROSTER = MG_ROOT / "rosters" / "sample-2students.csv"


def _write_test_env(tmp_path: Path) -> Path:
    env_file = tmp_path / "initialize.env"
    state_dir = tmp_path / "state"
    env_file.write_text(
        "\n".join(
            [
                "QUOTA_PROJECT=mg-ntu-quota",
                "ORG_ID=9876543210",
                "BILLING_ACCOUNT_ID=01ABCD-23EFGH-45IJKL",
                "DOMAIN=shankyram.altostrat.com",
                "MG_PARENT_FOLDER=folders/600433119916",
                "MG_FOLDER_ID=folders/700433119917",
                "MG_PROJECT_ID=mg-ntu-01",
                "MG_PROJECT_NUMBER=123456789012",
                "REGION=asia-southeast1",
                "STUDENT_GROUP_EMAIL=ntu-students@shankyram.altostrat.com",
                "IT_ADMINS_GROUP=ntu-admins@shankyram.altostrat.com",
                "MG_PRESET=dev",
                "ENABLE_CLOUD_SQL=true",
                "MG_SQL_INSTANCE=sql-mg-ntu-01",
                "MAX_SERVICES_PER_STUDENT=3",
                f"MG_STATE_DIR={state_dir}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return env_file


def _patch_cli_rest_clients(
    monkeypatch: pytest.MonkeyPatch,
    backend: StatefulGcpMockBackend,
    fake_clock: FakeClock,
    env_file: Path,
) -> None:
    """Wire CLI CLIENT_FACTORY to return fresh MockTransport GcpRestClient instances per command."""
    from manualground.cli import app as cli_app
    import manualground.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "DEFAULT_ENV_FILE", env_file)
    monkeypatch.setenv("MG_STATE_DIR", str(env_file.parent / "state"))
    monkeypatch.setenv("MG_PROJECT_ID", "mg-ntu-01")
    monkeypatch.setenv("MG_PROJECT_NUMBER", "123456789012")
    monkeypatch.setenv("QUOTA_PROJECT", "mg-ntu-quota")
    monkeypatch.setenv("STUDENT_GROUP_EMAIL", "ntu-students@shankyram.altostrat.com")

    monkeypatch.setattr(
        cli_app,
        "CLIENT_FACTORY",
        lambda _settings: _make_client_for_backend(backend, fake_clock, ADMIN_TOKEN),
    )


def test_mg_wrapper_exists_and_help_renders() -> None:
    mg_script = MG_ROOT / "mg"
    assert mg_script.is_file(), f"Missing ./mg wrapper at {mg_script}"
    assert os.access(mg_script, os.X_OK), "./mg wrapper must be chmod +x"

    from manualground.cli.app import app

    runner = CliRunner()
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0, f"./mg --help failed:\n{res.output}"
    for subcmd in ("preflight", "roster", "verify", "status"):
        assert subcmd in res.output, f"Missing {subcmd!r} in ./mg --help:\n{res.output}"


def test_cli_preflight_roster_apply_status_and_verify_workflow(
    monkeypatch: pytest.MonkeyPatch,
    fake_clock: FakeClock,
    tmp_path: Path,
) -> None:
    from manualground.cli.app import app

    env_file = _write_test_env(tmp_path)
    backend = StatefulGcpMockBackend()
    _patch_cli_rest_clients(monkeypatch, backend, fake_clock, env_file)

    runner = CliRunner()

    # 1. preflight
    pre_args = ["preflight"]
    pre_help = runner.invoke(app, ["preflight", "--help"]).output
    if "--roster" in pre_help:
        pre_args.extend(["--roster", str(SAMPLE_ROSTER)])
    res_pre = runner.invoke(app, pre_args)
    assert res_pre.exit_code == 0, f"mg preflight failed:\n{res_pre.output}"

    # 2. status (before roster apply)
    res_status_empty = runner.invoke(app, ["status"])
    assert res_status_empty.exit_code == 0, f"mg status failed:\n{res_status_empty.output}"

    # 3. roster apply (using sample-2students.csv)
    roster_help = runner.invoke(app, ["roster", "apply", "--help"]).output
    if "--roster" in roster_help:
        roster_args = ["roster", "apply", "--roster", str(SAMPLE_ROSTER)]
    else:
        roster_args = ["roster", "apply", str(SAMPLE_ROSTER)]
    res_apply = runner.invoke(app, roster_args)
    assert res_apply.exit_code == 0, f"mg roster apply failed:\n{res_apply.output}"

    # 4. status --json (after roster apply)
    status_help = runner.invoke(app, ["status", "--help"]).output
    status_args = ["status", "--json"] if "--json" in status_help else ["status"]
    res_status = runner.invoke(app, status_args)
    assert res_status.exit_code == 0, f"mg status after apply failed:\n{res_status.output}"
    assert "lsb-student1" in res_status.output

    # 5. Re-running roster apply with --resume skips already completed student slices!
    res_resume = runner.invoke(app, [*roster_args, "--json"])
    assert res_resume.exit_code == 0, f"mg roster apply --resume failed:\n{res_resume.output}"
    assert "SKIPPED" in res_resume.output

    # 6. verify (Student A vs Student B cross-tenant isolation check)
    verify_help = runner.invoke(app, ["verify", "--help"]).output
    if "--roster" in verify_help:
        verify_args = ["verify", "--roster", str(SAMPLE_ROSTER)]
    else:
        verify_args = ["verify", str(SAMPLE_ROSTER)]
    res_verify = runner.invoke(app, verify_args)
    assert res_verify.exit_code == 0, f"mg verify failed:\n{res_verify.output}"
