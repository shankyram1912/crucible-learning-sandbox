output "database" {
  description = "Firestore database resource name."
  value       = google_firestore_database.ct.id
}

output "location" {
  description = "Firestore database location."
  value       = google_firestore_database.ct.location_id
}
