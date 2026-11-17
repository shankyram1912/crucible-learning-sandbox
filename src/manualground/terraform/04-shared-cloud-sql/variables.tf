# Values come from initialize.env as TF_VAR_<lowercase key> (exported by initialize.sh).

variable "mg_project_id" {
  description = "Shard project ID (MG_PROJECT_ID)."
  type        = string
}

variable "region" {
  description = "Primary shard region for the shared PostgreSQL 16 instance (REGION)."
  type        = string
  default     = "asia-southeast1"
}

variable "mg_preset" {
  description = "Sizing and HA profile: 'dev' (zonal db-custom-2-8192) or 'prod' (regional HA db-custom-4-16384, 800 max_connections)."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "prod"], var.mg_preset)
    error_message = "mg_preset must be either 'dev' or 'prod'."
  }
}

variable "enable_cloud_sql" {
  description = "Whether to provision the shared Cloud SQL for PostgreSQL 16 instance (ENABLE_CLOUD_SQL)."
  type        = bool
  default     = true
}

variable "mg_sql_instance" {
  description = "Cloud SQL instance name (defaults to sql-<MG_PROJECT_ID> when empty)."
  type        = string
  default     = ""
}

variable "billing_labels" {
  description = "Billing attribution labels derived from LABEL_* keys in initialize.env."
  type        = map(string)
  default     = {}
}
