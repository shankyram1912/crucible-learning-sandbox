# ControlTowerProjectCreate
# 1. Control Tower folder: create it, or use an existing one (CT_FOLDER_ID).
# 2. Control Tower project in that folder, linked to billing.
# 3. Terraform state bucket in the project.

locals {
  # Create (and keep managing) the folder when no folder ID was given,
  # or when this operation created it on an earlier run.
  create_folder = var.ct_folder_managed || var.ct_folder_id == ""

  folder_id = local.create_folder ? google_folder.ct[0].folder_id : var.ct_folder_id

  labels = {
    managed-by = "lsb-day0"
    operation  = "control-tower-project-create"
  }
}

resource "google_folder" "ct" {
  count = local.create_folder ? 1 : 0

  display_name        = var.ct_folder_name
  parent              = var.ct_folder_parent
  deletion_protection = true
}

resource "google_project" "ct" {
  project_id      = var.ct_project_id
  name            = var.ct_project_id
  folder_id       = local.folder_id
  billing_account = var.billing_account_id
  labels          = local.labels
  deletion_policy = "PREVENT"

  lifecycle {
    prevent_destroy = true
  }
}

# Cloud Storage API is needed in the new project before the state bucket can be created.
resource "google_project_service" "storage" {
  project            = google_project.ct.project_id
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_storage_bucket" "tf_state" {
  name     = var.tf_state_bucket
  project  = google_project.ct.project_id
  location = var.region
  labels   = local.labels

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  soft_delete_policy {
    retention_duration_seconds = 604800 # 7 days
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.storage]
}
