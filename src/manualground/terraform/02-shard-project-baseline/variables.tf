# Values come from initialize.env as TF_VAR_<lowercase key> (exported by initialize.sh).

variable "mg_project_id" {
  description = "Globally unique project ID for this 80-student shard (MG_PROJECT_ID)."
  type        = string
}

variable "mg_folder_id" {
  description = "Playground guardrail folder ID (MG_FOLDER_ID, numeric or folders/<ID>)."
  type        = string
}

variable "billing_account_id" {
  description = "Billing account ID linked to the shard project (BILLING_ACCOUNT_ID)."
  type        = string
}

variable "region" {
  description = "Primary shard region (REGION)."
  type        = string
  default     = "asia-southeast1"
}

variable "student_group_email" {
  description = "Cohort Google Group email bound to shared project-level custom roles (STUDENT_GROUP_EMAIL). Optional."
  type        = string
  default     = ""
}

variable "tf_state_bucket" {
  description = "Optional GCS bucket name created inside the shard project for remote Terraform state (TF_STATE_BUCKET)."
  type        = string
  default     = ""
}

variable "billing_labels" {
  description = "Project billing attribution labels derived from LABEL_* keys in initialize.env."
  type        = map(string)
  default     = {}
}

variable "project_deletion_policy" {
  description = "Terraform project deletion policy (PREVENT for prod safety, DELETE for ephemeral test shards)."
  type        = string
  default     = "PREVENT"
}

# Baseline APIs for all 6 student services plus Eventarc/PubSub/Logging for ntu-run-auto-owner.
# Unmanaged VM/notebook/consumer-key APIs remain explicitly disabled.
variable "shard_apis" {
  description = "Google Cloud APIs enabled on the 80-student shard project."
  type        = list(string)
  default = [
    "serviceusage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "aiplatform.googleapis.com",
    "storage.googleapis.com",
    "storage-component.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "eventarc.googleapis.com",
    "pubsub.googleapis.com",
    "logging.googleapis.com",
    "sqladmin.googleapis.com",
    "firestore.googleapis.com",
    "firebase.googleapis.com",
    "discoveryengine.googleapis.com",
  ]

  validation {
    condition = (
      !contains(var.shard_apis, "compute.googleapis.com") &&
      !contains(var.shard_apis, "notebooks.googleapis.com") &&
      !contains(var.shard_apis, "generativelanguage.googleapis.com")
    )
    error_message = "compute.googleapis.com, notebooks.googleapis.com, and generativelanguage.googleapis.com must remain disabled on student shards."
  }
}

variable "service_agent_services" {
  description = "APIs whose Google-managed P4SA service identities are materialized eagerly."
  type        = list(string)
  default = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "eventarc.googleapis.com",
    "pubsub.googleapis.com",
    "aiplatform.googleapis.com",
    "discoveryengine.googleapis.com",
    "sqladmin.googleapis.com",
    "firestore.googleapis.com",
  ]
}
