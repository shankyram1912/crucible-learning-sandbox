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

  # Job history expires through a TTL policy on this field (the API sets it when it creates a job or task).
  ttl_field             = "expireAt"
  ttl_collection_groups = ["jobs", "tasks"]
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

# TTL policies on the runtime + jobs database: documents in jobs and tasks are deleted after expireAt.
resource "google_firestore_field" "ttl" {
  for_each = toset(local.ttl_collection_groups)

  project    = var.ct_project_id
  database   = google_firestore_database.ct.name
  collection = each.key
  field      = local.ttl_field

  ttl_config {}
}
