# ControlTowerFirestoreCreate
# Two Firestore (Native mode) databases for the Self Service APIs (helloworld-spec 1.9):
#   - FIRESTORE_CONFIG_DATABASE: config (desired state): tag catalog, Playground Folders, playgrounds,
#     immutable config versions. Written only by the API; the Terraform runner reads it.
#   - FIRESTORE_DATABASE: runtime (observed state) and jobs (jobs, tasks, locks). Written by the API
#     and the runner.
# Server-side access only for the CLI-first MVP; a future UI adds Firebase Auth + read-only rules.

locals {
  database_settings = {
    type                              = "FIRESTORE_NATIVE"
    concurrency_mode                  = "OPTIMISTIC"
    app_engine_integration_mode       = "DISABLED"
    point_in_time_recovery_enablement = "POINT_IN_TIME_RECOVERY_ENABLED"
    delete_protection_state           = "DELETE_PROTECTION_ENABLED"
  }

  # Weekly backups of config, kept 14 weeks (the maximum). PITR already covers the last 7 days.
  config_backup_retention = "8467200s"
}

# Runtime + jobs (existing database, unchanged).
resource "google_firestore_database" "ct" {
  project     = var.ct_project_id
  name        = var.firestore_database
  location_id = var.region

  type                              = local.database_settings.type
  concurrency_mode                  = local.database_settings.concurrency_mode
  app_engine_integration_mode       = local.database_settings.app_engine_integration_mode
  point_in_time_recovery_enablement = local.database_settings.point_in_time_recovery_enablement
  delete_protection_state           = local.database_settings.delete_protection_state
  deletion_policy                   = "ABANDON"

  lifecycle {
    prevent_destroy = true
  }
}

# Config (desired state).
resource "google_firestore_database" "config" {
  project     = var.ct_project_id
  name        = var.firestore_config_database
  location_id = var.region

  type                              = local.database_settings.type
  concurrency_mode                  = local.database_settings.concurrency_mode
  app_engine_integration_mode       = local.database_settings.app_engine_integration_mode
  point_in_time_recovery_enablement = local.database_settings.point_in_time_recovery_enablement
  delete_protection_state           = local.database_settings.delete_protection_state
  deletion_policy                   = "ABANDON"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_firestore_backup_schedule" "config_weekly" {
  project   = var.ct_project_id
  database  = google_firestore_database.config.name
  retention = local.config_backup_retention

  weekly_recurrence {
    day = "SUNDAY"
  }
}

# Job history is kept indefinitely: no TTL policies (helloworld-spec 1.9). The TTL policies created by an
# earlier version of this operation (google_firestore_field.ttl["jobs"], ["tasks"]) are no longer in this
# configuration, so the next apply destroys them, which disables TTL on jobs.expireAt and tasks.expireAt.
# LONG-RUNNING: each deletion is a Firestore index operation, often 10-20 minutes. Their delete timeout is
# the provider default (about 20 minutes, recorded in state when they were created); if it is exceeded,
# run.sh records FAILED and a re-run finishes the deletion.
