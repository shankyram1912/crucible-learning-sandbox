# ControlTowerApisEnable

## Summary
Enables the baseline APIs on the Control Tower project ${CT_PROJECT_ID} that its own services need (Self Service APIs on Cloud Run, Firestore, CI/CD, identity, billing), and creates the service agents that later operations grant IAM roles to. The Compute API is deliberately not enabled; it belongs to the later networking operation.

## Prerequisites
- ControlTowerProjectCreate is DONE (project ${CT_PROJECT_ID} exists, billing enabled, state bucket gs://${TF_STATE_BUCKET}).
- Signed-in admin ${LSB_ACCOUNT} can enable services on ${CT_PROJECT_ID} (Owner or Service Usage Admin).
- Quota project ${QUOTA_PROJECT} has the Service Usage API enabled.

## Inputs (initialize.env)
- CT_PROJECT_ID       ${CT_PROJECT_ID}
- CT_PROJECT_NUMBER   ${CT_PROJECT_NUMBER}
- TF_STATE_BUCKET     ${TF_STATE_BUCKET}
- REGION              ${REGION}

## What will happen
1. Enable on ${CT_PROJECT_ID}:
   - Platform: serviceusage, cloudresourcemanager, iam, iamcredentials
   - Observability: logging, monitoring
   - Billing: cloudbilling, billingbudgets
   - Data and state: firestore, storage
   - Runtime and CI/CD: run, artifactregistry, cloudbuild, secretmanager
   - Identity: cloudidentity, admin (Directory API)
2. Create the service agents for Cloud Run, Cloud Build and Artifact Registry
3. Store this operation's Terraform state in gs://${TF_STATE_BUCKET}/control-tower/02-control-tower-apis-enable
4. Wait until every API above shows ENABLED

## Resources created or changed
- 16 API enablements on ${CT_PROJECT_ID}
- 3 service agents (Cloud Run, Cloud Build, Artifact Registry)

## Written back to initialize.env
Nothing.

## Readiness check
Every listed API is ENABLED on ${CT_PROJECT_ID}. Also warns if compute.googleapis.com has become enabled (it would create a default VPC).

## Expected duration
About 1 to 3 minutes.

## Re-run behavior
Safe. Already enabled APIs show no changes. Adding an API to the list enables only that API.

## Cannot be undone
APIs are never disabled by this operation (disable_on_destroy = false), in line with "an enabled service is never disabled".
