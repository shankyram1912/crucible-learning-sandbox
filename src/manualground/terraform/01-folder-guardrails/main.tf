# FolderGuardrailsCreate
# Provisions (or attaches to) the parent Playground guardrail folder and enforces:
# 1. Managed Organization Policy boolean & domain constraints.
# 2. Single-resource-type custom Org Policy `custom.ntuDenyCloudRunGpu` blocking serverless GPUs.
# 3. Folder IAM Deny v2 policy locking down static keys and container/DB/RAG resource deletion
#    while keeping on-demand Cloud Run service workflows open for `ntu-run-auto-owner`.

locals {
  create_folder = var.mg_folder_managed || trimspace(var.mg_folder_id) == ""

  raw_folder_id = local.create_folder ? google_folder.playground[0].folder_id : trimspace(var.mg_folder_id)
  folder_num    = trimprefix(local.raw_folder_id, "folders/")
  folder_parent = "folders/${local.folder_num}"

  enforced_boolean_constraints = merge(
    {
      "iam.disableServiceAccountKeyCreation"            = true
      "iam.disableServiceAccountKeyUpload"              = true
      "iam.automaticIamGrantsForDefaultServiceAccounts" = true
      "storage.uniformBucketLevelAccess"                = true
      "storage.publicAccessPrevention"                  = true
      "sql.restrictAuthorizedNetworks"                  = true
    },
    var.require_invoker_iam ? { "run.managed.requireInvokerIam" = true } : {},
  )

  exception_principals = compact([
    trimspace(var.it_admins_group) != "" ? "principalSet://goog/group/${trimspace(var.it_admins_group)}" : "",
    trimspace(var.provisioner_sa_email) != "" ? "principal://iam.googleapis.com/projects/-/serviceAccounts/${trimspace(var.provisioner_sa_email)}" : "",
  ])
}

resource "google_folder" "playground" {
  count = local.create_folder ? 1 : 0

  display_name        = var.mg_folder_name
  parent              = var.mg_parent_folder
  deletion_protection = true
}

# Managed boolean Organization Policies inherited by all 80-student shard projects.
resource "google_org_policy_policy" "boolean_guardrails" {
  for_each = local.enforced_boolean_constraints

  name   = "${local.folder_parent}/policies/${each.key}"
  parent = local.folder_parent

  spec {
    rules {
      enforce = "TRUE"
    }
  }
}

# Domain restriction policy preventing external consumer Google accounts in IAM bindings.
resource "google_org_policy_policy" "allowed_member_domains" {
  count = trimspace(var.directory_customer_id) != "" ? 1 : 0

  name   = "${local.folder_parent}/policies/iam.allowedPolicyMemberDomains"
  parent = local.folder_parent

  spec {
    rules {
      values {
        allowed_values = [trimspace(var.directory_customer_id)]
      }
    }
  }
}

# Single-resource-type custom Org Policy blocking NVIDIA L4 / RTX GPUs on Cloud Run Services.
resource "google_org_policy_custom_constraint" "deny_cloud_run_gpu" {
  count = var.enable_org_custom_constraints ? 1 : 0

  name           = "custom.ntuDenyCloudRunGpu"
  parent         = "organizations/${var.org_id}"
  display_name   = "Deny Cloud Run GPU Accelerators in Student Playgrounds"
  description    = "Blocks NVIDIA L4 and RTX PRO 6000 GPU allocation on Cloud Run services."
  action_type    = "DENY"
  condition      = "resource.spec.template.spec.containers.exists(c, has(c.resources) && 'nvidia.com/gpu' in c.resources.limits) || (has(resource.spec.template.spec.nodeSelector) && 'run.googleapis.com/accelerator' in resource.spec.template.spec.nodeSelector)"
  method_types   = ["CREATE", "UPDATE"]
  resource_types = ["run.googleapis.com/Service"]
}

resource "google_org_policy_policy" "deny_cloud_run_gpu" {
  count = var.enable_org_custom_constraints ? 1 : 0

  name   = "${local.folder_parent}/policies/custom.ntuDenyCloudRunGpu"
  parent = local.folder_parent

  spec {
    rules {
      enforce = "TRUE"
    }
  }

  depends_on = [google_org_policy_custom_constraint.deny_cloud_run_gpu]
}

# Folder IAM Deny v2 Guardrail Policy.
resource "google_iam_deny_policy" "playground_guardrails" {
  provider = google-beta

  parent       = urlencode("cloudresourcemanager.googleapis.com/${local.folder_parent}")
  name         = "ntu-playground-folder-guardrails"
  display_name = "NTU Playground - Folder Control Plane & Keyless Guardrails"

  # Rule 1: Unconditional block on downloadable SA JSON keys and static API keys for everyone.
  rules {
    description = "Unconditionally block service account JSON keys and static API keys across all identities."
    deny_rule {
      denied_principals = ["principalSet://goog/public:all"]
      denied_permissions = [
        "iam.googleapis.com/serviceAccountKeys.create",
        "apikeys.googleapis.com/keys.create",
      ]
    }
  }

  # Rule 2: Lock bucket, SQL, Firestore, Discovery Engine, SA, custom role, and Run Job lifecycle
  # while exempting IT Admins and Layer 1/Layer 2 provisioning automation.
  rules {
    description = "Block unisolated resource creation and peer/slot container deletion outside provisioning automation."
    deny_rule {
      denied_principals    = ["principalSet://goog/public:all"]
      exception_principals = local.exception_principals
      denied_permissions   = var.denied_control_plane_permissions
    }
  }
}
