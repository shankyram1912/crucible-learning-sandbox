# IT Admin — Secondary Implementation Details (`THE HOW`)

> **Master Document:** [Business Requirements Specification — Master (`THE WHAT`)](../01-brs/brs-master.md)
> **TDD Master Document:** [Technical Design & LLD — Master](tdd-master.md)  
> **Companion CUJ Document:** [IT Admin CUJs (`THE WHY`)](../01-brs/brs-it-admin-cuj.md)  
> **Terraform Source Location:** `src/terraform/itadmin/`

---

## 1. Version-Tracked Global Platform Config & Service Catalog Schema

The IT Admin Global Config Screen loads its initial baseline from the repository's **Platform Service Catalog Config** (`src/bff/config/service_catalog.json`) and persists every update as an **immutable, version-tracked document** in Firebase DB:

* **Firebase Path:** `/environments/{live|simulate}/global_config/versions/v{version_number}` (plus a pointer on `/environments/{live|simulate}/global_config/meta.active_version`).
* **Why Version Tracking:**
  1. Previous configuration versions can be viewed and audited at any time by the IT Admin.
  2. When a School/Cohort Admin creates a Cohort, the Cohort records `config_version = v{N}` so **existing Cohorts remain 100% unaffected** when the IT Admin saves `v{N+1}`.

### Example Versioned Global Config Document (`v1`)
```json
{
  "version": 1,
  "created_at": "2026-11-07T03:00:00Z",
  "created_by": "it-admin@domain.edu",
  "default_students_per_project": 100,
  "billing_account_id": "012345-6789AB-CDEF01",
  "currency_code": "USD",
  "root_budget_amount": 100000,
  "services": {
    "service_account": {
      "requirement": "MANDATORY",
      "prerequisites": [],
      "enabled_by_default": true,
      "can_disable": false,
      "scope": "student_singleton",
      "service_sizes": {},
      "quota_defaults": { "min": 1, "max": 1, "allow_override": false }
    },
    "gemini": {
      "requirement": "OPTIONAL",
      "prerequisites": ["service_account"],
      "enabled_by_default": true,
      "can_disable": true,
      "scope": "student_singleton",
      "service_sizes": {
        "apis": ["aiplatform.googleapis.com"],
        "allowed_models": ["gemini-2.5-pro", "gemini-2.5-flash"]
      },
      "quota_defaults": { "min": 1, "max": 1, "allow_override": false }
    },
    "gcs": {
      "requirement": "OPTIONAL",
      "prerequisites": ["service_account"],
      "enabled_by_default": true,
      "can_disable": true,
      "scope": "student_singleton_and_app_container",
      "service_sizes": {
        "apis": ["storage.googleapis.com"],
        "storage_class": "STANDARD",
        "uniform_bucket_level_access": true
      },
      "quota_defaults": {
        "student_bucket_min": 1,
        "app_managed_folders_min": "UNLIMITED",
        "app_managed_folders_max": "UNLIMITED",
        "allow_override": false
      }
    },
    "cloud_sql": {
      "requirement": "OPTIONAL",
      "prerequisites": ["service_account"],
      "enabled_by_default": true,
      "can_disable": true,
      "scope": "student_singleton_and_app_container",
      "service_sizes": {
        "apis": ["sqladmin.googleapis.com"],
        "database_version": "POSTGRES_15",
        "tier": "db-custom-2-7680",
        "disk_size_gb": 50,
        "connection_limit_per_student": 5
      },
      "quota_defaults": {
        "student_logical_db_min": 1,
        "app_schemas_min": 2,
        "app_schemas_max": 10,
        "allow_override": true
      }
    },
    "cloud_run": {
      "requirement": "OPTIONAL",
      "prerequisites": ["service_account"],
      "enabled_by_default": true,
      "can_disable": true,
      "scope": "app_container",
      "service_sizes": {
        "apis": ["run.googleapis.com", "artifactregistry.googleapis.com", "cloudbuild.googleapis.com"],
        "cpu_limit": "1000m",
        "memory_limit": "512Mi",
        "max_instance_count": 2
      },
      "quota_defaults": {
        "min": 2,
        "max": 10,
        "allow_override": true
      }
    },
    "vertex_search": {
      "requirement": "OPTIONAL",
      "prerequisites": ["service_account", "gcs"],
      "enabled_by_default": true,
      "can_disable": true,
      "scope": "app_container",
      "service_sizes": {
        "apis": ["discoveryengine.googleapis.com"],
        "industry_vertical": "GENERIC",
        "solution_type": "SOLUTION_TYPE_SEARCH"
      },
      "quota_defaults": {
        "min": 1,
        "max": 5,
        "allow_override": true
      }
    }
  }
}
```

---

## 2. Folder Hierarchy Boundary: IT Admin vs. School Admin

1. **Root Sandbox Folder (`folders/<root_folder_id>`):** Created during Day-0 Bootstrap (`specs/technical-design/bootstrap-spec.md`).
2. **IT Admin Folder Scope (`Depth 1 — Top-Level School Folder`):**
   * `parent = "folders/${var.root_folder_id}"`
   * The IT Admin creates **Top-Level School Folders** and assigns **Top-Level School Admins** (`school_admin_principals`, e.g., `group:grp-school-admin-eng@domain.edu` or `user:dean@domain.edu`) and **Pooled School Folder Budgets**.
3. **Delegation Boundary with BU Admin (`School Admin` & `Cohort Admin`):**
   * IT Admin Terraform (`src/terraform/itadmin/`) **never** needs to create Department Sub-folders (`Depth 2`), Cohort Folders, or GCP Projects.
   * Instead, IT Admin Terraform outputs `school_folder_id` (`folders/100000000101`), `billing_account_id`, and `school_admin_principals` into Firebase DB so the delegated **School Admin** can self-serve Department Sub-folders and assign **Cohort Admins** at the Sub-folder or Cohort level.

---

## 3. Terraform State Isolation for IT Admin (`src/terraform/itadmin`)

Each Top-Level School Folder (and its School Admin IAM bindings and Pooled School Folder Budget) is managed in an isolated Terraform state prefix inside the Control Tower state bucket:

```text
gs://<control-tower-tfstate-bucket>/itadmin/school-<school_slug>/default.tfstate
```

### Input `.tfvars.json` Compiled from IT Admin Intent
```json
{
  "root_folder_id": "folders/900000000001",
  "school_slug": "eng",
  "school_display_name": "College of Engineering",
  "billing_account_id": "012345-6789AB-CDEF01",
  "currency_code": "USD",
  "school_budget_amount": 40000,
  "school_admin_principals": [
    "group:grp-school-admin-eng@domain.edu"
  ],
  "control_tower_budget_pubsub_topic": "projects/ct-prod/topics/sandbox-budget-events"
}
```

### Expected `terraform output -json` Persisted to Firebase DB
Both `LIVE` mode (via `terraform apply` $\rightarrow$ `terraform output -json`) and `SIMULATE` mode (via `terraform validate` $\rightarrow$ deterministic output synthesis) emit the exact same JSON structure into `/environments/{live|simulate}/schools/{school_slug}`:
```json
{
  "school_folder_id": { "value": "folders/100000000101" },
  "school_budget_name": { "value": "billingAccounts/012345-6789AB-CDEF01/budgets/bgt-eng" }
}
```

---

## 4. Cascading Top-Level School Admin IAM Bindings

When the IT Admin assigns `school_admin_principals` to a Top-Level School Folder, `src/terraform/itadmin` provisions `google_folder_iam_member` bindings on that School Folder:
1. **`roles/resourcemanager.folderViewer`** — allows viewing the School Folder and all child Department Sub-folders and Cohort Folders in GCP Console.
2. **`roles/viewer`** — cascades read/inspection visibility down to all descendant Sub-folders, Cohort Folders, and Project Shards.
3. **Portal Authorization in Firebase DB:** All write operations inside that School subtree (creating Department Sub-folders, assigning Cohort Admins at Sub-folder or Cohort level, creating Cohorts, overriding project budgets) are authorized by the Control Tower BFF by verifying that the caller belongs to `school_admin_principals` on that School Folder (executed using `sa-control-tower`).

---

## 5. Pooled Folder Budgets via `resource_ancestors`

At the Root and Top-Level School Folder levels, `src/terraform/itadmin` provisions `google_billing_budget` resources using `budget_filter.resource_ancestors`:
* **Filter:** `resource_ancestors = ["folders/${folder_id}"]`
* **Why `resource_ancestors`:** Automatically aggregates 100% of spend from every Department Sub-folder, Cohort Folder, and Project Shard created underneath that School Folder in the future, with zero updates required to the `itadmin` Terraform state when School/Cohort Admins add or destroy cohorts.
* **Red Alert Banner Behavior:** Crossing `1.0` (`100%`) of `CURRENT_SPEND` publishes to `var.control_tower_budget_pubsub_topic` and sets `budget_exceeded = true` on that folder in Firebase DB, surfacing a Red Budget Alert Banner without freezing active student resources.

---

## 6. Single-Action Lock Matrix for IT Admin Operations

| Operation | Lock Document in Firebase DB | Lock Lease TTL | Blocked Concurrent Actors |
| :--- | :--- | :--- | :--- |
| **Save New Global Config Version / Update Root Budget** | `locks/root` | 5 minutes | Other IT Admins editing Global Config or Root settings |
| **Create New Top-Level School Folder** | `locks/root` | 5 minutes | Other IT Admins creating Root-level School Folders |
| **Update School Folder / School Admins / School Budget** | `locks/school_<school_slug>` | 5 minutes | Any IT Admin or School Admin mutating that specific School Folder header |
| **Delete Empty School Folder** | `locks/school_<school_slug>` | 5 minutes | Any actor in that School Folder subtree (verified `active_subfolder_count == 0 && active_cohort_count == 0` pre-flight) |
