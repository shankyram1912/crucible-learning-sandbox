"""Static validation and hygiene checks across all 4 Layer 1 Terraform stacks."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import subprocess

import pytest


MG_ROOT = Path(__file__).resolve().parents[2]
TF_ROOT = MG_ROOT / "terraform"

EXPECTED_STACKS = (
    "01-folder-guardrails",
    "02-shard-project-baseline",
    "03-cloud-run-auto-owner",
    "04-shared-cloud-sql",
)

EXPECTED_CUSTOM_ROLES = (
    "custom_ntu_gemini_caller",
    "custom_ntu_gcs_bucket_metadata_viewer",
    "custom_ntu_gcs_console_lister",
    "custom_ntu_run_creator",
    "custom_ntu_run_owner",
    "custom_ntu_sql_connect",
    "custom_ntu_firestore_db_user",
    "custom_ntu_firestore_project_browser",
    "custom_ntu_vertex_search_console",
)

# Dedicated QA scratch validation mirror outside the Git repository so src/manualground/terraform stays 100% clean.
SCRATCH_VALIDATE_ROOT = Path("/usr/local/google/home/shankyram/workspace/code-sandbox/scratch/mg-qa-tfvalidate")


def _find_terraform_bin() -> str:
    candidates = [
        Path("/usr/local/google/home/shankyram/workspace/code-sandbox/tools/terraform-1.17.1/terraform"),
        Path.home() / ".local" / "bin" / "terraform",
    ]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    which_tf = shutil.which("terraform")
    if which_tf:
        return which_tf
    pytest.fail("Terraform binary not found in workspace tools, ~/.local/bin, or PATH")


def _read_all_tf(stack_dir: Path) -> str:
    parts: list[str] = []
    for tf_file in sorted(stack_dir.glob("*.tf")):
        parts.append(tf_file.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_gitignore_and_shell_entrypoints_hygiene() -> None:
    gitignore = MG_ROOT / ".gitignore"
    assert gitignore.is_file(), f"Missing {gitignore}"
    gi_text = gitignore.read_text(encoding="utf-8")
    for pattern in (
        "uv.lock",
        "initialize.env",
        "*.status",
        "logs/",
        "state/",
        ".terraform/",
        "*.tfstate*",
        ".pytest_cache/",
        "__pycache__/",
    ):
        assert pattern in gi_text, f".gitignore must ignore {pattern!r}"

    env_example = MG_ROOT / "initialize.env.example"
    assert env_example.is_file(), f"Missing {env_example}"

    for script_path in (MG_ROOT / "initialize.sh", TF_ROOT / "run.sh"):
        assert script_path.is_file(), f"Missing script {script_path}"
        assert os.access(script_path, os.X_OK), f"{script_path} must be executable (chmod +x)"
        res = subprocess.run(
            ["bash", "-n", str(script_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, f"bash -n failed for {script_path}:\n{res.stderr}"

    # Verify zero unintended .terraform/ or *.tfstate* directories/files inside repo terraform/
    dirty_tf_dirs = list(TF_ROOT.rglob(".terraform"))
    assert not dirty_tf_dirs, f"Dirty .terraform directories left inside repo: {dirty_tf_dirs}"
    dirty_states = list(TF_ROOT.rglob("*.tfstate*"))
    assert not dirty_states, f"Dirty tfstate files left inside repo: {dirty_states}"


@pytest.mark.parametrize("stack", EXPECTED_STACKS)
def test_terraform_fmt_check(stack: str) -> None:
    tf_bin = _find_terraform_bin()
    stack_dir = TF_ROOT / stack
    assert stack_dir.is_dir(), f"Missing Terraform stack directory: {stack_dir}"
    tf_files = list(stack_dir.glob("*.tf"))
    assert tf_files, f"No .tf files found in {stack_dir}"

    res = subprocess.run(
        [tf_bin, "fmt", "-check", "-diff", "-no-color"],
        cwd=stack_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, (
        f"terraform fmt -check failed in {stack}:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    )


def test_terraform_architectural_contracts() -> None:
    # 01-folder-guardrails: Deny v2 rules must NOT deny run.googleapis.com/services.create or services.delete
    tf_01 = _read_all_tf(TF_ROOT / "01-folder-guardrails")
    assert "run.googleapis.com/services.create" not in tf_01
    assert "run.googleapis.com/services.delete" not in tf_01
    for required_deny in (
        "storage.googleapis.com/buckets.create",
        "storage.googleapis.com/buckets.delete",
        "cloudsql.googleapis.com/instances.create",
        "cloudsql.googleapis.com/instances.delete",
        "datastore.googleapis.com/databases.create",
        "datastore.googleapis.com/databases.delete",
        "discoveryengine.googleapis.com/dataStores.create",
        "discoveryengine.googleapis.com/dataStores.delete",
        "discoveryengine.googleapis.com/engines.create",
        "discoveryengine.googleapis.com/engines.delete",
        "iam.googleapis.com/serviceAccounts.delete",
        "run.googleapis.com/jobs.create",
        "run.googleapis.com/jobs.delete",
    ):
        assert required_deny in tf_01, f"01-folder-guardrails missing denied permission {required_deny}"

    # 02-shard-project-baseline: all 9 custom roles must be defined
    tf_02 = _read_all_tf(TF_ROOT / "02-shard-project-baseline")
    for role_id in EXPECTED_CUSTOM_ROLES:
        assert role_id in tf_02, f"02-shard-project-baseline missing custom role {role_id}"

    # 03-cloud-run-auto-owner: LONG-RUNNING comment, 20m timeout, 60s ack deadline, v1+v2 CreateService
    tf_03 = _read_all_tf(TF_ROOT / "03-cloud-run-auto-owner")
    assert "LONG-RUNNING" in tf_03, "03-cloud-run-auto-owner must flag Eventarc with # LONG-RUNNING"
    assert "20m" in tf_03, "03-cloud-run-auto-owner must specify 20m Eventarc timeout"
    assert "google.cloud.run.v1.Services.CreateService" in tf_03
    assert "google.cloud.run.v2.Services.CreateService" in tf_03
    assert (TF_ROOT / "03-cloud-run-auto-owner" / "auto_owner.py").is_file()

    # 04-shared-cloud-sql: LONG-RUNNING comment, 45m timeout, IAM auth flag, ENCRYPTED_ONLY
    tf_04 = _read_all_tf(TF_ROOT / "04-shared-cloud-sql")
    assert "LONG-RUNNING" in tf_04, "04-shared-cloud-sql must flag SQL instance with # LONG-RUNNING"
    assert "45m" in tf_04, "04-shared-cloud-sql must specify 45m SQL timeout"
    assert "cloudsql.iam_authentication" in tf_04
    assert "ENCRYPTED_ONLY" in tf_04


def _sync_stack_to_scratch(src_dir: Path, dst_dir: Path) -> None:
    """Mirror stack source files into scratch without touching repo or wiping cached .terraform/."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    keep_names = {".terraform", ".terraform.lock.hcl"}

    src_entries = {p.name: p for p in src_dir.iterdir() if not p.name.startswith(".terraform")}
    for existing in list(dst_dir.iterdir()):
        if existing.name in keep_names:
            continue
        if existing.name not in src_entries:
            if existing.is_dir():
                shutil.rmtree(existing)
            else:
                existing.unlink()

    for name, src_item in src_entries.items():
        target = dst_dir / name
        if src_item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(src_item, target)
        else:
            shutil.copy2(src_item, target)


def _validate_single_stack(stack: str) -> subprocess.CompletedProcess[str]:
    tf_bin = _find_terraform_bin()
    src_dir = TF_ROOT / stack
    assert src_dir.is_dir(), f"Missing stack directory: {src_dir}"

    work_dir = SCRATCH_VALIDATE_ROOT / stack
    _sync_stack_to_scratch(src_dir, work_dir)

    env = os.environ.copy()
    env["TF_IN_AUTOMATION"] = "1"
    env.pop("TF_PLUGIN_CACHE_DIR", None)

    if not (work_dir / ".terraform" / "providers").is_dir():
        init_res = subprocess.run(
            [tf_bin, "init", "-backend=false", "-input=false", "-no-color"],
            cwd=work_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert init_res.returncode == 0, (
            f"terraform init -backend=false failed in {stack}:\n"
            f"STDOUT:\n{init_res.stdout}\nSTDERR:\n{init_res.stderr}"
        )

    val_res = subprocess.run(
        [tf_bin, "validate", "-no-color"],
        cwd=work_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if val_res.returncode != 0 and "terraform init" in (val_res.stdout + val_res.stderr):
        reinit = subprocess.run(
            [tf_bin, "init", "-backend=false", "-input=false", "-upgrade", "-no-color"],
            cwd=work_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert reinit.returncode == 0, (
            f"terraform init -upgrade failed in {stack}:\nSTDOUT:\n{reinit.stdout}\nSTDERR:\n{reinit.stderr}"
        )
        val_res = subprocess.run(
            [tf_bin, "validate", "-no-color"],
            cwd=work_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    return val_res


@pytest.fixture(scope="module")
def parallel_validate_results() -> dict[str, subprocess.CompletedProcess[str]]:
    """Run terraform validate across all 4 stacks concurrently to stay well under <5s."""
    with ThreadPoolExecutor(max_workers=len(EXPECTED_STACKS)) as pool:
        futures = {stack: pool.submit(_validate_single_stack, stack) for stack in EXPECTED_STACKS}
        return {stack: fut.result() for stack, fut in futures.items()}


@pytest.mark.parametrize("stack", EXPECTED_STACKS)
def test_terraform_validate(
    stack: str,
    parallel_validate_results: dict[str, subprocess.CompletedProcess[str]],
) -> None:
    val_res = parallel_validate_results[stack]
    assert val_res.returncode == 0, (
        f"terraform validate failed in {stack}:\nSTDOUT:\n{val_res.stdout}\nSTDERR:\n{val_res.stderr}"
    )
