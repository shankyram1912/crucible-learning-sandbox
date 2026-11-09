# Values come from initialize.env as TF_VAR_<lowercase key> (exported by initialize.sh).

variable "ct_project_id" {
  description = "Control Tower project ID (CT_PROJECT_ID)."
  type        = string
}

variable "region" {
  description = "Firestore location (REGION). Cannot be changed after the database is created."
  type        = string
}

variable "firestore_database" {
  description = "Firestore database ID for runtime state and jobs (FIRESTORE_DATABASE)."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,61}[a-z0-9]$", var.firestore_database))
    error_message = "FIRESTORE_DATABASE must be 4-63 characters: lowercase letters, digits, hyphens; start with a letter; not end with a hyphen."
  }
}

variable "firestore_config_database" {
  description = "Firestore database ID for config, the desired state (FIRESTORE_CONFIG_DATABASE)."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,61}[a-z0-9]$", var.firestore_config_database))
    error_message = "FIRESTORE_CONFIG_DATABASE must be 4-63 characters: lowercase letters, digits, hyphens; start with a letter; not end with a hyphen."
  }

  validation {
    condition     = var.firestore_config_database != var.firestore_database
    error_message = "FIRESTORE_CONFIG_DATABASE and FIRESTORE_DATABASE must be different databases."
  }
}
