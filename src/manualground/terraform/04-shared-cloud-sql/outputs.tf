output "sql_instance_enabled" {
  description = "Whether the shared Cloud SQL instance is enabled (ENABLE_CLOUD_SQL)."
  value       = var.enable_cloud_sql
}

output "sql_instance_name" {
  description = "Cloud SQL instance name (empty when ENABLE_CLOUD_SQL=false)."
  value       = var.enable_cloud_sql ? google_sql_database_instance.shared[0].name : ""
}

output "sql_connection_name" {
  description = "project:region:instance connection string for Cloud SQL Auth Proxy / Python Connector."
  value       = var.enable_cloud_sql ? google_sql_database_instance.shared[0].connection_name : ""
}

output "sql_preset" {
  description = "Applied sizing preset (dev or prod)."
  value       = var.mg_preset
}
