# IT Admin School Folder & Pooled Budget Terraform (`tdd-iac-itadmin-school.md`)

> **Domain Master:** [tdd-iac-master.md](tdd-iac-master.md)  
> **Terraform Source Location:** `src/terraform/itadmin/`

---

## 1. Scope & GCS State Path

Manages a single **Top-Level School Folder** under the Root Sandbox Folder (`CUJ-IT-02` .. `CUJ-IT-04`), executed via Cloud Build using isolated GCS state:

```text
gs://<control-tower-tfstate-bucket>/tfstate/itadmin/school-<school_slug>/default.tfstate
```

---

## 2. Input `.tfvars.json` Contract (`tfvars/itadmin/school-<school_slug>/latest.tfvars.json`)

```json
{
  "root_folder_id": "folders/900000000001",
  "school_slug": "eng",
  "school_display_name": "College of Engineering",
  "billing_account_id": "012345-6789AB-CDEF01",
  "currency_code": "USD",
  "school_budget_amount": 40000,
  "school_admin_principals": [
    "group:grp-school-admin-eng@school.edu",
    "user:dean-eng@school.edu"
  ],
  "control_tower_budget_pubsub_topic": "projects/ct-prod/topics/sandbox-budget-events"
}
```

---

## 3. Declarative Resources & IAM Bindings

1. **Top-Level School Folder (`google_folder.school`):**
   * `display_name = "${var.school_display_name} (${var.school_slug})"`
   * `parent = var.root_folder_id`
   * `deletion_protection = false`
2. **School Admin Read/Inspection Bindings (`google_folder_iam_member`):**
   * Binds each principal in `var.school_admin_principals` to:
     * `roles/resourcemanager.folderViewer`
     * `roles/viewer`
   * All write mutations inside the School subtree (creating Department Sub-folders, delegating Cohort Admins, creating Cohorts) are authorized by the FastAPI BFF (`School Admin` persona check) and executed by `sa-control-tower`.
3. **Pooled School Folder Budget (`google_billing_budget.school_budget`):**
   * `budget_filter.resource_ancestors = [google_folder.school.name]`
   * Automatically aggregates 100% of spend across all Department Sub-folders, Cohort Folders, and Project Shards created under this School Folder without requiring updates to the `itadmin` Terraform state.

---

## 4. Output Contract (`outputs.json`)

```json
{
  "school_folder_id": { "value": "folders/100000000101" },
  "school_budget_name": { "value": "billingAccounts/012345-6789AB-CDEF01/budgets/bgt-eng" }
}
```
