# Service Catalog, IT Admin Global Config & Cohort Config Schemas (`tdd-data-catalog-and-config.md`)

> **Domain Master:** [tdd-data-master.md](tdd-data-master.md)

---

## 1. Three-Level Configuration Cascade Overview

```text
[Level 1: ServiceCatalog (/service_catalog/default)]
  Defines supported services, MANDATORY vs OPTIONAL requirement, prerequisite DAG,
  allowed size presets, and platform quota bounds.
       │
       ▼ (Seeds baseline & bounds)
[Level 2: ITAdminGlobalConfig (/global_config/current + /versions/{vN})]
  Version-tracked institution defaults (v1, v2, ...): default_students_per_project = 100,
  billing_account_id, root_budget_amount, default enabled services, selected service_sizes,
  and default per-student min / max quotas.
       │
       ▼ (Pinned at Cohort creation via based_on_global_config_version)
[Level 3: CohortConfig (/cohorts/{cohort_slug}.current_config + /config_versions/{vN})]
  Version-tracked Cohort configuration (v1, v2, ...): student_group_emails[],
  target_student_count (N), active_provisioning_project_id, non-destructive service
  toggles, and per-student allowance overrides.
```

---

## 2. `ServiceCatalog` Schema (`/service_catalog/default`)

Seeded from `src/bff/config/service_catalog.json` at startup. Enforces two structural invariants:
1. **`service_account` is `MANDATORY`** (`can_disable: false`) across all Global Configs and Cohorts.
2. **Prerequisite DAG (`prerequisites`):** Any optional service can declare required prerequisite service IDs (e.g., `vertex_search` requires `["service_account", "gcs"]`). Enabling a service automatically enables all of its prerequisites; a prerequisite cannot be disabled while a dependent service is enabled.

```json
{
  "catalog_revision": "2026-11-07",
  "default_students_per_project": 100,
  "services": {
    "service_account": {
      "display_name": "Student Service Account",
      "requirement": "MANDATORY",
      "can_disable": false,
      "prerequisites": [],
      "provisioning_scope": "STUDENT_SINGLETON",
      "required_apis": [
        "iam.googleapis.com",
        "cloudresourcemanager.googleapis.com",
        "serviceusage.googleapis.com",
        "logging.googleapis.com",
        "monitoring.googleapis.com"
      ],
      "size_options": {},
      "quota_bounds": { "min_default": 1, "max_ceiling": 1, "allow_cohort_override": false }
    },
    "gemini": {
      "display_name": "Vertex AI / Gemini Access",
      "requirement": "OPTIONAL",
      "can_disable": true,
      "prerequisites": ["service_account"],
      "provisioning_scope": "STUDENT_SINGLETON",
      "required_apis": ["aiplatform.googleapis.com"],
      "size_options": {
        "allowed_models": ["gemini-2.5-pro", "gemini-2.5-flash"]
      },
      "quota_bounds": { "min_default": 1, "max_ceiling": 1, "allow_cohort_override": false }
    },
    "gcs": {
      "display_name": "Cloud Storage (1 Student Bucket + Unlimited App Managed Folders)",
      "requirement": "OPTIONAL",
      "can_disable": true,
      "prerequisites": ["service_account"],
      "provisioning_scope": "STUDENT_SINGLETON_AND_APP_CONTAINER",
      "required_apis": ["storage.googleapis.com"],
      "size_options": {
        "storage_class": ["STANDARD", "NEARLINE"],
        "default_storage_class": "STANDARD"
      },
      "quota_bounds": {
        "student_buckets": 1,
        "app_managed_folders": "UNLIMITED",
        "allow_cohort_override": false
      }
    },
    "cloud_sql": {
      "display_name": "Cloud SQL for PostgreSQL (Shared Shard Instance + 1 Student DB + App Schemas)",
      "requirement": "OPTIONAL",
      "can_disable": true,
      "prerequisites": ["service_account"],
      "provisioning_scope": "PROJECT_SHARD_AND_STUDENT_SINGLETON_AND_APP_CONTAINER",
      "required_apis": ["sqladmin.googleapis.com"],
      "size_options": {
        "database_version": "POSTGRES_15",
        "allowed_tiers": ["db-custom-2-7680", "db-custom-4-15360"],
        "default_tier": "db-custom-2-7680",
        "default_disk_size_gb": 50,
        "default_connection_limit_per_student": 5
      },
      "quota_bounds": {
        "student_logical_dbs": 1,
        "app_schemas_min_default": 2,
        "app_schemas_max_ceiling": 10,
        "allow_cohort_override": true
      }
    },
    "cloud_run": {
      "display_name": "Cloud Run App Services",
      "requirement": "OPTIONAL",
      "can_disable": true,
      "prerequisites": ["service_account"],
      "provisioning_scope": "APP_CONTAINER",
      "required_apis": [
        "run.googleapis.com",
        "artifactregistry.googleapis.com",
        "cloudbuild.googleapis.com"
      ],
      "size_options": {
        "allowed_cpu": ["1000m", "2000m"],
        "default_cpu": "1000m",
        "allowed_memory": ["512Mi", "1Gi", "2Gi"],
        "default_memory": "512Mi",
        "default_max_instances": 2
      },
      "quota_bounds": {
        "app_services_min_default": 2,
        "app_services_max_ceiling": 10,
        "allow_cohort_override": true
      }
    },
    "vertex_search": {
      "display_name": "Vertex AI Search (Data Store + Search App)",
      "requirement": "OPTIONAL",
      "can_disable": true,
      "prerequisites": ["service_account", "gcs"],
      "provisioning_scope": "APP_CONTAINER",
      "required_apis": ["discoveryengine.googleapis.com"],
      "size_options": {
        "industry_vertical": "GENERIC",
        "solution_type": "SOLUTION_TYPE_SEARCH"
      },
      "quota_bounds": {
        "app_search_engines_min_default": 1,
        "app_search_engines_max_ceiling": 5,
        "allow_cohort_override": true
      }
    }
  }
}
```

---

## 3. Version-Tracked `ITAdminGlobalConfig` Schema (`/global_config/current` & `/global_config/current/versions/{vN}`)

Every time an IT Admin updates the Global Config screen, a Firestore transaction:
1. Increments `latest_version_number` (`N -> N+1`, e.g., `v2`).
2. Writes an immutable snapshot to `/global_config/current/versions/v{N+1}`.
3. Updates `/global_config/current` with `latest_version_id = "v{N+1}"` and the active configuration fields.

```json
{
  "latest_version_id": "v2",
  "version_number": 2,
  "previous_version_id": "v1",
  "created_at": "2026-11-07T09:00:00Z",
  "created_by": "it-admin@school.edu",
  "change_summary": "Increased default Cloud Run max ceiling to 8",
  "default_students_per_project": 100,
  "billing_account_id": "012345-6789AB-CDEF01",
  "currency_code": "USD",
  "default_region": "asia-southeast1",
  "root_budget_amount": 100000,
  "services": {
    "service_account": {
      "enabled_by_default": true,
      "can_disable": false,
      "prerequisites": [],
      "quota_defaults": { "min": 1, "max": 1 }
    },
    "gemini": {
      "enabled_by_default": true,
      "can_disable": true,
      "prerequisites": ["service_account"],
      "service_sizes": { "allowed_models": ["gemini-2.5-pro", "gemini-2.5-flash"] },
      "quota_defaults": { "min": 1, "max": 1 }
    },
    "gcs": {
      "enabled_by_default": true,
      "can_disable": true,
      "prerequisites": ["service_account"],
      "service_sizes": { "storage_class": "STANDARD", "uniform_bucket_level_access": true },
      "quota_defaults": { "student_buckets": 1, "app_managed_folders": "UNLIMITED" }
    },
    "cloud_sql": {
      "enabled_by_default": true,
      "can_disable": true,
      "prerequisites": ["service_account"],
      "service_sizes": {
        "database_version": "POSTGRES_15",
        "tier": "db-custom-2-7680",
        "disk_size_gb": 50,
        "connection_limit_per_student": 5
      },
      "quota_defaults": { "student_logical_dbs": 1, "min": 2, "max": 10 }
    },
    "cloud_run": {
      "enabled_by_default": true,
      "can_disable": true,
      "prerequisites": ["service_account"],
      "service_sizes": { "cpu_limit": "1000m", "memory_limit": "512Mi", "max_instance_count": 2 },
      "quota_defaults": { "min": 2, "max": 8 }
    },
    "vertex_search": {
      "enabled_by_default": true,
      "can_disable": true,
      "prerequisites": ["service_account", "gcs"],
      "service_sizes": { "industry_vertical": "GENERIC", "solution_type": "SOLUTION_TYPE_SEARCH" },
      "quota_defaults": { "min": 1, "max": 5 }
    }
  }
}
```

---

## 4. Version-Tracked `CohortConfig` Schema (`/cohorts/{cohort_slug}/config_versions/{vN}`)

When a Cohort Admin creates or updates a Cohort's settings:
1. A new immutable **`CohortConfigVersion`** document (`v1`, `v2`, ...) is written to `/cohorts/{cohort_slug}/config_versions/{vN}`.
2. On the parent `/cohorts/{cohort_slug}` document:
   * **`latest_config_version_id`** is updated immediately to `"v{N}"` along with **`current_config`** (so the UI always shows the latest saved config and full version history).
   * **`applied_config_version_id`** remains at the prior version (e.g., `"v{N-1}"`, or `null` on `v1`) until the Cloud Build Terraform run for `"v{N}"` finishes with `SUCCESS`, at which point `applied_config_version_id` advances to `"v{N}"`.
3. **Non-Destructive Service Toggles (`policy_enabled_services` vs. `provisioned_project_services`):**
   * `policy_enabled_services`: Forward-looking gate controlling which services are initialized for new students and which App services students can create (`deployed_count < per_student_quantities[service]`).
   * `provisioned_project_services`: Monotonically additive union of all services ever enabled across `v1..vN` for this Cohort, passed into Cohort Terraform so disabling an optional service in `v{N}` never destroys already-provisioned shared project infrastructure (`sql-<project_id>`, `ar-<project_id>`).

```json
{
  "version_id": "v2",
  "version_number": 2,
  "previous_version_id": "v1",
  "cohort_slug": "cs101-fall",
  "based_on_global_config_version": "v2",
  "created_at": "2026-11-07T09:10:00Z",
  "created_by": "prof-smith@school.edu",
  "change_summary": "Added second lecture section student group and raised Cloud Run quantity to 3",
  "student_group_emails": [
    "grp-cs101-lec1@school.edu",
    "grp-cs101-lec2@school.edu"
  ],
  "target_student_count": 250,
  "students_per_project": 100,
  "required_shard_count": 3,
  "active_provisioning_project_id": "cs101-fall-p01",
  "cohort_budget_amount": 8000,
  "default_project_spend_limit": 3000,
  "project_spend_limit_overrides": {
    "cs101-fall-p01": 4000
  },
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
  },
  "pinned_service_sizes": {
    "cloud_sql_tier": "db-custom-2-7680",
    "cloud_sql_disk_gb": 50,
    "cloud_sql_connection_limit": 5,
    "cloud_run_cpu": "1000m",
    "cloud_run_memory": "512Mi",
    "cloud_run_max_instances": 2
  }
}
```
