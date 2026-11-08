# ControlTowerApisEnable
# Enables the baseline APIs on the Control Tower project and creates the service agents
# that later operations grant IAM roles to. APIs are never disabled (add-only).

resource "google_project_service" "apis" {
  for_each = toset(var.control_tower_apis)

  project                    = var.ct_project_id
  service                    = each.value
  disable_on_destroy         = false
  disable_dependent_services = false
}

# Service agents (e.g. service-<number>@serverless-robot-prod.iam.gserviceaccount.com for Cloud Run).
# They are created lazily by Google; creating them explicitly lets later IAM operations bind them right away.
resource "google_project_service_identity" "agents" {
  provider = google-beta
  for_each = toset(var.service_agent_services)

  project = var.ct_project_id
  service = each.value

  depends_on = [google_project_service.apis]
}
