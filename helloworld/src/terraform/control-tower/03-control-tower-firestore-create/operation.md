# ControlTowerFirestoreCreate

## Summary
Creates the Firestore database ${FIRESTORE_DATABASE} in the Control Tower project ${CT_PROJECT_ID}. The Self Service APIs store playgrounds, cohorts, jobs and tasks here. For the CLI-first MVP only the API's service account reads and writes it; a future UI adds Firebase Auth and read-only security rules without changing this database.

## Prerequisites
- ControlTowerApisEnable is DONE (firestore.googleapis.com enabled on ${CT_PROJECT_ID}).
- Signed-in admin ${LSB_ACCOUNT} can create databases on ${CT_PROJECT_ID} (Owner or Datastore Owner).
- Quota project ${QUOTA_PROJECT} has the Firestore API enabled.

## Inputs (initialize.env)
- CT_PROJECT_ID       ${CT_PROJECT_ID}
- FIRESTORE_DATABASE  ${FIRESTORE_DATABASE}
- REGION              ${REGION}
- TF_STATE_BUCKET     ${TF_STATE_BUCKET}

## What will happen
1. Create Firestore database ${FIRESTORE_DATABASE} on ${CT_PROJECT_ID}:
   - type FIRESTORE_NATIVE, location ${REGION}
   - optimistic concurrency, App Engine integration disabled
   - point-in-time recovery enabled (7-day window)
   - delete protection enabled
2. Store this operation's Terraform state in gs://${TF_STATE_BUCKET}/control-tower/03-control-tower-firestore-create
3. Wait until the database is reported by Firestore

## Resources created or changed
- Firestore database projects/${CT_PROJECT_ID}/databases/${FIRESTORE_DATABASE}

## Written back to initialize.env
Nothing (FIRESTORE_DATABASE is already set).

## Readiness check
gcloud firestore databases describe --database=${FIRESTORE_DATABASE} --project=${CT_PROJECT_ID} returns the database.

## Expected duration
About 1 minute.

## Re-run behavior
Safe. An existing database with the same settings shows no changes.

## Cannot be undone
The location (${REGION}) cannot change after creation. The database is protected from deletion (delete protection + prevent_destroy). A deleted database ID cannot be reused for a period.
