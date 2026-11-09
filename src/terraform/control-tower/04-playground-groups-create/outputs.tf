# Written back to initialize.env by run.sh after a successful apply.

output "it_admins_group_id" {
  description = "Cloud Identity resource name of the IT Admins group (IT_ADMINS_GROUP_ID)."
  value       = google_cloud_identity_group.it_admins.name
}

output "bu_admins_group_id" {
  description = "Cloud Identity resource name of the BU Admins group (BU_ADMINS_GROUP_ID)."
  value       = google_cloud_identity_group.bu_admins.name
}
