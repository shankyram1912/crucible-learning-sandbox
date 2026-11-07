# IT Admin — Secondary Implementation Details (THE HOW)

> **Parent Document:** [01 — Business & Functional Specification](../01-business-spec.md)  
> **Companion CUJ Document:** [IT Admin CUJs (WHY)](it-admin-cuj.md)  
> **Terraform Source Location:** `src/terraform/itadmin/`

---

## 1. Folder Hierarchy & Depth Constraints

1. **Root Sandbox Folder (`folders/<root_folder_id>`):** Created during Day-0 Bootstrap (`specs/technical-design/bootstrap-spec.md`).
2. **Allowed IT Admin Folder Depths:**
   * **Depth 1 — School Folder:** `parent = "folders/${var.root_folder_id}"`
   * **Depth 2 — Department Sub-folder:** `parent = "folders/${var.school_folder_id}"`
3. **Boundary with BU Admin (`src/terraform/buadmin/`):**
   * IT Admin Terraform **never** creates Cohort Folders or GCP Projects inside `src/terraform/itadmin/`.
   * Instead, IT Admin Terraform outputs the `folder_id` (`folders/123456...`), `billing_account_id`, and `bu_admin_group_email` into Firebase DB. When a BU Admin later creates a Cohort under that School Folder or Sub-folder, the BU Admin Terraform pipeline reads `parent_folder_id` from Firebase DB.

---

## 2. Terraform State Isolation for IT Admin (`src/terraform/itadmin`)

Each School Folder (and its Department Sub-folders, Admin Group bindings, and Folder Budgets) is managed in an isolated Terraform workspace/state prefix inside the Control Tower state bucket:

```text
gs://<control-tower-tfstate-bucket>/itadmin/school-<school_slug>/default.tfstate
```

### Input `.tfvars.json` Compiled from IT Admin Canvas Intent
```json
{
  "root_folder_id": "folders/900000000001",
  "school_slug": "eng",
  "school_display_name": "College of Engineering",
  "billing_account_id": "012345-6789AB-CDEF01",
  "currency_code": "USD",
  "school_budget_amount": 40000,
  "school_bu_admin_groups": ["grp-bu-admin-eng-dean@domain.edu"],
  "control_tower_budget_pubsub_topic": "projects/ct-prod/topics/sandbox-budget-events",
  "subfolders": {
    "cs": {
      "display_name": "Computer Science",
      "budget_amount": 25000,
      "bu_admin_groups": ["grp-bu-admin-cs@domain.edu"]
    },
    "ee": {
      "display_name": "Electrical Engineering",
      "budget_amount": 15000,
      "bu_admin_groups": ["grp-bu-admin-ee@domain.edu"]
    }
  }
}
```

### Expected `terraform output -json` Persisted to Firebase DB
Both `LIVE` mode (via `terraform apply` $ightarrow$ `terraform output -json`) and `SIMULATE` mode (via `terraform validate` $ightarrow$ deterministic output synthesis) emit the exact same JSON structure into `/environments/{live|simulate}/folders/{folder_id}`:
```json
{
  "school_folder_id": { "value": "folders/100000000101" },
  "school_budget_name": { "value": "billingAccounts/012345-6789AB-CDEF01/budgets/bgt-eng" },
  "subfolder_ids": {
    "value": {
      "cs": "folders/100000000201",
      "ee": "folders/100000000202"
    }
  },
  "subfolder_budget_names": {
    "value": {
      "cs": "billingAccounts/012345-6789AB-CDEF01/budgets/bgt-eng-cs",
      "ee": "billingAccounts/012345-6789AB-CDEF01/budgets/bgt-eng-ee"
    }
  }
}
```

---

## 3. Cascading BU Admin IAM Group Bindings

When the IT Admin maps `group:<bu_admin_group_email>` to a School Folder or Department Sub-folder, `src/terraform/itadmin` provisions `google_folder_iam_member` bindings at that Folder resource:
1. **`roles/resourcemanager.folderViewer`** — allows viewing the folder hierarchy in GCP Console.
2. **`roles/viewer`** (or custom read-only inspector role) — cascades read/inspection visibility down to all descendant Cohort Folders and Project Shards so BU Admins can inspect logs, metrics, and resources when helping students troubleshoot.
3. **Portal Authorization Mapping in Firebase DB:** All write/mutation operations (creating Cohorts, initializing Project Shards via Terraform, overriding project budgets, mapping student groups) are authorized by the Control Tower BFF by checking that the caller is a member of `bu_admin_groups` on that Folder or an ancestor School Folder (executed using `sa-control-tower`).

---

## 4. Pooled Folder Budgets via `resource_ancestors`

At the Root, School, and Department Sub-folder levels, `src/terraform/itadmin` provisions `google_billing_budget` resources using `budget_filter.resource_ancestors`:
* **Filter:** `resource_ancestors = ["folders/${folder_id}"]`
* **Why `resource_ancestors`:** Automatically aggregates 100% of spend from every Cohort Folder and Project Shard created underneath that folder in the future, with zero updates required to the `itadmin` Terraform state when BU Admins add or destroy cohorts.
* **Thresholds & Pub/Sub Wiring:** Configures `0.5`, `0.8`, `0.9`, and `1.0` `CURRENT_SPEND` thresholds publishing to `var.control_tower_budget_pubsub_topic` so the Control Tower updates live spend bars on the Visual Canvas.

---

## 5. Single-Action Lock Matrix for IT Admin Operations

| Operation | Lock Document in Firebase DB | Lock Lease TTL | Blocked Concurrent Actors |
| :--- | :--- | :--- | :--- |
| **Create New School Folder** | `locks/root` | 5 minutes | Other IT Admins creating Root-level School Folders |
| **Update School Folder / Add Sub-folder / Map Group / Update Budget** | `locks/folder_<school_slug>` | 5 minutes | Any IT Admin or BU Admin mutating that specific School Folder subtree (other Schools remain unlocked) |
| **Delete Empty School / Sub-folder** | `locks/folder_<school_slug>` | 5 minutes | Any actor in that School Folder subtree (verified `active_cohort_count == 0` pre-flight) |
