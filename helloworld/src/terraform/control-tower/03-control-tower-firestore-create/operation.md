# ControlTowerFirestoreCreate

## Summary
Creates the two Firestore databases of the Self Service APIs in the Control Tower project ${CT_PROJECT_ID}. ${FIRESTORE_CONFIG_DATABASE} holds config, the desired state: tag catalog, Playground Folders, playgrounds and their immutable config versions; only the API writes it and the Terraform runner reads it. ${FIRESTORE_DATABASE} holds runtime state (what exists in GCP) and jobs (jobs, tasks, locks); job history is kept indefinitely (no TTL policies). For the CLI-first MVP only service accounts read and write; a future UI adds Firebase Auth and read-only security rules without changing these databases.

## Prerequisites
- ControlTowerApisEnable is DONE (firestore.googleapis.com enabled on ${CT_PROJECT_ID}).
- Signed-in admin ${LSB_ACCOUNT} can create databases on ${CT_PROJECT_ID} (Owner or Datastore Owner).
- Quota project ${QUOTA_PROJECT} has the Firestore API enabled.

## Inputs (initialize.env)
- CT_PROJECT_ID              ${CT_PROJECT_ID}
- FIRESTORE_CONFIG_DATABASE  ${FIRESTORE_CONFIG_DATABASE}
- FIRESTORE_DATABASE         ${FIRESTORE_DATABASE}
- REGION                     ${REGION}
- TF_STATE_BUCKET            ${TF_STATE_BUCKET}

## What will happen
1. Create Firestore database ${FIRESTORE_CONFIG_DATABASE} (config) on ${CT_PROJECT_ID}:
   - type FIRESTORE_NATIVE, location ${REGION}
   - optimistic concurrency, App Engine integration disabled
   - point-in-time recovery enabled (7-day window), delete protection enabled
   - weekly backup every Sunday, kept 14 weeks
2. Create Firestore database ${FIRESTORE_DATABASE} (runtime and jobs) with the same settings (unchanged if it already exists)
3. Delete the TTL policies an earlier version of this operation created on ${FIRESTORE_DATABASE} (jobs.expireAt, tasks.expireAt), so job history is kept indefinitely
4. Store this operation's Terraform state in gs://${TF_STATE_BUCKET}/control-tower/03-control-tower-firestore-create
5. Wait until both databases are reported by Firestore

## Resources created or changed
- Firestore database projects/${CT_PROJECT_ID}/databases/${FIRESTORE_CONFIG_DATABASE} and its weekly backup schedule
- Firestore database projects/${CT_PROJECT_ID}/databases/${FIRESTORE_DATABASE}

## Written back to initialize.env
Nothing (both database IDs are already set).

## Readiness check
gcloud firestore databases describe returns both databases on ${CT_PROJECT_ID}.

## Expected duration
LONG-RUNNING on the first re-run after the TTL removal: 20 to 40 minutes, because deleting each TTL policy is a Firestore index operation of often 10 to 20 minutes (they may run one after the other). If Terraform times out (about 20 minutes per policy), the run is recorded FAILED and a re-run finishes the deletion. Progress: gcloud firestore fields ttls list --database=${FIRESTORE_DATABASE} --project=${CT_PROJECT_ID}
Otherwise about 1 to 2 minutes.

## Re-run behavior
Safe. Existing databases with the same settings show no changes.

## Cannot be undone
The location (${REGION}) cannot change after creation. Both databases are protected from deletion (delete protection + prevent_destroy). A deleted database ID cannot be reused for a period.
