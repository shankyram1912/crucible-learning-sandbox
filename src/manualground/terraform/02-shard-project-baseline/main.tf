# ShardProjectCreate
# 1. Creates the 80-student shared project shard inside MG_FOLDER_ID with billing & attribution labels.
# 2. Enables all baseline APIs and eagerly materializes Google-managed Service Agents (P4SAs).
# 3. Defines all 9 least-privilege custom IAM roles (`custom_ntu_*`).
# 4. Binds shared project-level custom roles to `group:<STUDENT_GROUP_EMAIL>` (non-authoritative `iam_member`
#    so Layer 2 `ProjectIamCoalescer` conditional bindings are never overwritten).

locals {
  folder_num = trimprefix(trimspace(var.mg_folder_id), "folders/")

  base_labels = {
    managed-by = "manualground"
    operation  = "shard-project-baseline"
  }

  # All 9 verified custom roles across the 6 playground services.
  custom_roles = {
    custom_ntu_gemini_caller = {
      title       = "NTU Playground Gemini Caller"
      description = "Stateless Gemini publisher model inference, embeddings, token counting, and Console studio access without training, tuning, or endpoint creation."
      permissions = [
        "aiplatform.endpoints.predict",
        "resourcemanager.projects.get",
        "serviceusage.services.get",
        "serviceusage.services.list",
        "serviceusage.services.use",
      ]
    }
    custom_ntu_gcs_bucket_metadata_viewer = {
      title       = "NTU Playground Bucket Metadata Viewer"
      description = "Read-only bucket metadata inspection on a student's own pre-provisioned bucket for Cloud Console direct URLs and SDK get_bucket() calls."
      permissions = [
        "storage.buckets.get",
      ]
    }
    custom_ntu_gcs_console_lister = {
      title       = "NTU Playground Console Bucket Lister"
      description = "Lists bucket names in Cloud Console without granting bucket metadata or object access on peer buckets."
      permissions = [
        "resourcemanager.projects.get",
        "storage.buckets.list",
      ]
    }
    custom_ntu_run_creator = {
      title       = "NTU Playground Cloud Run On-Demand Creator"
      description = "On-demand Cloud Run service creation and mid-deploy LRO polling without project-level update or delete rights."
      permissions = [
        "resourcemanager.projects.get",
        "run.locations.get",
        "run.locations.list",
        "run.operations.get",
        "run.services.create",
        "run.services.get",
        "run.services.list",
        "artifactregistry.locations.get",
        "artifactregistry.locations.list",
      ]
    }
    custom_ntu_run_owner = {
      title       = "NTU Playground Cloud Run Per-Service Owner"
      description = "Per-service revision rollout, update, deletion, and HTTP invocation bound strictly on services created by the owning student."
      permissions = [
        "run.services.get",
        "run.services.update",
        "run.services.delete",
        "run.services.getIamPolicy",
        "run.configurations.get",
        "run.revisions.get",
        "run.revisions.list",
        "run.revisions.delete",
        "run.routes.get",
        "run.routes.invoke",
        "run.operations.get",
      ]
    }
    custom_ntu_sql_connect = {
      title       = "NTU Playground Cloud SQL IAM Connector & Login"
      description = "Authorizes mTLS Connector/Proxy tunneling and passwordless IAM DB login without user/DB enumeration or instance mutation."
      permissions = [
        "cloudsql.instances.connect",
        "cloudsql.instances.get",
        "cloudsql.instances.login",
      ]
    }
    custom_ntu_firestore_db_user = {
      title       = "NTU Firestore Student Database User"
      description = "Scoped document CRUD, queries, vector/composite index management, and index LRO status on a single named Firestore database."
      permissions = [
        "datastore.databases.get",
        "datastore.databases.getMetadata",
        "datastore.entities.allocateIds",
        "datastore.entities.create",
        "datastore.entities.delete",
        "datastore.entities.get",
        "datastore.entities.list",
        "datastore.entities.update",
        "datastore.indexes.create",
        "datastore.indexes.delete",
        "datastore.indexes.get",
        "datastore.indexes.list",
        "datastore.indexes.update",
        "datastore.operations.get",
        "datastore.operations.list",
        "datastore.statistics.get",
        "datastore.statistics.list",
      ]
    }
    custom_ntu_firestore_project_browser = {
      title       = "NTU Firestore Project Metadata Browser"
      description = "Allows listing database IDs and regions at the project node without reading or modifying documents."
      permissions = [
        "datastore.databases.list",
        "datastore.locations.get",
        "datastore.locations.list",
        "resourcemanager.projects.get",
      ]
    }
    custom_ntu_vertex_search_console = {
      title       = "NTU Playground Vertex Search Console & Restricted Access"
      description = "Project-level Cloud Console bootstrap and filtered resource listing for isolated per-student Discovery Engine apps and data stores."
      permissions = [
        "discoveryengine.aclConfigs.get",
        "discoveryengine.collections.get",
        "discoveryengine.collections.list",
        "discoveryengine.dataStores.list",
        "discoveryengine.devToolsConfigs.get",
        "discoveryengine.engines.list",
        "discoveryengine.locations.buildAuthorizationUrl",
        "discoveryengine.locations.getConnectorSource",
        "discoveryengine.locations.listConnectorSources",
        "discoveryengine.projects.get",
        "resourcemanager.projects.get",
        "serviceusage.services.get",
        "serviceusage.services.list",
        "serviceusage.services.use",
      ]
    }
  }

  # Project-level custom roles granted unconditionally to group:<STUDENT_GROUP_EMAIL> when set.
  student_group_project_roles = [
    "custom_ntu_gemini_caller",
    "custom_ntu_gcs_console_lister",
    "custom_ntu_run_creator",
    "custom_ntu_sql_connect",
    "custom_ntu_firestore_project_browser",
    "custom_ntu_vertex_search_console",
  ]
}

resource "google_project" "shard" {
  project_id      = var.mg_project_id
  name            = var.mg_project_id
  folder_id       = local.folder_num
  billing_account = var.billing_account_id
  labels          = merge(local.base_labels, var.billing_labels)
  deletion_policy = var.project_deletion_policy
}

resource "google_project_service" "apis" {
  for_each = toset(var.shard_apis)

  project                    = google_project.shard.project_id
  service                    = each.value
  disable_on_destroy         = false
  disable_dependent_services = false
}

resource "google_project_service_identity" "agents" {
  provider = google-beta
  for_each = toset(var.service_agent_services)

  project = google_project.shard.project_id
  service = each.value

  depends_on = [google_project_service.apis]
}

# Pre-bind Eventarc Service Agent role on the shard project so 03-cloud-run-auto-owner
# triggers validate IAM readiness without propagation errors.
resource "google_project_iam_member" "eventarc_service_agent" {
  project = google_project.shard.project_id
  role    = "roles/eventarc.serviceAgent"
  member  = "serviceAccount:${google_project_service_identity.agents["eventarc.googleapis.com"].email}"
}

resource "google_project_iam_member" "run_service_agent" {
  project = google_project.shard.project_id
  role    = "roles/run.serviceAgent"
  member  = "serviceAccount:${google_project_service_identity.agents["run.googleapis.com"].email}"
}

# Optional remote Terraform state & status backup bucket inside the shard project.
resource "google_storage_bucket" "tf_state" {
  count = trimspace(var.tf_state_bucket) != "" ? 1 : 0

  name     = trimspace(var.tf_state_bucket)
  project  = google_project.shard.project_id
  location = var.region
  labels   = local.base_labels

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  soft_delete_policy {
    retention_duration_seconds = 604800
  }

  depends_on = [google_project_service.apis]
}

# All 9 least-privilege custom IAM roles defined at the shard project level.
resource "google_project_iam_custom_role" "roles" {
  for_each = local.custom_roles

  project     = google_project.shard.project_id
  role_id     = each.key
  title       = each.value.title
  description = each.value.description
  stage       = "GA"
  permissions = each.value.permissions

  depends_on = [google_project_service.apis]
}

# Non-authoritative cohort group grants (consumes 1 principal entry per role in root policy).
resource "google_project_iam_member" "student_group_baseline" {
  for_each = trimspace(var.student_group_email) != "" ? toset(local.student_group_project_roles) : toset([])

  project = google_project.shard.project_id
  role    = google_project_iam_custom_role.roles[each.key].name
  member  = "group:${trimspace(var.student_group_email)}"
}
