# Values come from initialize.env as TF_VAR_<lowercase key> (exported by initialize.sh).

variable "org_id" {
  description = "Google Cloud Organization numeric ID (ORG_ID)."
  type        = string
}

variable "region" {
  description = "Primary region for shared playground shards (REGION)."
  type        = string
  default     = "asia-southeast1"
}

variable "mg_parent_folder" {
  description = "Parent resource under which the Playground folder resides: organizations/<ORG_ID> or folders/<FOLDER_ID>."
  type        = string
}

variable "mg_folder_name" {
  description = "Display name when creating a new Playground guardrail folder."
  type        = string
  default     = "NTU Playground"
}

variable "mg_folder_id" {
  description = "Existing Playground folder ID (numeric or folders/<ID>). Empty creates a new folder."
  type        = string
  default     = ""
}

variable "mg_folder_managed" {
  description = "True when this Terraform stack created MG_FOLDER_ID on an earlier run and continues managing it."
  type        = bool
  default     = false
}

variable "directory_customer_id" {
  description = "Workspace / Cloud Identity customer ID (e.g. C03ccny1h) for iam.allowedPolicyMemberDomains. Optional."
  type        = string
  default     = ""
}

variable "it_admins_group" {
  description = "IT Admins Google Group email exempted from Folder IAM Deny v2 control-plane locks."
  type        = string
  default     = ""
}

variable "provisioner_sa_email" {
  description = "Optional dedicated Layer 1/Layer 2 provisioner service account email exempted from Folder IAM Deny v2."
  type        = string
  default     = ""
}

variable "require_invoker_iam" {
  description = "Enforce constraints/run.managed.requireInvokerIam on the Playground folder."
  type        = bool
  default     = true
}

variable "enable_org_custom_constraints" {
  description = "Create and enforce custom.ntuDenyCloudRunGpu at the Organization/Folder level."
  type        = bool
  default     = true
}

# Cloud Run service creation and per-service deletion are intentionally NOT included here
# so students can create services on-demand via ClickOps and delete only services on which
# ntu-run-auto-owner granted them custom_ntu_run_owner.
variable "denied_control_plane_permissions" {
  description = "IAM v2 FQDN permissions denied across all child shard projects except admin/provisioner principals."
  type        = list(string)
  default = [
    "iam.googleapis.com/serviceAccounts.create",
    "iam.googleapis.com/serviceAccounts.delete",
    "iam.googleapis.com/roles.create",
    "iam.googleapis.com/roles.update",
    "iam.googleapis.com/roles.delete",
    "storage.googleapis.com/buckets.create",
    "storage.googleapis.com/buckets.delete",
    "storage.googleapis.com/buckets.update",
    "storage.googleapis.com/buckets.setIamPolicy",
    "cloudsql.googleapis.com/instances.create",
    "cloudsql.googleapis.com/instances.delete",
    "cloudsql.googleapis.com/instances.update",
    "cloudsql.googleapis.com/databases.delete",
    "datastore.googleapis.com/databases.create",
    "datastore.googleapis.com/databases.delete",
    "datastore.googleapis.com/databases.update",
    "discoveryengine.googleapis.com/dataStores.create",
    "discoveryengine.googleapis.com/dataStores.delete",
    "discoveryengine.googleapis.com/dataStores.setIamPolicy",
    "discoveryengine.googleapis.com/engines.create",
    "discoveryengine.googleapis.com/engines.delete",
    "discoveryengine.googleapis.com/engines.setIamPolicy",
    "run.googleapis.com/jobs.create",
    "run.googleapis.com/jobs.delete",
  ]
}
