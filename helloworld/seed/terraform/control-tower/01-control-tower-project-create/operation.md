# ControlTowerProjectCreate

## Summary
Creates the Control Tower foundation: the Control Tower folder (or uses an existing one), the Control Tower project inside it with billing linked, and the bucket that will hold all Terraform state and runner backups. Every later operation depends on this one.

## Prerequisites
- No earlier operation (this is the first one).
- Signed-in admin ${LSB_ACCOUNT} needs: Folder Creator (on ${CT_FOLDER_PARENT}), Project Creator, Billing User (on ${BILLING_ACCOUNT_ID}).
- Quota project ${QUOTA_PROJECT} has Resource Manager, Service Usage, Cloud Billing and Cloud Storage APIs enabled.

## Inputs (initialize.env)
- ORG_ID              ${ORG_ID}
- CT_FOLDER_NAME      ${CT_FOLDER_NAME}
- CT_FOLDER_PARENT    ${CT_FOLDER_PARENT}
- CT_FOLDER_ID        ${CT_FOLDER_ID}
- CT_PROJECT_ID       ${CT_PROJECT_ID}
- BILLING_ACCOUNT_ID  ${BILLING_ACCOUNT_ID}
- REGION              ${REGION}
- TF_STATE_BUCKET     ${TF_STATE_BUCKET}

## What will happen
1. Folder: ${LSB_FOLDER_MODE}
2. Create project ${CT_PROJECT_ID} in that folder (deletion policy PREVENT)
3. Link billing account ${BILLING_ACCOUNT_ID}
4. Enable the Cloud Storage API on ${CT_PROJECT_ID}
5. Create bucket gs://${TF_STATE_BUCKET} in ${REGION} (versioning on, 7-day soft delete, uniform access, public access prevented)
6. Move this operation's Terraform state from Cloud Shell into gs://${TF_STATE_BUCKET}/control-tower/01-control-tower-project-create
7. Wait until the project is ACTIVE and billing is enabled
8. Write CT_FOLDER_ID, CT_FOLDER_MANAGED and CT_PROJECT_NUMBER back to initialize.env

## Resources created or changed
- Folder "${CT_FOLDER_NAME}" (only if CT_FOLDER_ID is empty)
- Project ${CT_PROJECT_ID}
- Billing link ${CT_PROJECT_ID} -> ${BILLING_ACCOUNT_ID}
- API storage.googleapis.com on ${CT_PROJECT_ID}
- Bucket gs://${TF_STATE_BUCKET}

## Written back to initialize.env
CT_FOLDER_ID, CT_FOLDER_MANAGED, CT_PROJECT_NUMBER

## Readiness check
Project lifecycle state is ACTIVE and billing is enabled.

## Expected duration
About 1 to 3 minutes.

## Re-run behavior
Safe. The existing folder, project and bucket are kept; Terraform shows no changes when everything matches.

## Cannot be undone
The project (deletion policy PREVENT), folder (deletion protection) and bucket are protected from deletion. Project IDs and bucket names are global and cannot be reused once taken.
