# PlaygroundTagsCreate

## Summary
Creates the five playground tag keys at organization level as dynamic tags: cost-center-bu, cost-center-code, cost-category, bu-tracking-code and bu-subcategory. Each key accepts any value that matches the pattern ^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$, so no tag values are created up front. Allowed values for cost-center-bu, cost-center-code and cost-category live in the Firestore catalog and are checked by the Self Service APIs before binding. IT Admins (${IT_ADMINS_GROUP}) get Tag User on those three keys; BU Admins (${BU_ADMINS_GROUP}) get Tag User on bu-tracking-code and bu-subcategory, which are free values within the pattern. The tags are bound on Playground Folders and playgrounds later, never on the Control Tower.

## Prerequisites
- PlaygroundGroupsCreate is DONE (both groups exist).
- Signed-in admin ${LSB_ACCOUNT} can create tag keys and set their IAM policy on organizations/${ORG_ID} (Tag Administrator or Organization Administrator).
- Quota project ${QUOTA_PROJECT} has the Cloud Resource Manager API enabled.

## Inputs (initialize.env)
- ORG_ID            ${ORG_ID}
- IT_ADMINS_GROUP   ${IT_ADMINS_GROUP}
- BU_ADMINS_GROUP   ${BU_ADMINS_GROUP}
- TF_STATE_BUCKET   ${TF_STATE_BUCKET}

## What will happen
1. Create tag key ${ORG_ID}/cost-center-bu with the allowed-values pattern
2. Create tag key ${ORG_ID}/cost-center-code with the allowed-values pattern
3. Create tag key ${ORG_ID}/cost-category with the allowed-values pattern
4. Create tag key ${ORG_ID}/bu-tracking-code with the allowed-values pattern
5. Create tag key ${ORG_ID}/bu-subcategory with the allowed-values pattern
6. Grant Tag User on cost-center-bu, cost-center-code and cost-category to group ${IT_ADMINS_GROUP}
7. Grant Tag User on bu-tracking-code and bu-subcategory to group ${BU_ADMINS_GROUP}
8. Store this operation's Terraform state in gs://${TF_STATE_BUCKET}/control-tower/05-playground-tags-create
9. Check all five keys exist with the pattern and the Tag User grants are in place
10. Write the five tag key IDs back to initialize.env

## Resources created or changed
- 5 tag keys under organizations/${ORG_ID} (no tag values)
- 5 IAM bindings (Tag User) on those keys

## Written back to initialize.env
TAG_KEY_COST_CENTER_BU_ID, TAG_KEY_COST_CENTER_CODE_ID, TAG_KEY_COST_CATEGORY_ID, TAG_KEY_BU_TRACKING_CODE_ID, TAG_KEY_BU_SUBCATEGORY_ID

## Readiness check
All five keys are found under organizations/${ORG_ID} with the allowed-values pattern, and each key's IAM policy shows the expected group as Tag User.

## Expected duration
Under a minute.

## Re-run behavior
Safe. Existing keys and grants are kept. Nothing is bound to any folder or project.

## Cannot be undone
Tag key short names are reserved in the organization while the key exists. The keys are protected from deletion by Terraform (prevent_destroy). Grants are additive and do not replace other Tag User grants on the keys.
