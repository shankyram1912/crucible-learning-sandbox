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
  description = "Firestore database ID (FIRESTORE_DATABASE)."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,61}[a-z0-9]$", var.firestore_database))
    error_message = "FIRESTORE_DATABASE must be 4-63 characters: lowercase letters, digits, hyphens; start with a letter; not end with a hyphen."
  }
}

variable "billing_labels" {
  description = "Billing labels from initialize.env LABEL_* keys (built by initialize.sh). Applied as provider default_labels."
  type        = map(string)
  default     = {}

  validation {
    condition = alltrue([
      for k, v in var.billing_labels :
      can(regex("^[a-z][a-z0-9_-]{0,62}$", k)) && can(regex("^[a-z0-9_-]{0,63}$", v))
    ])
    error_message = "Billing label keys must start with a lowercase letter; keys and values may use lowercase letters, digits, '-' and '_' (max 63 characters)."
  }
}
