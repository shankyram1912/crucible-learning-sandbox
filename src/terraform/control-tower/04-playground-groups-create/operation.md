# PlaygroundGroupsCreate

## Summary
Creates the two playground service groups as security groups (not locked): ${IT_ADMINS_GROUP} (IT Admins, configure Playground Folders and manage membership of both groups) and ${BU_ADMINS_GROUP} (BU Admins, configure playgrounds). IT Admins are nested in BU Admins. Membership is managed outside the platform by people with directory rights (Admin console); the groups have no owners or managers. Runs before the tag operations, which grant these groups Tag User.

## Prerequisites
- ControlTowerFirestoreCreate is DONE (state bucket gs://${TF_STATE_BUCKET} exists).
- Signed-in admin ${LSB_ACCOUNT} is a Super Admin or Groups Admin in ${DOMAIN}.
- Quota project ${QUOTA_PROJECT} has the Cloud Identity API enabled.

## Inputs (initialize.env)
- DIRECTORY_CUSTOMER_ID      ${DIRECTORY_CUSTOMER_ID}
- DOMAIN                     ${DOMAIN}
- IT_ADMINS_GROUP            ${IT_ADMINS_GROUP}
- BU_ADMINS_GROUP            ${BU_ADMINS_GROUP}
- IT_ADMINS_INITIAL_MEMBERS  ${IT_ADMINS_INITIAL_MEMBERS}
- TF_STATE_BUCKET            ${TF_STATE_BUCKET}

## What will happen
1. Create group ${IT_ADMINS_GROUP} ("LSB IT Admins") under customers/${DIRECTORY_CUSTOMER_ID}: security label, no owner
2. Create group ${BU_ADMINS_GROUP} ("LSB BU Admins") the same way
3. Add ${IT_ADMINS_GROUP} as a member of ${BU_ADMINS_GROUP} (every IT Admin is a BU Admin)
4. Store this operation's Terraform state in gs://${TF_STATE_BUCKET}/control-tower/04-playground-groups-create
5. Add the initial IT Admins (${IT_ADMINS_INITIAL_MEMBERS}) to ${IT_ADMINS_GROUP}
6. Check both groups exist and the nesting is in place
7. Write IT_ADMINS_GROUP_ID and BU_ADMINS_GROUP_ID back to initialize.env

## Resources created or changed
- Cloud Identity group ${IT_ADMINS_GROUP}
- Cloud Identity group ${BU_ADMINS_GROUP}
- Membership ${IT_ADMINS_GROUP} in ${BU_ADMINS_GROUP}
- Memberships of the initial IT Admins in ${IT_ADMINS_GROUP} (outside Terraform)

## Written back to initialize.env
IT_ADMINS_GROUP_ID, BU_ADMINS_GROUP_ID

## Readiness check
Both groups are found, ${IT_ADMINS_GROUP} is a member of ${BU_ADMINS_GROUP}.

## Expected duration
Under a minute.

## Re-run behavior
Safe. Existing groups and memberships are kept; initial members already present are skipped.

## Cannot be undone
The security label cannot be removed from a group once set. The groups are protected from deletion by Terraform (prevent_destroy).
