output "database" {
  description = "Firestore database for runtime state and jobs (resource name)."
  value       = google_firestore_database.ct.id
}

output "config_database" {
  description = "Firestore database for config (resource name)."
  value       = google_firestore_database.config.id
}

output "location" {
  description = "Firestore location of both databases."
  value       = google_firestore_database.ct.location_id
}
