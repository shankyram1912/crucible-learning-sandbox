output "folder_id" {
  description = "Numeric ID of the Playground guardrail folder."
  value       = local.folder_num
}

output "folder_resource_name" {
  description = "Full folders/<ID> resource name of the Playground guardrail folder."
  value       = local.folder_parent
}

output "folder_managed" {
  description = "Whether this Terraform stack created and owns the Playground folder."
  value       = local.create_folder
}

output "deny_policy_name" {
  description = "Folder IAM Deny v2 policy resource name."
  value       = google_iam_deny_policy.playground_guardrails.name
}
