# Async Execution Pipelines — Master (`tdd-pipelines-master.md`)

> **Parent TDD Master:** [../tdd-master.md](../tdd-master.md)  
> **Domain Sub-Specs:**
> * [tdd-pipelines-cloud-build-terraform.md](tdd-pipelines-cloud-build-terraform.md) — Cloud Build Terraform Runner (`itadmin`, `subfolder`, `cohort`, and `destroy`), Failure Modes, Stale `.tflock` Recovery & Lazy Poll Reconciliation
> * [tdd-pipelines-atomic-runner.md](tdd-pipelines-atomic-runner.md) — Direct Python GCP SDK / SQL Runner for `<15s` JIT Student Workspace Initialization, App Container CRUD & Student Offboarding

---

## 1. Dual-Pipeline Architecture Overview

The Learning Sandbox separates execution into two specialized pipeline engines based on resource scope and latency requirements:

| Pipeline Engine | Target Operations | Execution Runtime | Typical Latency | Concurrency & State Guard |
| :--- | :--- | :--- | :--- | :--- |
| **1. Cloud Build Terraform Pipeline** ([tdd-pipelines-cloud-build-terraform.md](tdd-pipelines-cloud-build-terraform.md)) | • Create/Update/Delete School Folder (`itadmin`)<br>• Create/Update/Delete Department Sub-folder (`subfolder`)<br>• Create/Update/Resize Cohort & Project Shards (`cohort`)<br>• Cohort Teardown (`terraform destroy`) | **Google Cloud Build** (`cloudbuild.projects.builds.create` running `hashicorp/terraform` as `sa-control-tower`) | `45s` (folders) to `6–10m` (shards with Shared Cloud SQL) | Native **GCS `.tflock`** on `default.tfstate` + `active_cloud_build_id` on entity doc |
| **2. Atomic Python SDK / SQL Pipeline** ([tdd-pipelines-atomic-runner.md](tdd-pipelines-atomic-runner.md)) | • JIT Student Workspace Initialization on Cohort Entry (`sa-<student_slug>`, `Gemini`, `bkt-...`, `db_<student_sql_slug>`)<br>• App Container (`app-<app_slug>`) & App Service `CREATE` / `DELETE`<br>• Suspend Student / Delete Student Slice | **In-Process Async Python Task** inside FastAPI BFF (using `google-cloud-*` SDKs + `asyncpg` as `sa-control-tower`) | `2s – 15s` | Per-Student Firestore transactional status (`status = "INITIALIZING" \| "UPDATING"`) |

---

## 2. Request-Level `simulate: bool` Pass-Through Flag

Every mutating API request accepts a `simulate: bool = false` flag (via query parameter `?simulate=true` or request body) and passes it straight down to the invoked pipeline:

1. **In the Cloud Build Terraform Pipeline (`simulate=true`):**
   * Compiles the real `<version_id>.tfvars.json` and uploads it to GCS.
   * Either triggers a lightweight Cloud Build validation step (`terraform init -backend=false && terraform validate`) **or** synthesizes deterministic output payloads (`school_folder_id`, `shard_project_ids`, `sql-<project_id>`) directly into Firestore so the full version-tracking and UI polling flow can be tested in seconds without waiting 8 minutes for Cloud SQL creation.
2. **In the Atomic Python Pipeline (`simulate=true`):**
   * Executes the exact same Firestore transactions, shard capacity rollover math, and per-student allowance gate checks, while mocking the external GCP SDK / PostgreSQL DDL calls and writing deterministic resource metadata into the `StudentSlice` and `AppServiceInstance` documents.
