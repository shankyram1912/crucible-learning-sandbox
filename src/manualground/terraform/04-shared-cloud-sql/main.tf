# SharedCloudSqlCreate
# Provisions one shared Cloud SQL for PostgreSQL 16 instance (`sql-<project>`) per 80-student shard
# when `ENABLE_CLOUD_SQL=true`, enforcing passwordless IAM DB authentication (`cloudsql.iam_authentication=on`)
# and encrypted mTLS connections (`ssl_mode=ENCRYPTED_ONLY`) with zero public IP allowlist CIDRs.

locals {
  is_prod       = var.mg_preset == "prod"
  instance_name = trimspace(var.mg_sql_instance) != "" ? trimspace(var.mg_sql_instance) : "sql-${var.mg_project_id}"

  user_labels = merge(
    {
      managed-by = "manualground"
      operation  = "shared-cloud-sql"
      preset     = var.mg_preset
    },
    var.billing_labels,
  )
}

# LONG-RUNNING: Cloud SQL for PostgreSQL 16 instance creation and HA standby setup take 10-25 minutes
# (up to 35-40 minutes for REGIONAL HA failover initialization). Explicit 45m timeouts prevent false failures.
resource "google_sql_database_instance" "shared" {
  count = var.enable_cloud_sql ? 1 : 0

  name                = local.instance_name
  project             = var.mg_project_id
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = local.is_prod

  settings {
    edition                     = "ENTERPRISE"
    tier                        = local.is_prod ? "db-custom-4-16384" : "db-custom-2-8192"
    availability_type           = local.is_prod ? "REGIONAL" : "ZONAL"
    disk_type                   = "PD_SSD"
    disk_size                   = local.is_prod ? 100 : 20
    disk_autoresize             = true
    deletion_protection_enabled = local.is_prod
    user_labels                 = local.user_labels

    # Enable passwordless Cloud SQL IAM DB authentication and bound total backend connections
    # (80 students * 8 connections/student = 640 peak in prod, leaving 160 slots for postgres/autovacuum).
    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    database_flags {
      name  = "max_connections"
      value = local.is_prod ? "800" : "200"
    }

    # Public IP with zero authorized_networks + ENCRYPTED_ONLY requires all student/workload
    # connections to traverse Cloud SQL Auth Proxy or Python Connector over IAM-authenticated mTLS.
    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      start_time                     = "19:00"
      point_in_time_recovery_enabled = local.is_prod
    }
  }

  timeouts {
    create = "45m"
    update = "45m"
    delete = "45m"
  }
}
