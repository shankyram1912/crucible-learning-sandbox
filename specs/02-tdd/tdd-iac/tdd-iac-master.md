# Infrastructure-as-Code (Terraform) — Master (`tdd-iac-master.md`)

> **Parent TDD Master:** [../tdd-master.md](../tdd-master.md)  
> **Domain Sub-Specs:**
> * [tdd-iac-bootstrap.md](tdd-iac-bootstrap.md) — Day-0 Control Tower Project, Automation SA (`sa-control-tower`), GCS State Bucket & Cloud Build Setup
> * [tdd-iac-itadmin-school.md](tdd-iac-itadmin-school.md) — Top-Level School Folders, School Admin IAM Bindings & Pooled School Budgets (`src/terraform/itadmin`)
> * [tdd-iac-buadmin-subfolder-and-cohort.md](tdd-iac-buadmin-subfolder-and-cohort.md) — Department Sub-folders, Cohort Folders, Project Shards (`<cohort_slug>-p01..pKK`), P4SA `time_sleep` Barriers & Shared Cloud SQL (`src/terraform/buadmin`)

---

## 1. Terraform Module Hierarchy & Boundary Rules

1. **`src/terraform/bootstrap/` (Day-0 One-Time Setup):**
   * Provisions the Root Sandbox Folder (`folders/<root_folder_id>`), the Control Tower GCP Project, the GCS Terraform State & `.tfvars.json` Bucket (`gs://<tfstate-bucket>`), the privileged `sa-control-tower` Service Account, and Cloud Build permissions.
2. **`src/terraform/itadmin/` (Per-School Folder State — Triggered by IT Admin via Cloud Build):**
   * Provisions a Top-Level School Folder under `folders/<root_folder_id>`, binds `school_admin_principals` (`roles/resourcemanager.folderViewer` + `roles/viewer`), and attaches a Pooled School Folder Budget (`resource_ancestors`).
3. **`src/terraform/buadmin/subfolder/` (Per-Department Sub-folder State — Triggered by School Admin via Cloud Build):**
   * Provisions a Department Sub-folder under a School Folder, binds delegated `cohort_admin_principals`, and attaches an optional Pooled Sub-folder Budget.
4. **`src/terraform/buadmin/cohort/` (Per-Cohort State — Triggered by Cohort Admin via Cloud Build):**
   * Provisions the Cohort Folder, $K = \max(1, \lceil N / 100 \rceil)$ Project Shards (`<cohort_slug>-p01..pKK`), project-level APIs, P4SA warmup + `time_sleep` barrier, Shared Cloud SQL (`sql-<project_id>`), Artifact Registry (`ar-<project_id>`), Cohort Student Group baseline IAM (`student_group_emails[]`), custom Usage-Only Roles, and Pooled Cohort + Per-Shard Budgets.
   * **Strict Boundary:** Cohort Terraform **never** loops over individual students. Individual Student-Level Singletons (`sa-<student_slug>`, `bkt-...`, `db_<student_sql_slug>`) and App Containers (`app-<app_slug>`) are provisioned just-in-time by the Atomic Python Pipeline (`tdd-pipelines-atomic-runner.md`).

---

## 2. GCS State Isolation & Atomic `.tflock` Locking (`backend "gcs"`)

Every School, Department Sub-folder, and Cohort is isolated in its own GCS state prefix inside `gs://<control-tower-tfstate-bucket>`:

| Scope | GCS State Path (`default.tfstate`) | GCS Lock File (`default.tflock`) | Compiled `.tfvars.json` Path |
| :--- | :--- | :--- | :--- |
| **School Folder** | `tfstate/itadmin/school-<school_slug>/default.tfstate` | `.../default.tflock` | `tfvars/itadmin/school-<school_slug>/latest.tfvars.json` |
| **Department Sub-folder** | `tfstate/buadmin/subfolder-<school_slug>-<subfolder_slug>/default.tfstate` | `.../default.tflock` | `tfvars/buadmin/subfolder-<school_slug>-<subfolder_slug>/latest.tfvars.json` |
| **Cohort & Project Shards** | `tfstate/buadmin/cohort-<cohort_slug>/default.tfstate` | `.../default.tflock` | `tfvars/buadmin/cohort-<cohort_slug>/<version_id>.tfvars.json` |

* **How GCS `.tflock` Works:** When Cloud Build executes `terraform apply` (or `destroy`), Terraform creates `default.tflock` in GCS using `ifGenerationMatch = 0`. If another Cloud Build run is already active on the same Cohort, GCS rejects the second lock request (`412 Precondition Failed`), guaranteeing single-writer serialization per state prefix.

---

## 3. Terraform Best Practices for Async GCP Operations

To eliminate first-run eventual consistency failures and handle long-running GCP operations cleanly within a single declarative `terraform apply`:

1. **`time_sleep` Eventual Consistency Barriers (`hashicorp/time`):**
   * Inserted between `google_project_service` / `google_project_service_identity` (P4SA generation) and downstream `google_project_iam_member` / data-plane resources (`create_duration = "30s"`), ensuring GCP IAM and Service Usage globally recognize newly enabled APIs and P4SAs before bindings are applied.
2. **Native Provider LRO Polling & Explicit `timeouts`:**
   * Long-running resources (`google_project`, `google_sql_database_instance`) rely on the `google` provider's built-in LRO polling with explicit `timeouts { create = "20m", update = "20m", delete = "20m" }` — strictly shorter than the outer Cloud Build timeout (`3600s` / `60m`) so Terraform always exits cleanly and releases `.tflock` before Cloud Build can hard-kill the worker.
3. **Clean Teardown Settings (`deletion_protection = false` & `deletion_policy = "DELETE"`):**
   * All sandbox project shards and shared Cloud SQL instances set `deletion_protection = false` and `force_destroy = true` so `terraform destroy` during **Cohort Teardown** deletes the entire project shards cleanly even when students have created dynamic buckets, Cloud Run services, or databases inside those shards.
