# Values come from initialize.env as TF_VAR_<lowercase key> (exported by initialize.sh).

variable "region" {
  description = "Default region (REGION)."
  type        = string
}

variable "org_id" {
  description = "Numeric organization ID (ORG_ID)."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.org_id))
    error_message = "ORG_ID must be the numeric organization ID."
  }
}

variable "it_admins_group" {
  description = "IT Admins service group email (IT_ADMINS_GROUP). Gets Tag User on cost-center-bu, cost-center-code, cost-category."
  type        = string
}

variable "bu_admins_group" {
  description = "BU Admins service group email (BU_ADMINS_GROUP). Gets Tag User on bu-tracking-code and bu-subcategory."
  type        = string

  validation {
    condition     = var.bu_admins_group != var.it_admins_group
    error_message = "BU_ADMINS_GROUP and IT_ADMINS_GROUP must be different groups."
  }
}
