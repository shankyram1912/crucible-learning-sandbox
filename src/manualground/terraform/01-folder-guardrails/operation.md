# FolderGuardrailsCreate

## Summary
Creates (or attaches to) the parent Playground guardrail folder (`fld-ntu-playground`) and enforces inherited Organization Policy constraints plus the Folder IAM Deny v2 policy across every child 80-student shard project.

## Prerequisites
- Signed-in admin ${MG_ACCOUNT} holds Organization Policy Administrator (`roles/orgpolicy.policyAdmin`), IAM Deny Admin (`roles/iam.denyAdmin`), and Folder Creator/Admin on ${MG_PARENT_FOLDER}.
- Quota project ${QUOTA_PROJECT} has Resource Manager, Organization Policy, and IAM APIs enabled.

## Inputs (initialize.env)
- ORG_ID                 ${ORG_ID}
- MG_PARENT_FOLDER       ${MG_PARENT_FOLDER}
- MG_FOLDER_NAME         ${MG_FOLDER_NAME}
- MG_FOLDER_ID           ${MG_FOLDER_ID}
- DIRECTORY_CUSTOMER_ID  ${DIRECTORY_CUSTOMER_ID}
- IT_ADMINS_GROUP        ${IT_ADMINS_GROUP}
- PROVISIONER_SA_EMAIL   ${PROVISIONER_SA_EMAIL}

## What will happen
1. Create folder "${MG_FOLDER_NAME}" under ${MG_PARENT_FOLDER} (or reuse ${MG_FOLDER_ID} if already set).
2. Enforce managed boolean Org Policies (`disableServiceAccountKeyCreation`, `disableServiceAccountKeyUpload`, `automaticIamGrantsForDefaultServiceAccounts`, `uniformBucketLevelAccess`, `publicAccessPrevention`, `restrictAuthorizedNetworks`, `requireInvokerIam`).
3. Enforce `iam.allowedPolicyMemberDomains` (when DIRECTORY_CUSTOMER_ID is set) and custom constraint `custom.ntuDenyCloudRunGpu` on `run.googleapis.com/Service`.
4. Attach Folder IAM Deny v2 policy `ntu-playground-folder-guardrails` (keeping on-demand Cloud Run service creation/per-service owner deletion open for `ntu-run-auto-owner` while blocking Cloud Run Jobs, static keys, and container deletion across GCS, Cloud SQL, Firestore, Discovery Engine, and SAs).
5. Write `MG_FOLDER_ID` and `MG_FOLDER_MANAGED` back to `initialize.env`.

## Expected duration
About 1 to 2 minutes (note: IAM Deny v2 and Org Policy cache propagation takes ~60-120 seconds globally).
