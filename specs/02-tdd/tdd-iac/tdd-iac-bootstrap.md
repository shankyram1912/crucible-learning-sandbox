# Day-0 Control Tower Bootstrap Terraform (`tdd-iac-bootstrap.md`)

> **Domain Master:** [tdd-iac-master.md](tdd-iac-master.md)  
> **Terraform Source Location:** `src/terraform/bootstrap/`

---

## 1. Purpose

Executed once by Central IT during Day-0 platform installation to stand up the **Control Tower Project**, the **Root Sandbox Folder**, the **GCS Terraform State & `.tfvars.json` Bucket**, the privileged **Control Tower Service Account (`sa-control-tower`)**, and the **Cloud Build Trigger / Worker Permissions**.

---

## 2. Provisioned Day-0 Resources

1. **Root Sandbox Folder (`google_folder.sandbox_root`):**
   * Top-level GCP folder (`display_name = "Learning Sandbox Root"`) under which all School Folders, Department Sub-folders, Cohort Folders, and Project Shards live.
2. **Control Tower Project & APIs:**
   * Enables `cloudresourcemanager.googleapis.com`, `iam.googleapis.com`, `serviceusage.googleapis.com`, `cloudbilling.googleapis.com`, `billingbudgets.googleapis.com`, `cloudbuild.googleapis.com`, `firestore.googleapis.com`, `run.googleapis.com`, `sqladmin.googleapis.com`, `discoveryengine.googleapis.com`.
3. **GCS State & Artifacts Bucket (`bkt-<control_tower_project>-tfstate`):**
   * Object Versioning enabled (`versioning { enabled = true }`).
   * Hosts:
     * `/modules/{itadmin,subfolder,cohort}/*.tf` (synced Terraform modules used by Cloud Build workers)
     * `/tfstate/**` (`default.tfstate` and `.tflock` per School, Sub-folder, and Cohort)
     * `/tfvars/**` (compiled `<version_id>.tfvars.json` inputs and `<version_id>-outputs.json` outputs)
4. **Control Tower Service Account (`sa-control-tower@<control_tower_project>.iam.gserviceaccount.com`):**
   * Used by both the **Cloud Build Terraform Worker** and the **FastAPI Atomic Pipeline Runner**.
   * **Bindings on `google_folder.sandbox_root`:**
     * `roles/resourcemanager.folderAdmin` (create/manage School, Sub-folder, and Cohort Folders)
     * `roles/resourcemanager.projectCreator` & `roles/resourcemanager.projectDeleter` (create and teardown Cohort Project Shards)
     * `roles/owner` or scoped Admin roles (`roles/iam.securityAdmin`, `roles/iam.serviceAccountAdmin`, `roles/serviceusage.serviceUsageAdmin`, `roles/storage.admin`, `roles/cloudsql.admin`, `roles/run.admin`, `roles/discoveryengine.admin`) cascading down the Root Sandbox Folder so both Cloud Build Terraform and the Atomic Pipeline can provision resources inside any descendant Project Shard.
   * **Bindings on the Cloud Billing Account:**
     * `roles/billing.user` (link Cohort Project Shards to Billing Account)
     * `roles/billing.costsManager` (create and update `google_billing_budget` resources).
5. **Root Pooled Billing Budget (`google_billing_budget.root_budget`):**
   * `budget_filter.resource_ancestors = ["folders/${google_folder.sandbox_root.folder_id}"]`.
   * Publishes threshold alerts to `google_pubsub_topic.budget_events`.
