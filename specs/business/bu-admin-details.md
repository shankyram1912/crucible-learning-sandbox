# BU Admin — Secondary Implementation Details (THE HOW)

> **Parent Document:** [01 — Business & Functional Specification](../01-business-spec.md)  
> **Companion CUJ Document:** [BU Admin CUJs (WHY)](bu-admin-cuj.md)  
> **Terraform Source Location:** `src/terraform/buadmin/`

---

## 1. Cohort Sharding & Project Naming Math

1. **Parent Folder Flexibility:** A Cohort Folder (`google_folder.cohort`) takes `parent_folder_id`, which can be either a **School Folder** (`folders/<school_id>`) or a **Department Sub-folder** (`folders/<subfolder_id>`).
2. **Shard Count Formula:**
   $$K = \max\left(1, \left\lceil rac{N_{	ext{students}}}{100} ightceilight)$$
3. **Deterministic Project Shard Naming:**
   * Each shard $i \in \{1 \dots K\}$ is named:
     $$	ext{project\_id}_i = 	exttt{<cohort\_slug>-p}\langle	ext{zero-padded } iangle \quad (	ext{e.g., } 	exttt{cs101-fall-p01})$$

---

## 2. Terraform State Isolation for BU Admin (`src/terraform/buadmin`)

Each Cohort has its own isolated Terraform state file in the Control Tower state bucket so initializing, resizing, or tearing down a Cohort (`terraform destroy`) never touches parent School/Department folders or sibling Cohorts:

```text
gs://<control-tower-tfstate-bucket>/buadmin/cohort-<cohort_slug>/default.tfstate
```

### Input `.tfvars.json` Compiled from BU Admin Intent
```json
{
  "parent_folder_id": "folders/100000000201",
  "cohort_slug": "cs101-fall",
  "cohort_display_name": "CS101 Fall 2026",
  "expected_student_count": 350,
  "shard_count": 4,
  "billing_account_id": "012345-6789AB-CDEF01",
  "currency_code": "USD",
  "region": "asia-southeast1",
  "cohort_budget_amount": 8000,
  "default_project_limit": 3000,
  "project_limit_overrides": {
    "cs101-fall-p02": 5000
  },
  "control_tower_budget_pubsub_topic": "projects/ct-prod/topics/sandbox-budget-events",
  "default_enabled_services": {
    "gemini": true,
    "gcs": true,
    "cloud_run": true,
    "vertex_search": true,
    "cloud_sql": true
  },
  "per_project_service_overrides": {}
}
```

---

## 3. What `src/terraform/buadmin` Initializes Inside Each Project Shard

For each project shard (`<cohort_slug>-p01..pKK`), the BU Admin Terraform module provisions:

1. **GCP Project & Billing Attachment:** Creates `google_project` under `google_folder.cohort` with `billing_account = var.billing_account_id` and labels `{ cohort = var.cohort_slug, managed_by = "learning-sandbox" }`.
2. **Baseline & Conditional APIs (`google_project_service`):**
   * Always enabled: `aiplatform.googleapis.com`, `iam.googleapis.com`, `cloudresourcemanager.googleapis.com`, `serviceusage.googleapis.com`, `logging.googleapis.com`, `monitoring.googleapis.com`.
   * If `gcs == true`: `storage.googleapis.com`.
   * If `cloud_run == true`: `run.googleapis.com`, `artifactregistry.googleapis.com`, `cloudbuild.googleapis.com` + a shared **Artifact Registry Docker Repository** (`ar-<project_id>`) so students can build/push container images for their Cloud Run service.
   * If `vertex_search == true`: `discoveryengine.googleapis.com` + enables **Resource Access Control** (`data_store_access_control_enabled = true`) so students only see the Search App and Data Connector bound to their identity.
   * If `cloud_sql == true`: `sqladmin.googleapis.com` + provisions **1 Shared Cloud SQL for PostgreSQL Instance** (`sql-<project_id>`) with `cloudsql.iam_authentication = "on"` and `deletion_protection = false` (so Cohort Teardown succeeds cleanly).
3. **Project-Level Student IAM Group & Custom Usage-Only Roles:**
   * Creates/binds `grp-students-<project_id>@<domain>` with baseline project viewer/consumer permissions (`serviceusage.services.use`, `aiplatform.endpoints.predict`, `discoveryengine.agentspaceRestrictedUser`, `artifactregistry.writer`, `logging.LogsViewer`).
   * Creates custom **Usage-Only Roles** in the project (excluding `*.create`, `*.delete`, and `*.setIamPolicy` on top-level resources) that the Atomic Pipeline later binds on individual student resources (`bkt-*`, `run-*`, `ds-*`, `app-*`).
4. **Pooled Cohort Budget + Per-Project Shard Limits (with Overrides):**
   * **1 Pooled Cohort Folder Budget** (`resource_ancestors = ["folders/${google_folder.cohort.folder_id}"]`, amount = `var.cohort_budget_amount`).
   * **$K$ Project Shard Limit Budgets** (`projects = ["projects/${each.value.number}"]`, amount = `lookup(var.project_limit_overrides, each.key, var.default_project_limit)`).

---

## 4. What Happens During Student Mapping to a Cohort (Atomic Roster Pipeline)

When the BU Admin maps Cloud Identity Users, User Groups, or a CSV list to a Cohort:
1. **Group Expansion & Normalization:** Resolves Cloud Identity groups/users to individual student emails and computes each student's `student_slug` (email prefix before `@`, e.g., `alice.tan@school.edu` $ightarrow$ `alice-tan`).
2. **Shard Bin-Packing ($\le 100$ students / project):** Assigns each student to the first shard `<cohort_slug>-pNN` with `< 100` assigned students (idempotent if the student is already assigned to that Cohort).
3. **Automatic Student Service Account Creation:**
   * Creates `sa-<student_slug>@<project_id>.iam.gserviceaccount.com` in the assigned shard.
   * Binds `roles/iam.serviceAccountUser` (`iam.serviceAccounts.actAs`) on `sa-<student_slug>` to `user:<student_email>` (so the student can deploy Cloud Run revisions using `sa-<student_slug>`).
   * Binds `roles/aiplatform.user` to `serviceAccount:sa-<student_slug>@...` so the student's workloads can call **Gemini** out of the box.
4. **Multi-Cohort Support in Firebase DB:** Stores the membership under `/environments/{mode}/students/{student_email}/cohorts/{cohort_slug}` so a student in multiple cohorts has an independent `project_id` and `sa-<student_slug>` per cohort.

---

## 5. Cohort Teardown Sequence
When the BU Admin triggers **Cohort Teardown**:
1. Acquires `locks/cohort_<cohort_slug>`.
2. Runs `terraform destroy -auto-approve` on `gs://<ct-tfstate>/buadmin/cohort-<cohort_slug>/default.tfstate` (which destroys all `<cohort_slug>-p01..pNN` projects, shared Cloud SQL instances, student resources inside those projects, budgets, and the Cohort Folder).
3. Archives/removes the Cohort and its project shard assignments from Firebase DB.
