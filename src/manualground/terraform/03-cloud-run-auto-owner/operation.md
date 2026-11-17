# CloudRunAutoOwnerCreate

## Summary
Deploys `ntu-run-auto-owner` (pure-stdlib Python 3.12 CloudEvent receiver on Cloud Run v2 with `<250ms` cold start, `INGRESS_TRAFFIC_INTERNAL_ONLY`, `concurrency=20`, `max_instance_count=5`, `timeout=60s`) plus regional Eventarc Cloud Audit Log triggers (`v1` and `v2` `Services.CreateService`) with Pub/Sub `ack_deadline_seconds=60`.

## Prerequisites
- `ShardProjectCreate` is `DONE` (`MG_PROJECT_ID`, `MG_PROJECT_NUMBER`, and `custom_ntu_run_owner` exist).

## Inputs (initialize.env)
- MG_PROJECT_ID             ${MG_PROJECT_ID}
- MG_PROJECT_NUMBER         ${MG_PROJECT_NUMBER}
- REGION                    ${REGION}
- MAX_SERVICES_PER_STUDENT  ${MAX_SERVICES_PER_STUDENT}

## LONG-RUNNING Operation Notice (~5 to 15 minutes, 20m timeout)
Eventarc Cloud Audit Log triggers (`ntu-run-auto-owner-create-v1` and `ntu-run-auto-owner-create-v2`) routinely take **5 to 15 minutes** to provision Pub/Sub transport subscriptions and propagate audit-log routing rules. Terraform sets explicit `20m` timeouts.

Watch progress from a second terminal while `apply` runs:
  watch -n 10 "gcloud eventarc triggers list --location=${REGION} --project=${MG_PROJECT_ID}"
  gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="ntu-run-auto-owner"' --project=${MG_PROJECT_ID} --limit=20

## Expected duration
About 6 to 15 minutes (dominated by Eventarc audit-log trigger propagation).
