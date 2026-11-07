# IT Admin Operational API Domain (`tdd-apis-it-admin.md`)

> **Domain Master:** [tdd-apis-master.md](tdd-apis-master.md)  
> **Route Prefix:** `/api/v1/it-admin`  
> **Required Persona:** `IT Admin`

---

## 1. Service Catalog & Version-Tracked Global Config Endpoints (`CUJ-IT-01`)

| Method & Path | Description | Pipeline / Store Action |
| :--- | :--- | :--- |
| `GET /api/v1/it-admin/service-catalog` | Returns the master `/service_catalog/default` document (`MANDATORY` `service_account`, `prerequisites` mappings, allowed size presets, and platform quota bounds). | Firestore Read |
| `GET /api/v1/it-admin/global-config` | Returns `/global_config/current` including `latest_version_id` (`"v2"`), `default_students_per_project` (`100`), billing account, root budget, and per-service defaults/sizes/quotas. | Firestore Read |
| `GET /api/v1/it-admin/global-config/versions` | Lists all immutable historical versions (`/global_config/current/versions/{v1..vN}`) in descending order so the IT Admin can inspect previous config versions. | Firestore Read |
| `GET /api/v1/it-admin/global-config/versions/{version_id}` | Fetches a specific historical `ITAdminGlobalConfig` version (e.g., `v1`). | Firestore Read |
| `POST /api/v1/it-admin/global-config` | Validates prerequisite invariants (`service_account` cannot be disabled; enabled services have all prerequisites enabled; `min <= max`), writes a new immutable `v{N+1}` snapshot to `/global_config/current/versions/v{N+1}`, and updates `latest_version_id` on `/global_config/current`. Existing Cohorts remain pinned to their `based_on_global_config_version`. | Firestore Transaction |

---

## 2. Top-Level School Folder & Pooled Budget Endpoints (`CUJ-IT-02` .. `CUJ-IT-04`)

| Method & Path | Description | Pipeline / Store Action |
| :--- | :--- | :--- |
| `GET /api/v1/it-admin/schools` | Lists all Top-Level School Folders (`/schools/*`). For any School with `status in {"PROVISIONING", "UPDATING"}`, lazily reconciles `active_cloud_build_id` via Cloud Build API before returning. | Firestore Read + Lazy Cloud Build Reconcile |
| `POST /api/v1/it-admin/schools?simulate=bool` | Creates `/schools/{school_slug}` (`status = "PROVISIONING"`), compiles `tfvars/itadmin/school-<slug>/latest.tfvars.json`, and triggers the **Cloud Build Terraform Pipeline (`itadmin` module)** (`202 Accepted`). | Cloud Build Terraform Pipeline (`itadmin`) |
| `PATCH /api/v1/it-admin/schools/{school_slug}?simulate=bool` | Updates `school_admin_principals` or `pooled_budget_amount` on `/schools/{school_slug}` (`status = "UPDATING"`) and triggers the **Cloud Build Terraform Pipeline (`itadmin` module)** (`202 Accepted`). | Cloud Build Terraform Pipeline (`itadmin`) |
| `POST /api/v1/it-admin/schools/{school_slug}/retry?simulate=bool` | Re-triggers the Cloud Build Terraform run for a School in `status == "ERROR"` (automatically setting `_FORCE_UNLOCK_IF_LOCKED=true` if the prior build died holding `.tflock`). | Cloud Build Terraform Pipeline (`itadmin`) |
| `DELETE /api/v1/it-admin/schools/{school_slug}?simulate=bool` | Verifies the School has `0` child Sub-folders and `0` child Cohorts, then triggers Cloud Build `terraform destroy` for `itadmin/school-<school_slug>`. | Cloud Build Terraform Pipeline (`itadmin` `DESTROY`) |
