terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

# Quota/billing project for API calls comes from the environment set by initialize.sh
# (GOOGLE_BILLING_PROJECT + USER_PROJECT_OVERRIDE=true).
provider "google" {
  region = var.region
}
