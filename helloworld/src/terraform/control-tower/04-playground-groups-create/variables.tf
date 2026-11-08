# Values come from initialize.env as TF_VAR_<lowercase key> (exported by initialize.sh).

variable "region" {
  description = "Default region (REGION)."
  type        = string
}

variable "directory_customer_id" {
  description = "Workspace / Cloud Identity customer ID, e.g. C03ccny1h (DIRECTORY_CUSTOMER_ID)."
  type        = string

  validation {
    condition     = can(regex("^C[0-9a-z]+$", var.directory_customer_id))
    error_message = "DIRECTORY_CUSTOMER_ID must look like C0xxxxxxx."
  }
}

variable "domain" {
  description = "Primary domain of the org (DOMAIN)."
  type        = string
}

variable "it_admins_group" {
  description = "IT Admins service group email (IT_ADMINS_GROUP)."
  type        = string
}

variable "bu_admins_group" {
  description = "BU Admins service group email (BU_ADMINS_GROUP)."
  type        = string

  validation {
    condition     = var.bu_admins_group != var.it_admins_group
    error_message = "BU_ADMINS_GROUP and IT_ADMINS_GROUP must be different groups."
  }
}
