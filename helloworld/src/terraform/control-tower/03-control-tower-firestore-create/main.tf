# ControlTowerFirestoreCreate
# Firestore (Native mode) database for the Self Service APIs: jobs, tasks, playgrounds, cohorts.
# Server-side access only for the CLI-first MVP; a future UI adds Firebase Auth + read-only rules.

resource "google_firestore_database" "ct" {
  project     = var.ct_project_id
  name        = var.firestore_database
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  concurrency_mode                  = "OPTIMISTIC"
  app_engine_integration_mode       = "DISABLED"
  point_in_time_recovery_enablement = "POINT_IN_TIME_RECOVERY_ENABLED"
  delete_protection_state           = "DELETE_PROTECTION_ENABLED"
  deletion_policy                   = "ABANDON"

  lifecycle {
    prevent_destroy = true
  }
}
