# Values come from initialize.env as TF_VAR_<lowercase key> (exported by initialize.sh).

variable "ct_project_id" {
  description = "Control Tower project ID (CT_PROJECT_ID)."
  type        = string
}

variable "region" {
  description = "Default region (REGION)."
  type        = string
}

# Baseline APIs for the Control Tower's own services (day0-bootstrap-spec.md, operation 2).
# compute.googleapis.com is deliberately excluded: its first enablement creates a permissive
# default VPC. Compute and networking belong to the later networking operation.
variable "control_tower_apis" {
  description = "APIs enabled on the Control Tower project."
  type        = list(string)
  default = [
    # Platform
    "serviceusage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    # Observability
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    # Billing
    "cloudbilling.googleapis.com",
    "billingbudgets.googleapis.com",
    # Data and state
    "firestore.googleapis.com",
    "storage.googleapis.com",
    # Runtime and CI/CD
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "secretmanager.googleapis.com",
    # Identity
    "cloudidentity.googleapis.com",
    "admin.googleapis.com",
  ]

  validation {
    condition     = !contains(var.control_tower_apis, "compute.googleapis.com")
    error_message = "compute.googleapis.com must not be enabled here; it belongs to the networking operation."
  }
}

# Services whose service agents must exist before later operations grant them IAM roles.
variable "service_agent_services" {
  description = "Services for which the service agent (service identity) is created."
  type        = list(string)
  default = [
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
  ]
}
