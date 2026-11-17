output "auto_owner_service_name" {
  description = "Cloud Run v2 service name for the auto-owner reconciler."
  value       = google_cloud_run_v2_service.auto_owner.name
}

output "auto_owner_uri" {
  description = "Internal Cloud Run v2 URI of ntu-run-auto-owner."
  value       = google_cloud_run_v2_service.auto_owner.uri
}

output "auto_owner_sa_email" {
  description = "Dedicated service account email running ntu-run-auto-owner."
  value       = google_service_account.auto_owner.email
}

output "eventarc_trigger_names" {
  description = "Map of v1/v2 Eventarc CreateService trigger resource IDs."
  value       = { for k, t in google_eventarc_trigger.run_create_service : k => t.id }
}

output "eventarc_subscriptions" {
  description = "Underlying Eventarc Pub/Sub transport subscriptions updated to ack_deadline_seconds=60."
  value       = [for t in google_eventarc_trigger.run_create_service : t.transport[0].pubsub[0].subscription]
}
