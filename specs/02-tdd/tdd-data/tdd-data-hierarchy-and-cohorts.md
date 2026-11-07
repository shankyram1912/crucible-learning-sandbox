# School, Department Sub-folder, Cohort & Project Shard Schemas (`tdd-data-hierarchy-and-cohorts.md`)

> **Domain Master:** [tdd-data-master.md](tdd-data-master.md)

---

## 1. `School` Document Schema (`/schools/{school_slug}`)

Created and updated by the **IT Admin** (`CUJ-IT-02` .. `CUJ-IT-04`). Assigns **Top-Level School Admins** (`school_admin_emails[]` / groups), who automatically inherit **Cohort Admin** permissions across the entire School subtree.

```json
{
  "school_slug": "eng",
  "display_name": "College of Engineering",
  "root_folder_id": "folders/900000000001",
  "gcp_folder_id": "folders/100000000101",
  "school_admin_principals": [
    "group:grp-school-admin-eng@school.edu",
    "user:dean-eng@school.edu"
  ],
  "pooled_budget_amount": 40000,
  "currency_code": "USD",
  "billing_budget_name": "billingAccounts/012345-6789AB-CDEF01/budgets/bgt-eng",
  "spend_to_date": 4250.00,
  "budget_exceeded": false,
  "status": "READY",
  "active_cloud_build_id": null,
  "last_cloud_build_id": "cb-98a7bc12",
  "last_error": null,
  "created_at": "2026-11-07T08:00:00Z",
  "updated_at": "2026-11-07T08:05:00Z"
}
```

---

## 2. `DepartmentSubfolder` Document Schema (`/subfolders/{school_slug}__{subfolder_slug}`)

Created, updated, and decommissioned by a **Top-Level School Admin** (`CUJ-BU-01` .. `CUJ-BU-03`). Allows delegating additional **Cohort Admins** at the Department Sub-folder level.

```json
{
  "subfolder_id": "eng__cs",
  "school_slug": "eng",
  "subfolder_slug": "cs",
  "display_name": "Department of Computer Science",
  "parent_school_folder_id": "folders/100000000101",
  "gcp_folder_id": "folders/100000000201",
  "cohort_admin_principals": [
    "group:grp-cs-cohort-admins@school.edu"
  ],
  "pooled_budget_amount": 15000,
  "billing_budget_name": "billingAccounts/012345-6789AB-CDEF01/budgets/bgt-eng-cs",
  "spend_to_date": 1800.00,
  "budget_exceeded": false,
  "status": "READY",
  "active_cloud_build_id": null,
  "last_cloud_build_id": "cb-4412ef09",
  "last_error": null,
  "created_at": "2026-11-07T08:15:00Z",
  "updated_at": "2026-11-07T08:18:00Z"
}
```

---

## 3. `Cohort` Document Schema (`/cohorts/{cohort_slug}`)

Created and managed by any **Cohort Admin** (which includes all **Top-Level School Admins** by default) (`CUJ-BU-04` .. `CUJ-BU-09`).

### Key State & Versioning Fields on `Cohort`:
* **`latest_config_version_id` (`"v2"`):** Points to the most recent `CohortConfigVersion` saved by the Cohort Admin (embedded in `current_config` for single-read access).
* **`applied_config_version_id` (`"v2"` or `"v1"`):** Points to the last `CohortConfigVersion` whose Cloud Build Terraform run completed with `SUCCESS`.
  * When `status == "PROVISIONING"` on initial creation (`applied_config_version_id == null`), students cannot initialize workspaces yet.
  * When `status == "UPDATING"` (`latest_config_version_id == "v2"`, `applied_config_version_id == "v1"`), students continue operating smoothly against the applied `"v1"` state until `"v2"` finishes provisioning.
* **`active_provisioning_project_id` (`"<cohort_slug>-p01"`):** The Project Shard where new students entering the Cohort workspace are assigned. Automatically advances to the next shard with `remaining_capacity > 0` when full, and can be manually switched by a Cohort Admin at any time.

```json
{
  "cohort_slug": "cs101-fall",
  "display_name": "CS101 Fall 2026",
  "school_slug": "eng",
  "parent_type": "SUBFOLDER",
  "parent_subfolder_slug": "cs",
  "parent_gcp_folder_id": "folders/100000000201",
  "gcp_folder_id": "folders/100000000301",
  "cohort_admin_principals": [
    "user:prof-smith@school.edu"
  ],
  "latest_config_version_id": "v2",
  "applied_config_version_id": "v2",
  "active_provisioning_project_id": "cs101-fall-p01",
  "current_config": {
    "version_id": "v2",
    "based_on_global_config_version": "v2",
    "student_group_emails": [
      "grp-cs101-lec1@school.edu",
      "grp-cs101-lec2@school.edu"
    ],
    "target_student_count": 250,
    "students_per_project": 100,
    "required_shard_count": 3,
    "cohort_budget_amount": 8000,
    "default_project_spend_limit": 3000,
    "policy_enabled_services": {
      "service_account": true,
      "gemini": true,
      "gcs": true,
      "cloud_sql": true,
      "cloud_run": true,
      "vertex_search": true
    },
    "provisioned_project_services": {
      "service_account": true,
      "gemini": true,
      "gcs": true,
      "cloud_sql": true,
      "cloud_run": true,
      "vertex_search": true
    },
    "per_student_quantities": {
      "service_account": 1,
      "gemini": 1,
      "gcs_bucket": 1,
      "gcs_managed_folders": "UNLIMITED",
      "cloud_sql_db": 1,
      "cloud_sql_schemas": 2,
      "cloud_run": 3,
      "vertex_search": 1
    }
  },
  "spend_to_date": 920.50,
  "budget_exceeded": false,
  "status": "READY",
  "active_cloud_build_id": null,
  "last_cloud_build_id": "cb-7721aa03",
  "last_error": null,
  "created_at": "2026-11-07T08:30:00Z",
  "updated_at": "2026-11-07T09:10:00Z"
}
```

---

## 4. `ProjectShard` Document Schema (`/cohorts/{cohort_slug}/shards/{project_id}`)

Each Cohort with $N$ target students provisions $K = \max(1, \lceil N / 100 \rceil)$ Project Shards named `<cohort_slug>-p01` .. `<cohort_slug>-pKK`.

```json
{
  "project_id": "cs101-fall-p01",
  "project_number": "445566778801",
  "cohort_slug": "cs101-fall",
  "shard_index": 1,
  "max_student_capacity": 100,
  "initialized_student_count": 42,
  "remaining_capacity": 58,
  "is_active_provisioning_shard": true,
  "shared_infrastructure": {
    "cloud_sql_instance_name": "sql-cs101-fall-p01",
    "cloud_sql_connection_name": "cs101-fall-p01:asia-southeast1:sql-cs101-fall-p01",
    "cloud_sql_state": "RUNNABLE",
    "artifact_registry_repo": "projects/cs101-fall-p01/locations/asia-southeast1/repositories/ar-cs101-fall-p01",
    "p4sa_warmed_up": true
  },
  "spend_limit": 4000,
  "is_spend_limit_overridden": true,
  "spend_to_date": 410.25,
  "budget_exceeded": false,
  "status": "READY",
  "updated_at": "2026-11-07T09:12:00Z"
}
```
