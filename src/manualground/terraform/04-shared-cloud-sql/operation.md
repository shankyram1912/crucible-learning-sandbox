# SharedCloudSqlCreate

## Summary
Provisions the shared Cloud SQL for PostgreSQL 16 instance (`${MG_SQL_INSTANCE}`) when `ENABLE_CLOUD_SQL=true`, configured with `cloudsql.iam_authentication=on`, `ssl_mode=ENCRYPTED_ONLY`, zero `0.0.0.0/0` authorized networks, and sizing controlled by `MG_PRESET` (`dev` zonal vs `prod` regional HA with `max_connections=800`).

## Prerequisites
- `ShardProjectCreate` is `DONE` (`sqladmin.googleapis.com` enabled on `${MG_PROJECT_ID}`).

## Inputs (initialize.env)
- MG_PROJECT_ID     ${MG_PROJECT_ID}
- REGION            ${REGION}
- MG_PRESET         ${MG_PRESET}
- ENABLE_CLOUD_SQL  ${ENABLE_CLOUD_SQL}
- MG_SQL_INSTANCE   ${MG_SQL_INSTANCE}

## LONG-RUNNING Operation Notice (~10 to 25 minutes, 45m timeout)
Cloud SQL for PostgreSQL 16 instance creation takes **10 to 15 minutes** in `dev` (`ZONAL`) and **15 to 25 minutes** in `prod` (`REGIONAL` HA standby initialization). Terraform configures explicit `45m` `create`/`update`/`delete` timeouts. Set `ENABLE_CLOUD_SQL=false` in `initialize.env` if a cohort module does not use PostgreSQL.

Watch progress from a second terminal while `apply` runs:
  watch -n 15 "gcloud sql operations list --instance=${MG_SQL_INSTANCE} --project=${MG_PROJECT_ID} --limit=5"
  gcloud sql instances describe ${MG_SQL_INSTANCE} --project=${MG_PROJECT_ID} --format="table(name,state,gceZone,settings.tier,settings.availabilityType)"

## Written back to initialize.env
MG_SQL_INSTANCE (when `ENABLE_CLOUD_SQL=true`)

## Expected duration
About 10 to 25 minutes when `ENABLE_CLOUD_SQL=true` (under 5 seconds when `ENABLE_CLOUD_SQL=false`).
