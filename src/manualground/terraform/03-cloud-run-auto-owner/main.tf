# CloudRunAutoOwnerCreate
# Deploys the pure-stdlib Python 3.12 CloudEvent receiver (`ntu-run-auto-owner`) on Cloud Run v2
# (`INGRESS_TRAFFIC_INTERNAL_ONLY`, concurrency=20, max_instance_count=5, timeout=60s) and binds
# regional Eventarc Cloud Audit Log triggers for BOTH Cloud Run v1 and v2 `CreateService` calls.

locals {
  labels = {
    managed-by = "manualground"
    operation  = "cloud-run-auto-owner"
  }

  eventarc_methods = {
    v1 = "google.cloud.run.v1.Services.CreateService"
    v2 = "google.cloud.run.v2.Services.CreateService"
  }

  pubsub_service_agent   = "service-${var.mg_project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"
  eventarc_service_agent = "service-${var.mg_project_number}@gcp-sa-eventarc.iam.gserviceaccount.com"
}

# Dedicated runtime identity for ntu-run-auto-owner (students have zero actAs on this SA).
resource "google_service_account" "auto_owner" {
  project      = var.mg_project_id
  account_id   = "sa-run-auto-owner"
  display_name = "NTU Cloud Run Auto-Owner Reconciler"
  description  = "Privileged reconciler binding custom_ntu_run_owner and enforcing MAX_SERVICES_PER_STUDENT."
}

# Dedicated delivery identity used exclusively by Eventarc push subscriptions.
resource "google_service_account" "eventarc_invoker" {
  project      = var.mg_project_id
  account_id   = "sa-eventarc-invoker"
  display_name = "NTU Eventarc Auto-Owner Invoker"
  description  = "Delivers Cloud Run CreateService CloudEvents from Eventarc to ntu-run-auto-owner."
}

resource "google_project_iam_member" "auto_owner_run_admin" {
  project = var.mg_project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.auto_owner.email}"
}

resource "google_project_iam_member" "auto_owner_log_writer" {
  project = var.mg_project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.auto_owner.email}"
}

resource "google_project_iam_member" "eventarc_receiver" {
  project = var.mg_project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.eventarc_invoker.email}"
}

resource "google_project_iam_member" "eventarc_agent_ready" {
  project = var.mg_project_id
  role    = "roles/eventarc.serviceAgent"
  member  = "serviceAccount:${local.eventarc_service_agent}"
}

# Allow Pub/Sub service agent to mint OIDC push tokens as sa-eventarc-invoker.
resource "google_service_account_iam_member" "pubsub_token_creator" {
  service_account_id = google_service_account.eventarc_invoker.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${local.pubsub_service_agent}"
}

resource "google_cloud_run_v2_service" "auto_owner" {
  name                = var.auto_owner_service_name
  location            = var.region
  project             = var.mg_project_id
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = false
  labels              = local.labels

  template {
    service_account                  = google_service_account.auto_owner.email
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    max_instance_request_concurrency = 20
    timeout                          = "60s"

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image   = var.auto_owner_image
      command = ["python3", "-u", "-c"]
      args = [
        "import base64, os, pathlib, runpy; p = pathlib.Path('/tmp/auto_owner.py'); p.write_bytes(base64.b64decode(os.environ['AUTO_OWNER_SOURCE_B64'])); runpy.run_path(str(p), run_name='__main__')"
      ]

      env {
        name  = "MG_PROJECT_ID"
        value = var.mg_project_id
      }
      env {
        name  = "DEFAULT_REGION"
        value = var.region
      }
      env {
        name  = "AUTO_OWNER_SERVICE_NAME"
        value = var.auto_owner_service_name
      }
      env {
        name  = "MAX_SERVICES_PER_STUDENT"
        value = tostring(var.max_services_per_student)
      }
      env {
        name  = "IGNORED_PRINCIPALS"
        value = var.ignored_principals
      }
      env {
        name  = "AUTO_OWNER_SOURCE_B64"
        value = filebase64("${path.module}/auto_owner.py")
      }

      resources {
        cpu_idle          = true
        startup_cpu_boost = true
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }

  depends_on = [
    google_project_iam_member.auto_owner_run_admin,
    google_project_iam_member.auto_owner_log_writer,
  ]
}

# Only sa-eventarc-invoker holds run.invoker on ntu-run-auto-owner (zero student access).
resource "google_cloud_run_v2_service_iam_member" "eventarc_invoker" {
  project  = google_cloud_run_v2_service.auto_owner.project
  location = google_cloud_run_v2_service.auto_owner.location
  name     = google_cloud_run_v2_service.auto_owner.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.eventarc_invoker.email}"
}

# LONG-RUNNING: Eventarc Cloud Audit Log triggers take 5-15 minutes to provision Pub/Sub transport
# topics/subscriptions and propagate regional audit-log routing rules across run.googleapis.com.
resource "google_eventarc_trigger" "run_create_service" {
  for_each = local.eventarc_methods

  name            = "ntu-run-auto-owner-create-${each.key}"
  location        = var.region
  project         = var.mg_project_id
  service_account = google_service_account.eventarc_invoker.email
  labels          = local.labels

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.audit.log.v1.written"
  }
  matching_criteria {
    attribute = "serviceName"
    value     = "run.googleapis.com"
  }
  matching_criteria {
    attribute = "methodName"
    value     = each.value
  }

  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.auto_owner.name
      region  = var.region
      path    = "/"
    }
  }

  timeouts {
    create = "20m"
    update = "20m"
    delete = "20m"
  }

  depends_on = [
    google_cloud_run_v2_service_iam_member.eventarc_invoker,
    google_project_iam_member.eventarc_receiver,
    google_project_iam_member.eventarc_agent_ready,
    google_service_account_iam_member.pubsub_token_creator,
  ]
}

# Raise the Eventarc-managed Pub/Sub transport subscription ack_deadline_seconds to 60s
# so simultaneous 80-student classroom deployment bursts never suffer 10s ack timeouts.
resource "terraform_data" "eventarc_pubsub_ack_deadline" {
  for_each = google_eventarc_trigger.run_create_service

  input = {
    project              = var.mg_project_id
    subscription         = each.value.transport[0].pubsub[0].subscription
    ack_deadline_seconds = var.ack_deadline_seconds
  }

  provisioner "local-exec" {
    command = "gcloud pubsub subscriptions update '${self.input.subscription}' --project='${self.input.project}' --ack-deadline=${self.input.ack_deadline_seconds} --min-retry-delay=10s --max-retry-delay=60s"
  }
}
