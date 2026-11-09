# PlaygroundGroupsCreate
# Two security groups for the playground service, IT Admins nested in BU Admins.
# Not locked (decided 2026-11-09): the platform never changes membership; people with directory rights do,
# and the groups have no owners or managers, so only Super Admins / Groups Admins can change them anyway.
# Initial IT Admin users are added by run.sh after apply (membership is data, not Terraform).

locals {
  # discussion_forum: required for Google Groups; security: usable in IAM / security-sensitive;
  group_labels = {
    "cloudidentity.googleapis.com/groups.discussion_forum" = ""
    "cloudidentity.googleapis.com/groups.security"         = ""
  }
}

resource "google_cloud_identity_group" "it_admins" {
  parent               = "customers/${var.directory_customer_id}"
  display_name         = "LSB IT Admins"
  description          = "Learning Sandbox IT Admins: configure Playground Folders; only they change membership of the LSB service groups. Managed by the platform."
  initial_group_config = "EMPTY" # no human becomes group owner

  group_key {
    id = var.it_admins_group
  }

  labels = local.group_labels

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_cloud_identity_group" "bu_admins" {
  parent               = "customers/${var.directory_customer_id}"
  display_name         = "LSB BU Admins"
  description          = "Learning Sandbox BU Admins: configure playgrounds in the Playground Folders they control. IT Admins are nested. Managed by the platform."
  initial_group_config = "EMPTY"

  group_key {
    id = var.bu_admins_group
  }

  labels = local.group_labels

  lifecycle {
    prevent_destroy = true
  }
}

# Structure: every IT Admin is also a BU Admin.
resource "google_cloud_identity_group_membership" "it_admins_in_bu_admins" {
  group = google_cloud_identity_group.bu_admins.id

  preferred_member_key {
    id = var.it_admins_group
  }

  roles {
    name = "MEMBER"
  }

  create_ignore_already_exists = true

  depends_on = [google_cloud_identity_group.it_admins]
}
