# Student Workspace & App Container Operational API Domain (`tdd-apis-student.md`)

> **Domain Master:** [tdd-apis-master.md](tdd-apis-master.md)  
> **Route Prefix:** `/api/v1/student`  
> **Required Persona:** `Student` (matching `Cohort.current_config.student_group_emails[]`) or `Cohort Admin` / `School Admin` / `IT Admin` acting on behalf of a student.

---

## 1. Cohort Selection & JIT Workspace Entry Endpoints (`CUJ-ST-01`)

| Method & Path | Description & Connected Pipeline |
| :--- | :--- |
| `GET /api/v1/student/cohorts` | Returns all Cohorts where the logged-in student belongs to at least one group in `Cohort.current_config.student_group_emails[]` (or an empty list if unassigned). |
| `POST /api/v1/student/cohorts/{cohort_slug}/enter?simulate=bool` | **JIT Workspace Entry & Auto-Initialization:**<br>1. Verifies caller belongs to `student_group_emails[]` and `Cohort.applied_config_version_id != null` (if `null`, returns `202` with `workspace_init_status = "WAITING_FOR_COHORT_FOUNDATION"`).<br>2. If the student has no `StudentSlice` yet, transactionally assigns them to `Cohort.active_provisioning_project_id` (`<cohort_slug>-pNN`), increments that shard's `initialized_student_count` (`+1`), and auto-advances `active_provisioning_project_id` to the next shard with `remaining_capacity > 0` if the shard reaches `100`.<br>3. Checks if all Student-Level Singletons enabled in `applied_config.policy_enabled_services` (`sa-<student_slug>`, `Gemini`, `bkt-<project_id>-<student_slug>`, `db_<student_sql_slug>`) are `READY`; if any are missing, invokes **Atomic Pipeline (`INIT_STUDENT_WORKSPACE`)**.<br>4. Sets `can_create_apps = true` and returns the complete `StudentSlice` + `apps[]` list. |
| `GET /api/v1/student/cohorts/{cohort_slug}/workspace` | Returns the student's `StudentSlice` (`singletons`, `usage_counters`, `can_create_apps`), the Cohort's `per_student_quantities` & `policy_enabled_services`, and all `AppContainer`s (`app-<app_slug>`) with their child `AppServiceInstance`s. |

---

## 2. App Container (`app-<app_slug>`) & App Service CRUD Endpoints (`CUJ-ST-02` .. `CUJ-ST-06`)

| Method & Path | Description & Connected Pipeline |
| :--- | :--- |
| `POST /api/v1/student/cohorts/{cohort_slug}/apps` | Requires `StudentSlice.can_create_apps == true` and `status == "ACTIVE"`. Creates a logical `AppContainer` document (`app-<app_slug>`) under `/cohorts/{cohort_slug}/students/{student_slug}/apps/{app_slug}`. |
| `DELETE /api/v1/student/cohorts/{cohort_slug}/apps/{app_slug}?simulate=bool` | Invokes **Atomic Pipeline (`DELETE_APP_CONTAINER`)** to tear down all child `AppServiceInstance`s inside `app-<app_slug>` in dependency order (`VERTEX_SEARCH_APP` $\rightarrow$ `CLOUD_RUN_SERVICE` $\rightarrow$ `POSTGRES_SCHEMA` $\rightarrow$ `GCS_MANAGED_FOLDER`), decrements `StudentSlice.usage_counters`, and deletes the `AppContainer` document. |
| `POST /api/v1/student/cohorts/{cohort_slug}/apps/{app_slug}/services?simulate=bool` | **Create App-Scoped Service:**<br>1. Validates `service_type` $\in$ `{GCS_MANAGED_FOLDER, POSTGRES_SCHEMA, CLOUD_RUN_SERVICE, VERTEX_SEARCH_APP}`.<br>2. Enforces **Pre-Flight Allowance Gate** against `Cohort.current_config`: verifies `policy_enabled_services[s] == true` and `StudentSlice.usage_counters[s] < per_student_quantities[s]` (unlimited $\infty$ for `GCS_MANAGED_FOLDER`).<br>3. Invokes **Atomic Pipeline (`CREATE_APP_SERVICE`)** to provision the resource, bind usage-only rights to `user:<student_email>` and `sa-<student_slug>`, increment `usage_counters[s]`, and return `connection_metadata`. |
| `DELETE /api/v1/student/cohorts/{cohort_slug}/apps/{app_slug}/services/{service_instance_id}?simulate=bool` | **Delete App-Scoped Service (Frees Allowance):**<br>Invokes **Atomic Pipeline (`DELETE_APP_SERVICE`)** to delete the underlying GCP / SQL resource, remove the `AppServiceInstance` document, and decrement `StudentSlice.usage_counters[s]` (`-1`) so the student can immediately reuse that allowance slot. |
