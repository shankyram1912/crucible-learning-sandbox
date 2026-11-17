output "project_id" {
  description = "Shard project ID."
  value       = google_project.shard.project_id
}

output "project_number" {
  description = "Numeric project number of the shard project (written back to MG_PROJECT_NUMBER)."
  value       = google_project.shard.number
}

output "enabled_apis" {
  description = "Sorted list of APIs enabled on the shard project."
  value       = sort([for s in google_project_service.apis : s.service])
}

output "service_agents" {
  description = "Map of service FQDN to materialized Google-managed service agent email."
  value       = { for k, v in google_project_service_identity.agents : k => v.email }
}

output "custom_role_names" {
  description = "Map of custom_ntu_* role IDs to full projects/<id>/roles/<role_id> resource names."
  value       = { for k, v in google_project_iam_custom_role.roles : k => v.name }
}
