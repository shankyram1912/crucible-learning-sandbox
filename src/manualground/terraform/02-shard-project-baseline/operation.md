# ShardProjectCreate

## Summary
Creates an 80-student shared Playground shard project inside `${MG_FOLDER_ID}`, links billing, enables all required APIs (keeping `compute.googleapis.com` disabled), materializes Google-managed Service Agents (including `gcp-sa-eventarc` and `gcp-sa-discoveryengine`), and defines all 9 least-privilege `custom_ntu_*` IAM roles.

## Prerequisites
- `FolderGuardrailsCreate` is `DONE` (`MG_FOLDER_ID` is populated in `initialize.env`).
- Signed-in admin ${MG_ACCOUNT} holds Project Creator on `folders/${MG_FOLDER_ID}` and Billing User on `${BILLING_ACCOUNT_ID}`.

## Inputs (initialize.env)
- MG_FOLDER_ID         ${MG_FOLDER_ID}
- MG_PROJECT_ID        ${MG_PROJECT_ID}
- BILLING_ACCOUNT_ID   ${BILLING_ACCOUNT_ID}
- REGION               ${REGION}
- STUDENT_GROUP_EMAIL  ${STUDENT_GROUP_EMAIL}
- TF_STATE_BUCKET      ${TF_STATE_BUCKET}

## Resources created or changed
- Project `${MG_PROJECT_ID}` with billing linked and `LABEL_*` attribution labels
- 16 baseline Google Cloud APIs + 8 eagerly materialized P4SA service identities
- `roles/eventarc.serviceAgent` and `roles/run.serviceAgent` readiness bindings
- All 9 custom roles: `custom_ntu_gemini_caller`, `custom_ntu_gcs_bucket_metadata_viewer`, `custom_ntu_gcs_console_lister`, `custom_ntu_run_creator`, `custom_ntu_run_owner`, `custom_ntu_sql_connect`, `custom_ntu_firestore_db_user`, `custom_ntu_firestore_project_browser`, `custom_ntu_vertex_search_console`
- Non-authoritative project IAM grants for `group:${STUDENT_GROUP_EMAIL}` (when configured)
- Optional Terraform state bucket `gs://${TF_STATE_BUCKET}`

## Written back to initialize.env
MG_PROJECT_NUMBER

## Expected duration
About 2 to 4 minutes.
