# Written back to initialize.env by run.sh after a successful apply.

output "tag_key_ids" {
  description = "Tag key resource names by short name, e.g. {\"cost-center-bu\" = \"tagKeys/123\"}."
  value       = { for k, v in google_tags_tag_key.playground : k => "tagKeys/${v.name}" }
}

output "value_pattern" {
  description = "Allowed-values pattern set on every playground tag key."
  value       = local.value_pattern
}
