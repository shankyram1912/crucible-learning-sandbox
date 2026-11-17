# Values come from initialize.env as TF_VAR_<lowercase key> (exported by initialize.sh).

variable "mg_project_id" {
  description = "Shard project ID (MG_PROJECT_ID)."
  type        = string
}

variable "mg_project_number" {
  description = "Numeric shard project number written by ShardProjectCreate (MG_PROJECT_NUMBER)."
  type        = string
}

variable "region" {
  description = "Primary shard region where ntu-run-auto-owner and Eventarc triggers run (REGION)."
  type        = string
  default     = "asia-southeast1"
}

variable "max_services_per_student" {
  description = "Maximum concurrent Cloud Run services each student may own before auto-deletion (MAX_SERVICES_PER_STUDENT)."
  type        = number
  default     = 3
}

variable "ack_deadline_seconds" {
  description = "Pub/Sub subscription acknowledgement deadline (seconds) for 80-student classroom deployment bursts."
  type        = number
  default     = 60
}

variable "auto_owner_service_name" {
  description = "Cloud Run v2 service name for the Eventarc auto-owner receiver."
  type        = string
  default     = "ntu-run-auto-owner"
}

variable "auto_owner_image" {
  description = "Pure-stdlib Python 3.12 container image (<250ms cold start, zero pip install at boot)."
  type        = string
  default     = "mirror.gcr.io/library/python:3.12-slim"
}

variable "ignored_principals" {
  description = "Optional comma-separated admin/instructor user emails ignored by ntu-run-auto-owner."
  type        = string
  default     = ""
}
