# BU Admin (School Admin & Cohort Admin) — Secondary Implementation Details (`THE HOW`)

> **Master Document:** [Business Requirements Specification — Master (`THE WHAT`)](../01-brs/brs-master.md)
> **TDD Master Document:** [Technical Design & LLD — Master](tdd-master.md)  
> **Companion CUJ Document:** [BU Admin CUJs (`THE WHY`)](../01-brs/sub-bu-admin-cuj.md)  
> **Terraform Source Location:** `src/terraform/buadmin/`

---

## 1. Two-Tier BU Admin Delegation & Terraform State Isolation

**All BU Admins are by default Cohort Admins** within their delegated scope:
1. **Top-Level School Admin Scope (Delegated by IT Admin at `folders/<school_folder_id>`):**
   * Holds full **Cohort Admin** rights across the entire School Folder by default.
   * Creates, updates, and decommissions **Department Sub-folders** (`google_folder` with `parent = "folders/${school_folder_id}"`) and optional **Pooled Sub-folder Budgets** (`resource_ancestors = ["folders/${subfolder_id}"]`).
   * Can assign additional **Cohort Admins** (`cohort_admin_principals` — Users or Cloud Identity Groups) at either:
     * **Department Sub-folder level (`folders/<subfolder_id>`)**: Grants Cohort Admin rights over all Cohorts inside that Sub-folder.
     * **Cohort Folder level (`folders/<cohort_folder_id>`)**: Grants Cohort Admin rights restricted to that single Cohort.
   * **Isolated Sub-folder Terraform State:**
     ```text
     gs://<control-tower-tfstate-bucket>/buadmin/subfolder-<school_slug>-<subfolder_slug>/default.tfstate
     ```
2. **Cohort Admin Scope (Default for all BU Admins, or Delegated at Sub-folder / Cohort level):**
   * Manages Cohort initialization, service toggles (with mandatory `Service Account` locked ON and automatic prerequisite enforcement), per-student quantity overrides, mapping the **Cohort Student Email Group**, managing/switching the Cohort's **Current Active Provisioning Project (`active_provisioning_project_id`)**, student suspension or slice deletion, project shard spend limit overrides, student search/support, and Cohort Teardown.
   * **Isolated Cohort Terraform State:**
     ```text
     gs://<control-tower-tfstate-bucket>/buadmin/cohort-<cohort_slug>/default.tfstate
     ```

---

## 2. Cohort Sharding Math, Active Provisioning Project Pointer & Config Version Pinning

1. **Config Version Pinning:** When a Cohort is created, it snapshots `config_version = v{N}` from `/environments/{mode}/global_config/meta.active_version`. All underlying `service_sizes` (e.g., Cloud SQL tier, Cloud Run CPU/memory limits), prerequisite rules, and default `min` quantities are inherited from `v{N}` so future global config edits by IT Admin do not mutate existing Cohorts.
2. **Service Catalog Prerequisite Resolution:**
   * `service_account` has `requirement = "MANDATORY"` and is always locked ON for every Cohort.
   * Each optional service declares `prerequisites` in the Service Catalog Config (e.g., `vertex_search` requires `["service_account", "gcs"]`). Enabling a service on a Cohort automatically enables all of its prerequisites.
3. **Shard Count Formula (Default `100` Students per Project Shard):**
   $$K = \max\left(1, \left\lceil \frac{N_{\text{students}}}{S_{\text{shard}}} \right\rceil\right) \quad \text{where default } S_{\text{shard}} = 100$$
4. **Deterministic Project Shard Naming:**
   * Each shard $i \in \{1 \dots K\}$ is named:
     $$\text{project\_id}_i = \texttt{<cohort\_slug>-p}\langle\text{zero-padded } i\rangle \quad (\text{e.g., } \texttt{cs101-fall-p01})$$
5. **Current Active Provisioning Project (`active_provisioning_project_id`):**
   * Stored on the Cohort document in Firebase DB (`/environments/{mode}/cohorts/{cohort_slug}.active_provisioning_project_id`), initialized to `<cohort_slug>-p01`.
   * Tracks `initialized_student_count` and `remaining_capacity = students_per_project - initialized_student_count` on each shard (`<cohort_slug>-p01..pKK`).
   * **Automatic Capacity Rollover:** When a student enters the Cohort workspace and is initialized into `active_provisioning_project_id`, if that shard's `remaining_capacity` reaches `0`, the BFF transactionally advances `active_provisioning_project_id` to the next shard in `<cohort_slug>-p01..pKK` with `remaining_capacity > 0`.
   * **Manual Admin Override:** A Cohort Admin (or School Admin) can manually switch `active_provisioning_project_id` to any shard in `<cohort_slug>-p01..pKK` that has `remaining_capacity > 0` at any time (e.g., to balance spend across shards).

---

## 3. Cohort Student Email Group Mapping & Non-Destructive Service Toggles

### A. Cohort Student Email Group Mapping
* Instead of maintaining per-student resources inside Terraform, the Cohort Admin maps one or more **Cohort Student Email Groups** (e.g., `grp-cs101-students@school.edu`) to the Cohort.
* Cohort Terraform (`src/terraform/buadmin`) binds baseline project-level viewer/consumer roles to `group:grp-cs101-students@school.edu` across the Cohort's `<cohort_slug>-p01..pKK` shards, while each individual student's **Student-Level Singletons** (`sa-<student_slug>`, `bkt-<project_id>-<student_slug>`, `db_<student_slug>`) are auto-initialized just-in-time via the Atomic Pipeline when the student enters the Cohort workspace (`sub-student-details.md`).

### B. Non-Destructive Service Disable & Quantity Reduction
1. **`policy_enabled_services` & `per_student_quantities` (Forward-Looking Policy Gate):**
   * Controls which services are auto-initialized for students entering the Cohort workspace and what per-student quantity (`min` from Service Catalog Config + Cohort override) is enforced when students create new App-level resources (`deployed_count < per_student_quantity`).
   * Lowering `per_student_quantity` or setting `policy_enabled_services.<svc> = false` updates only the policy gate — **existing student resources deployed in excess of the new quantity are never deleted**.
2. **`provisioned_project_services` (Additive Union Compiled into Cohort `.tfvars.json`):**
   * Whenever a project-level service (such as `cloud_sql` for the shared `sql-<project_id>` instance) is enabled on a Cohort, it is added to `provisioned_project_services` and provisioned via Cohort Terraform.
   * Disabling the service later in the UI **never removes** it from `provisioned_project_services`, ensuring `terraform apply` never destroys shared project infrastructure (`sql-<project_id>`, `ar-<project_id>`) until **Cohort Teardown** (`terraform destroy`).

---

## 4. Input `.tfvars.json` Compiled for Cohort Terraform (`src/terraform/buadmin`)

Because Student-Level Singletons are auto-initialized when a student enters the Cohort workspace, Cohort Terraform (`src/terraform/buadmin`) stays strictly focused on the **Cohort Folder** and the **$K$ Project Shards**:

```json
{
  "parent_folder_id": "folders/100000000201",
  "cohort_slug": "cs101-fall",
  "cohort_display_name": "CS101 Fall 2026",
  "pinned_config_version": 1,
  "expected_student_count": 350,
  "students_per_project": 100,
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
  "cohort_admin_principals": [
    "group:grp-cohort-admin-cs101@domain.edu"
  ],
  "cohort_student_groups": [
    "group:grp-cs101-students@school.edu"
  ],
  "provisioned_project_services": {
    "service_account": true,
    "gemini": true,
    "gcs": true,
    "cloud_sql": true,
    "cloud_run": true,
    "vertex_search": true
  },
  "service_sizes": {
    "cloud_sql_tier": "db-custom-2-7680",
    "cloud_sql_disk_gb": 50,
    "cloud_run_cpu": "1000m",
    "cloud_run_memory": "512Mi"
  }
}
```

---

## 5. What Cohort Terraform (`src/terraform/buadmin`) Provisions in Each Project Shard

For each project shard (`<cohort_slug>-p01..pKK`):
1. **GCP Project & Billing Attachment:** `google_project` under `google_folder.cohort` with `billing_account = var.billing_account_id`.
2. **Project APIs & Shared Infrastructure (from `provisioned_project_services` & `service_sizes`):**
   * **Service Account & Core IAM (Mandatory):** `iam.googleapis.com`, `cloudresourcemanager.googleapis.com`, `serviceusage.googleapis.com`, `logging.googleapis.com`, `monitoring.googleapis.com`.
   * **Gemini:** `aiplatform.googleapis.com`.
   * **GCS:** `storage.googleapis.com`.
   * **Cloud SQL:** `sqladmin.googleapis.com` + **1 Shared Cloud SQL for PostgreSQL Instance** (`sql-<project_id>`) sized per `service_sizes.cloud_sql_tier`, with `cloudsql.iam_authentication = "on"` and `deletion_protection = false`.
   * **Cloud Run:** `run.googleapis.com`, `artifactregistry.googleapis.com`, `cloudbuild.googleapis.com` + shared **Artifact Registry Docker Repository** (`ar-<project_id>`).
   * **Vertex AI Search:** `discoveryengine.googleapis.com` + Resource Access Control enabled.
3. **Cohort Student Group Baseline & Custom Usage-Only Roles:**
   * Binds `cohort_student_groups` to baseline project viewer/consumer roles (`serviceusage.services.use`, `aiplatform.endpoints.predict` if Gemini enabled, `discoveryengine.agentspaceRestrictedUser`, `artifactregistry.writer`, `logging.LogsViewer`, `cloudsql.client`, `cloudsql.instanceUser`).
   * Provisions project-level custom **Usage-Only Roles** (for Cloud Run and Vertex AI Search) that the Atomic Pipeline later binds to individual student resources.
4. **Pooled Cohort Budget + Per-Project Shard Limit Budgets:**
   * **1 Pooled Cohort Folder Budget** (`resource_ancestors = ["folders/${google_folder.cohort.folder_id}"]`, amount = `var.cohort_budget_amount`).
   * **$K$ Project Shard Limit Budgets** (`projects = ["projects/${each.value.number}"]`, amount = `lookup(var.project_limit_overrides, each.key, var.default_project_limit)`).

---

## 6. Suspend Student vs. Delete Student Slice

1. **Suspend Student (`SUSPEND_STUDENT`):**
   * Sets `status = "SUSPENDED"` on the student's slice in Firebase DB and removes `user:<student_email>` from their Student-Level Singleton and App resource IAM bindings (while keeping `sa-<student_slug>`, `bkt-<project_id>-<student_slug>`, `db_<student_slug>`, and all `app-<app_slug>` resources intact).
   * Reversible via `UNSUSPEND_STUDENT`.
2. **Delete Student Slice (`DELETE_STUDENT_SLICE`):**
   * Runs the Atomic Pipeline teardown to destroy all of the student's App Containers (`app-<app_slug>`) and their Student-Level Singletons (`db_<student_slug>`, `bkt-<project_id>-<student_slug>`, `sa-<student_slug>`), removes the student's record from the Cohort shard in Firebase DB, and increments the shard's `remaining_capacity` by `1`.

---

## 7. Single-Action Lock Matrix for BU Admin (School & Cohort Admin) Operations

| Operation | Lock Document in Firebase DB | Lock Lease TTL | Blocked Concurrent Actors |
| :--- | :--- | :--- | :--- |
| **Create / Update / Delete Department Sub-folder** | `locks/subfolder_<school_slug>_<subfolder_slug>` | 5 minutes | Other School Admins mutating that specific Department Sub-folder |
| **Create / Resize / Edit Services / Map Student Email Group / Switch Active Provisioning Project / Teardown Cohort** | `locks/cohort_<cohort_slug>` | 10 minutes | Concurrent Cohort-level mutations on that specific Cohort |
| **Suspend Student or Delete Student Slice** | `locks/student_<student_slug>_<project_id>` | 2 minutes | Concurrent mutations on that specific student's slice |
