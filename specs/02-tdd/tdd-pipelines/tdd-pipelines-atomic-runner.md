# Atomic Python GCP SDK & SQL Pipeline (`tdd-pipelines-atomic-runner.md`)

> **Domain Master:** [tdd-pipelines-master.md](tdd-pipelines-master.md)  
> **Pipeline Source Location:** `src/bff/pipelines/atomic_runner.py`

---

## 1. Purpose & Scope

Handles all fast (`2s – 15s`), student-level and app-level mutations directly from the FastAPI BFF using `sa-control-tower` credentials, completely bypassing Terraform so student actions never block or contend with Cohort Terraform state:

1. **JIT Student Workspace Auto-Initialization (`INIT_STUDENT_WORKSPACE`):** Triggered automatically when a student enters a Cohort workspace (`CUJ-ST-01`).
2. **App Container & App Service Creation (`CREATE_APP_SERVICE`):** Triggered when an initialized student creates a `GCS_MANAGED_FOLDER`, `POSTGRES_SCHEMA`, `CLOUD_RUN_SERVICE`, or `VERTEX_SEARCH_APP` inside an `AppContainer` (`app-<app_slug>`) (`CUJ-ST-02`, `CUJ-ST-03`).
3. **App Service or Whole-App Container Deletion (`DELETE_APP_SERVICE`, `DELETE_APP_CONTAINER`):** Triggered when a student deletes an App service or entire App Container to free up their per-student allowance (`CUJ-ST-04`).
4. **BU Admin Student Governance (`SUSPEND_STUDENT`, `UNSUSPEND_STUDENT`, `DELETE_STUDENT_SLICE`):** Triggered by a Cohort Admin (`CUJ-BU-06`).

---

## 2. JIT Student Workspace Initialization Flow (`INIT_STUDENT_WORKSPACE`)

When `POST /api/v1/student/cohorts/{cohort_slug}/enter` is called for `student_email`:

1. **Verify Cohort Readiness:**
   * Check `Cohort.applied_config_version_id != null`. If `null`, return `202` with `workspace_init_status = "WAITING_FOR_COHORT_FOUNDATION"`.
   * Load the applied `CohortConfig` (`config_versions/{applied_config_version_id}`).
2. **Transactional Shard Seat Assignment (`active_provisioning_project_id`):**
   * If `/cohorts/{cohort_slug}/students/{student_slug}` does not have an `assigned_project_id`:
     * Read `Cohort.active_provisioning_project_id` (e.g., `<cohort_slug>-p01`).
     * Assign `assigned_project_id = active_provisioning_project_id` and increment `shards/{project_id}.initialized_student_count` (`+1`).
     * **Auto-Rollover Check:** If `initialized_student_count >= students_per_project` (`100`), automatically update `Cohort.active_provisioning_project_id` to the first shard in `<cohort_slug>-p01..pKK` with `remaining_capacity > 0`.
3. **Idempotent Student-Level Singleton Provisioning (Against `applied_config.policy_enabled_services`):**
   * **Step 1 — Mandatory Student Service Account (`sa-<student_slug>`):**
     * Create `sa-<student_slug>@<project_id>.iam.gserviceaccount.com` via IAM API (idempotent if exists).
     * Bind `roles/iam.serviceAccountUser` (`iam.serviceAccounts.actAs`) on `sa-<student_slug>` to `user:<student_email>`.
   * **Step 2 — Gemini Access (`if policy_enabled_services.gemini`):**
     * Bind `roles/aiplatform.user` to `serviceAccount:sa-<student_slug>@...`.
   * **Step 3 — Singleton Student GCS Bucket (`if policy_enabled_services.gcs`):**
     * Create `bkt-<project_id>-<student_slug>` with Uniform Bucket-Level Access enabled.
     * Bind `roles/storage.objectUser` on `bkt-<project_id>-<student_slug>` to `user:<student_email>` and `serviceAccount:sa-<student_slug>@...`.
   * **Step 4 — Singleton Student Logical Postgres DB (`if policy_enabled_services.cloud_sql`):**
     * Register Cloud SQL IAM users `<student_email>` (`CLOUD_IAM_USER`) and `sa-<student_slug>@...` (`CLOUD_IAM_SERVICE_ACCOUNT`) on `sql-<project_id>`.
     * Connect to `sql-<project_id>` and execute:
       ```sql
       CREATE DATABASE db_<student_sql_slug>;
       REVOKE CONNECT ON DATABASE db_<student_sql_slug> FROM PUBLIC;
       GRANT ALL PRIVILEGES ON DATABASE db_<student_sql_slug> TO "<student_email>", "sa-<student_slug>@<project_id>.iam.gserviceaccount.com";
       ALTER ROLE "<student_email>" CONNECTION LIMIT 5;
       ```
4. **Unlock App Container Creation:**
   * Set `StudentSlice.workspace_init_status = "INITIALIZED"`, `status = "ACTIVE"`, and `can_create_apps = true`.

---

## 3. App-Scoped Resource `CREATE` & `DELETE` Execution Matrix

Before creating any countable App service $s \in \{\texttt{cloud\_sql\_schemas}, \texttt{cloud\_run}, \texttt{vertex\_search}\}$, the pipeline verifies the **Pre-Flight Allowance Gate** against `Cohort.current_config`:
$$\texttt{policy\_enabled\_services}[s] == \texttt{true} \quad \land \quad \texttt{student.usage\_counters}[s] < \texttt{per\_student\_quantities}[s]$$
*(Lowering `per_student_quantities[s]` or setting `policy_enabled_services[s] = false` never deletes existing instances; it only gates new `CREATE` calls).*

| `service_type` | Atomic `CREATE` Execution Steps | Atomic `DELETE` Execution Steps (Frees Allowance) |
| :--- | :--- | :--- |
| **`GCS_MANAGED_FOLDER`**<br>*(Allowance: $\infty$)* | Calls `StorageControlClient.create_managed_folder` for `apps/<app_slug>/<folder_name>/` inside `bkt-<project_id>-<student_slug>`. | Verifies no active `VERTEX_SEARCH_APP` in `app-<app_slug>` is bound to the folder; deletes objects under prefix `apps/<app_slug>/<folder_name>/` and deletes the Managed Folder. |
| **`POSTGRES_SCHEMA`** | Connects to `sql-<project_id>/db_<student_sql_slug>`, executes `CREATE SCHEMA <app_slug>_<schema_name> AUTHORIZATION "<student_email>"; GRANT ALL ON SCHEMA <app_slug>_<schema_name> TO "sa-<student_slug>@...";`, and increments `usage_counters.cloud_sql_schemas` (`+1`). | Executes `DROP SCHEMA IF EXISTS <app_slug>_<schema_name> CASCADE;` inside `db_<student_sql_slug>` and decrements `usage_counters.cloud_sql_schemas` (`-1`). |
| **`CLOUD_RUN_SERVICE`** | Calls Cloud Run v2 `ServicesClient.create_service` for `run-<student_slug>-<app_slug>-<svc_name>` with `service_account = sa-<student_slug>@...` and CPU/memory/max-instance limits from `pinned_service_sizes`; binds `customStudentCloudRunUser` on that service to `user:<student_email>`; increments `usage_counters.cloud_run` (`+1`). | Calls `ServicesClient.delete_service` for `run-<student_slug>-<app_slug>-<svc_name>` and decrements `usage_counters.cloud_run` (`-1`). |
| **`VERTEX_SEARCH_APP`** | 1. Ensures Managed Folder `apps/<app_slug>/<name>-docs/` exists in `bkt-<project_id>-<student_slug>`.<br>2. Creates Discovery Engine Data Store `search-ds-<student_slug>-<app_slug>-<name>` synced to `gs://bkt-.../apps/<app_slug>/<name>-docs/*`.<br>3. Creates Search Engine `search-app-<student_slug>-<app_slug>-<name>` linked to the Data Store.<br>4. Calls `:setIamPolicy` on both Data Store and Engine to bind `customStudentVertexSearchUser` to `user:<student_email>` and `sa-<student_slug>@...`.<br>5. Increments `usage_counters.vertex_search` (`+1`). | Deletes Search Engine `search-app-...` and Data Store `search-ds-...` via Discovery Engine API and decrements `usage_counters.vertex_search` (`-1`). |

---

## 4. Suspend Student vs. Delete Student Slice (`CUJ-BU-06`)

1. **`SUSPEND_STUDENT`:**
   * Removes `user:<student_email>` from IAM bindings on `sa-<student_slug>`, `bkt-<project_id>-<student_slug>`, and their App-level Cloud Run / Vertex Search resources, sets `ALTER ROLE "<student_email>" NOLOGIN;` in Cloud SQL, and marks `StudentSlice.status = "SUSPENDED"` (preserving all data and App Containers for later `UNSUSPEND_STUDENT`).
2. **`DELETE_STUDENT_SLICE`:**
   * Iterates over all `AppContainer`s (`app-<app_slug>`) owned by the student and runs Atomic `DELETE` on every `AppServiceInstance`.
   * Drops `db_<student_sql_slug>` on `sql-<project_id>`, force-deletes `bkt-<project_id>-<student_slug>`, and deletes `sa-<student_slug>@...`.
   * Deletes the `StudentSlice` document and decrements `ProjectShard.initialized_student_count` (`-1`), freeing the seat in that Project Shard.
