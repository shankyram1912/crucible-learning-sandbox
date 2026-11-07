# Student Slice, Singleton Resources & App Container Schemas (`tdd-data-students-and-apps.md`)

> **Domain Master:** [tdd-data-master.md](tdd-data-master.md)

---

## 1. Student Slug Normalization Rules (Single Institutional Domain)

Because the platform operates within a single institutional domain (`@school.edu`), a student's identity is uniquely derived from the local-part of their email address (before `@`) with **zero collision risk**:

* **`student_email`:** `alice.tan@school.edu`
* **`student_slug` (GCP IAM / GCS / Cloud Run / Vertex Search safe):** Lowercase alphanumeric with non-alphanumerics replaced by `-` $\rightarrow$ `alice-tan`
* **`student_sql_slug` (PostgreSQL identifier safe):** Lowercase alphanumeric with `-` replaced by `_` $\rightarrow$ `alice_tan`

---

## 2. `StudentSlice` Document Schema (`/cohorts/{cohort_slug}/students/{student_slug}`)

Created or updated **just-in-time (JIT)** when a student belonging to one of the Cohort's `student_group_emails[]` enters the Cohort workspace (`POST /api/v1/student/cohorts/{cohort_slug}/enter`).

* **Shard Assignment:** On first entry, the student is transactionally assigned to `Cohort.active_provisioning_project_id` (`assigned_project_id`), incrementing that shard's `initialized_student_count` (`+1`). Once assigned, `assigned_project_id` is permanent for that student in that Cohort.
* **Student-Level Singletons (`singletons`):** Tracks the provisioning state of the student's baseline singleton resources (`1` mandatory `sa-<student_slug>`, `Gemini`, `1` `bkt-<project_id>-<student_slug>`, `1` `db_<student_sql_slug>`).
* **App Creation Gate (`can_create_apps`):** Set to `true` as soon as `workspace_init_status == "INITIALIZED"` and `status == "ACTIVE"`.
* **Pooled Usage Counters (`usage_counters`):** Tracks active App-scoped resources across **all** of the student's `AppContainer`s inside this Cohort to enforce `Cohort.current_config.per_student_quantities`.

```json
{
  "student_slug": "alice-tan",
  "student_sql_slug": "alice_tan",
  "student_email": "alice.tan@school.edu",
  "cohort_slug": "cs101-fall",
  "assigned_project_id": "cs101-fall-p01",
  "status": "ACTIVE",
  "workspace_init_status": "INITIALIZED",
  "can_create_apps": true,
  "singletons": {
    "service_account": {
      "status": "READY",
      "email": "sa-alice-tan@cs101-fall-p01.iam.gserviceaccount.com"
    },
    "gemini": {
      "status": "READY",
      "models": ["gemini-2.5-pro", "gemini-2.5-flash"]
    },
    "gcs_bucket": {
      "status": "READY",
      "bucket_name": "bkt-cs101-fall-p01-alice-tan",
      "uri": "gs://bkt-cs101-fall-p01-alice-tan"
    },
    "cloud_sql_db": {
      "status": "READY",
      "instance_name": "sql-cs101-fall-p01",
      "database_name": "db_alice_tan"
    }
  },
  "usage_counters": {
    "gcs_managed_folders": 2,
    "cloud_sql_schemas": 1,
    "cloud_run": 1,
    "vertex_search": 1
  },
  "first_entered_at": "2026-11-07T09:00:00Z",
  "updated_at": "2026-11-07T09:05:00Z"
}
```

---

## 3. `AppContainer` Document Schema (`/cohorts/{cohort_slug}/students/{student_slug}/apps/{app_slug}`)

Once `StudentSlice.can_create_apps == true`, a student can create multiple logical **App Containers (`app-<app_slug>`)** (`CUJ-ST-02`) to organize their coursework or projects without resource naming collisions.

```json
{
  "app_slug": "rag-bot",
  "app_container_id": "app-rag-bot",
  "display_name": "Policy RAG Chatbot",
  "student_slug": "alice-tan",
  "cohort_slug": "cs101-fall",
  "project_id": "cs101-fall-p01",
  "status": "READY",
  "service_counts": {
    "gcs_managed_folders": 1,
    "cloud_sql_schemas": 1,
    "cloud_run": 1,
    "vertex_search": 1
  },
  "created_at": "2026-11-07T09:02:00Z",
  "updated_at": "2026-11-07T09:05:00Z"
}
```

---

## 4. `AppServiceInstance` Document Schema (`.../apps/{app_slug}/services/{service_instance_id}`)

Represents an individual App-scoped building block created by the student inside `app-<app_slug>` (`CUJ-ST-03`) and torn down when deleted (`CUJ-ST-04`):

| `service_type` | `service_instance_id` Example | Underlying GCP / SQL Resource Identifier | Counts Toward Student Allowance |
| :--- | :--- | :--- | :--- |
| `GCS_MANAGED_FOLDER` | `gcs-folder-docs` | `gs://bkt-<project_id>-<student_slug>/apps/<app_slug>/<folder_name>/` | Unlimited (`∞`) |
| `POSTGRES_SCHEMA` | `sql-schema-vectors` | Schema `<app_slug>_<schema_name>` inside `db_<student_sql_slug>` on `sql-<project_id>` | `usage_counters.cloud_sql_schemas` |
| `CLOUD_RUN_SERVICE` | `run-svc-api` | Cloud Run v2 Service `run-<student_slug>-<app_slug>-<svc_name>` (running as `sa-<student_slug>`) | `usage_counters.cloud_run` |
| `VERTEX_SEARCH_APP` | `vertex-search-kb` | Paired Data Store `search-ds-<student_slug>-<app_slug>-<name>` + Engine `search-app-<student_slug>-<app_slug>-<name>` | `usage_counters.vertex_search` |

```json
{
  "service_instance_id": "run-svc-api",
  "service_type": "CLOUD_RUN_SERVICE",
  "name_suffix": "api",
  "gcp_resource_name": "run-alice-tan-rag-bot-api",
  "app_slug": "rag-bot",
  "student_slug": "alice-tan",
  "cohort_slug": "cs101-fall",
  "project_id": "cs101-fall-p01",
  "status": "READY",
  "connection_metadata": {
    "service_url": "https://run-alice-tan-rag-bot-api-xyz-as.a.run.app",
    "runtime_service_account": "sa-alice-tan@cs101-fall-p01.iam.gserviceaccount.com",
    "console_url": "https://console.cloud.google.com/run/detail/asia-southeast1/run-alice-tan-rag-bot-api?project=cs101-fall-p01"
  },
  "created_at": "2026-11-07T09:04:00Z",
  "updated_at": "2026-11-07T09:04:12Z"
}
```
