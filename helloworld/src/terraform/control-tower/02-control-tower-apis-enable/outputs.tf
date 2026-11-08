output "enabled_apis" {
  description = "APIs managed by this operation."
  value       = sort([for s in google_project_service.apis : s.service])
}

output "service_agents" {
  description = "Service agent emails created by this operation, by service."
  value       = { for k, v in google_project_service_identity.agents : k => v.email }
}
