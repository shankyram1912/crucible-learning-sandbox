# BU Admin (School Admin & Cohort Admin) Operational API Domain (`tdd-apis-bu-admin.md`)

> **Domain Master:** [tdd-apis-master.md](tdd-apis-master.md)  
> **Route Prefix:** `/api/v1/bu-admin`  
> **Required Persona:** `School Admin` (for Sub-folder CRUD & Admin delegation) or `Cohort Admin` (for Cohort, `CohortConfig`, Shard & Student operations — **all School Admins are Cohort Admins by default**).

---

## 1. Department Sub-folder & Cohort Admin Delegation Endpoints (`CUJ-BU-01` .. `CUJ-BU-03`)

| Method & Path | Minimum Role | Description & Connected Pipeline |
| :--- | :--- | :--- |
| `GET /api/v1/bu-admin/schools/{school_slug}/subfolders` | `School Admin` / `Cohort Admin` | Lists Department Sub-folders under `{school_slug}` (lazily reconciling any in-flight `active_cloud_build_id`). |
| `POST /api/v1/bu-admin/schools/{school_slug}/subfolders?simulate=bool` | `School Admin` | Creates `/subfolders/{school}__{subfolder}` and triggers Cloud Build Terraform (`subfolder` module) to provision the GCP Folder and optional Pooled Sub-folder Budget (`202 Accepted`). |
| `PATCH /api/v1/bu-admin/schools/{school_slug}/subfolders/{subfolder_slug}?simulate=bool` | `School Admin` | Updates Sub-folder budget or delegated `cohort_admin_principals` and triggers Cloud Build Terraform (`subfolder` module). |
| `DELETE /api/v1/bu-admin/schools/{school_slug}/subfolders/{subfolder_slug}?simulate=bool` | `School Admin` | Verifies `0` active Cohorts exist under the Sub-folder and triggers Cloud Build `terraform destroy` (`subfolder` module). |
| `PUT /api/v1/bu-admin/cohorts/{cohort_slug}/admins` | `School Admin` | Assigns or updates additional `cohort_admin_principals` scoped to a specific Cohort Folder. |

---

## 2. Cohort & Version-Tracked `CohortConfig` Endpoints (`CUJ-BU-04`, `CUJ-BU-05`, `CUJ-BU-07`, `CUJ-BU-09`)

| Method & Path | Description & Connected Pipeline |
| :--- | :--- |
| `GET /api/v1/bu-admin/cohorts` | Lists all Cohorts within the caller's `School Admin` or `Cohort Admin` scope. Lazily reconciles `active_cloud_build_id` via `cloudbuild.builds.get()` if `status in {"PROVISIONING", "UPDATING", "TEARING_DOWN"}`. |
| `GET /api/v1/bu-admin/cohorts/{cohort_slug}` | Returns the Cohort document (`latest_config_version_id`, `applied_config_version_id`, `active_provisioning_project_id`, `current_config`) plus all child `ProjectShard` documents (`/cohorts/{cohort_slug}/shards/*`). |
| `GET /api/v1/bu-admin/cohorts/{cohort_slug}/config/versions` | Lists the immutable `CohortConfigVersion` history (`/cohorts/{cohort_slug}/config_versions/{v1..vN}`) so the Cohort Admin can inspect every config change over time. |
| `POST /api/v1/bu-admin/cohorts?simulate=bool` | **Create Cohort (`CohortConfig v1`):**<br>1. Pins `based_on_global_config_version` to `/global_config/current.latest_version_id`.<br>2. Validates `student_group_emails[]`, $N$ students ($\rightarrow K = \lceil N/100 \rceil$ shards `<cohort_slug>-p01..pKK`), mandatory `service_account = true`, and prerequisite rules from `ServiceCatalog`.<br>3. Sets `active_provisioning_project_id = "<cohort_slug>-p01"`, `latest_config_version_id = "v1"`, `applied_config_version_id = null`, `status = "PROVISIONING"`.<br>4. Uploads `v1.tfvars.json` to GCS and triggers **Cloud Build Terraform (`buadmin/cohort`)** (`202 Accepted`). |
| `PUT /api/v1/bu-admin/cohorts/{cohort_slug}/config?simulate=bool` | **Update Cohort Config (`CohortConfig v{N+1}`):**<br>1. Enforces non-destructive rules: `provisioned_project_services` is the additive union of `v{N}.provisioned_project_services` and `v{N+1}.policy_enabled_services`; lowering `per_student_quantities` or disabling a service in `policy_enabled_services` never deletes existing student resources.<br>2. Writes immutable `/config_versions/v{N+1}`, sets `latest_config_version_id = "v{N+1}"`, keeps `applied_config_version_id = "v{N}"`, and sets `status = "UPDATING"`.<br>3. If infrastructure inputs changed (shard count $K$, newly enabled project services, `student_group_emails[]`, or budgets), uploads `v{N+1}.tfvars.json` and triggers **Cloud Build Terraform (`buadmin/cohort`)** (`202 Accepted`); if only forward-looking `per_student_quantities` changed, marks `applied_config_version_id = "v{N+1}"` and `status = "READY"` immediately (`200 OK`). |
| `POST /api/v1/bu-admin/cohorts/{cohort_slug}/resync?simulate=bool` | **Resync Users & Trigger Cohort Terraform:** Re-validates `student_group_emails[]` bindings and re-runs/reconciles the Cohort Cloud Build Terraform pipeline (with auto `force-unlock` if the previous build failed). |
| `PATCH /api/v1/bu-admin/cohorts/{cohort_slug}/active-project` | **Switch Active Provisioning Project:** Validates that the target `project_id` belongs to `{cohort_slug}` and has `remaining_capacity > 0` (`initialized_student_count < 100`), then updates `Cohort.active_provisioning_project_id` and records a new `CohortConfig` version. |
| `PATCH /api/v1/bu-admin/cohorts/{cohort_slug}/projects/{project_id}/budget?simulate=bool` | Sets or updates a per-project spend limit override in `CohortConfig` (`v{N+1}`) and triggers Cloud Build Terraform to update that shard's `google_billing_budget`. |
| `POST /api/v1/bu-admin/cohorts/{cohort_slug}/teardown?simulate=bool` | **Cohort Teardown:** Sets `status = "TEARING_DOWN"` and triggers Cloud Build `terraform destroy` (`_ACTION=DESTROY`) on `buadmin/cohort-<cohort_slug>` to destroy all `<cohort_slug>-p01..pKK` shards, shared Cloud SQL instances, and the Cohort Folder (`202 Accepted`). |

---

## 3. Student Slice Governance Endpoints (`CUJ-BU-06`, `CUJ-BU-08`)

| Method & Path | Description & Connected Pipeline |
| :--- | :--- |
| `GET /api/v1/bu-admin/cohorts/{cohort_slug}/students?q=...&project_id=...` | Searches or lists `StudentSlice` documents across the Cohort's shards, returning each student's `assigned_project_id`, `status`, `singletons`, and `usage_counters`. |
| `POST /api/v1/bu-admin/cohorts/{cohort_slug}/students/{student_slug}/suspend?simulate=bool` | Invokes **Atomic Pipeline (`SUSPEND_STUDENT`)** to revoke `user:<student_email>` access while keeping their singletons and `app-<app_slug>` containers intact (`status = "SUSPENDED"`). |
| `POST /api/v1/bu-admin/cohorts/{cohort_slug}/students/{student_slug}/unsuspend?simulate=bool` | Invokes **Atomic Pipeline (`UNSUSPEND_STUDENT`)** to restore `user:<student_email>` IAM bindings and DB login (`status = "ACTIVE"`). |
| `DELETE /api/v1/bu-admin/cohorts/{cohort_slug}/students/{student_slug}?simulate=bool` | Invokes **Atomic Pipeline (`DELETE_STUDENT_SLICE`)** to tear down all of the student's `AppContainer`s and Student-Level Singletons (`db_<student_sql_slug>`, `bkt-...`, `sa-<student_slug>`) and decrement `initialized_student_count` (`-1`) on their assigned Project Shard. |
