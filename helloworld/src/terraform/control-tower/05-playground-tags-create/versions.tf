terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source = "hashicorp/google"
      # allowed_values_regex on google_tags_tag_key needs google provider 7.20 or later.
      # Operations 1-4 stay on ~> 6.0; each operation has its own root and state.
      version = "~> 8.0"
    }
  }
}

# Calls are billed to QUOTA_PROJECT: initialize.sh sets GOOGLE_BILLING_PROJECT + USER_PROJECT_OVERRIDE=true.
provider "google" {
  region = var.region
}
