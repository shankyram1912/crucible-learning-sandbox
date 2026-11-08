terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

# Cloud Identity calls need a billing/quota project: initialize.sh sets
# GOOGLE_BILLING_PROJECT + USER_PROJECT_OVERRIDE=true from QUOTA_PROJECT.
provider "google" {
  region = var.region
}
