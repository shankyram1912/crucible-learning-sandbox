# PlaygroundTagsCreate
# Five dynamic playground tag keys at org level. No tag values are created: any value matching
# the pattern can be bound directly. Allowed values for the IT-governed keys live in the Firestore
# catalog and are checked by the Self Service APIs before binding (tdd-master 1.8).

locals {
  # One value format for tags and labels: starts with a letter, lowercase letters, digits and
  # hyphens, ends with a letter or digit, max 63 characters (valid as a tag value and a label value).
  value_pattern = "^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$"

  tag_keys = {
    "cost-center-bu" = {
      description = "Learning Sandbox billing: school or business unit. Values from the LSB catalog, bound on Playground Folders by IT Admins. Managed by the platform."
      tag_user    = var.it_admins_group
    }
    "cost-center-code" = {
      description = "Learning Sandbox billing: cost center code. Values from the LSB catalog, bound on Playground Folders by IT Admins. Managed by the platform."
      tag_user    = var.it_admins_group
    }
    "cost-category" = {
      description = "Learning Sandbox billing: cost category. Values from the LSB catalog, bound on Playground Folders by IT Admins. Managed by the platform."
      tag_user    = var.it_admins_group
    }
    "bu-tracking-code" = {
      description = "Learning Sandbox billing: BU tracking code (for example grant, project or course code) under the school's cost center. Free value, default on the Playground Folder, overridable per playground by BU Admins. Managed by the platform."
      tag_user    = var.bu_admins_group
    }
    "bu-subcategory" = {
      description = "Learning Sandbox billing: BU subcategory. Free value, default on the Playground Folder, overridable per playground by BU Admins. Managed by the platform."
      tag_user    = var.bu_admins_group
    }
  }
}

resource "google_tags_tag_key" "playground" {
  for_each = local.tag_keys

  parent               = "organizations/${var.org_id}"
  short_name           = each.key
  description          = each.value.description
  allowed_values_regex = local.value_pattern

  lifecycle {
    prevent_destroy = true
  }
}

# Who may bind each key. Additive only (iam_member), never authoritative.
resource "google_tags_tag_key_iam_member" "tag_user" {
  for_each = local.tag_keys

  tag_key = google_tags_tag_key.playground[each.key].name
  role    = "roles/resourcemanager.tagUser"
  member  = "group:${each.value.tag_user}"
}
