# Written back to initialize.env by run.sh after a successful apply.

output "folder_id" {
  description = "Control Tower folder ID (CT_FOLDER_ID)."
  value       = local.folder_id
}

output "folder_managed" {
  description = "Whether this operation created and manages the folder (CT_FOLDER_MANAGED)."
  value       = local.create_folder
}

output "project_id" {
  description = "Control Tower project ID."
  value       = google_project.ct.project_id
}

output "project_number" {
  description = "Control Tower project number (CT_PROJECT_NUMBER)."
  value       = google_project.ct.number
}

output "tf_state_bucket" {
  description = "Terraform state bucket."
  value       = google_storage_bucket.tf_state.name
}
