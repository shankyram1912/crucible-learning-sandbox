# Hello World Seed Data (proposal)

Status: proposed 2026-11-08. Users defined in `users.csv`, created by `create-users.sh` (not run yet). Replaces the defunct seed in `seed/backup/` (old cohort model).

## Principle
Seed only what the platform cannot create: **people** and the **tag value catalog**. Schools, Playground Folders and playgrounds are created through the Self Service API operations as test scenarios, so the seed exercises the real flows instead of bypassing them.

Domain: `shankyram.altostrat.com`. All users are Cloud Identity Free users with **no GCP roles of their own**.

## 1. Users ([users.csv](users.csv), created by [create-users.sh](create-users.sh))

| Email | Persona | Service group (seeded) | Used for |
|---|---|---|---|
| `lsb-it-admin1@` | IT Admin | `grp-lsb-it-admins@` | Tag binding test now; creates Playground Folders (API op 04) |
| `lsb-bu-biz1@` | BU Admin, Business | `grp-lsb-bu-admins@` | BU tag test now; controller of the Business Playground Folder |
| `lsb-bu-cs1@` | BU Admin, Computing | `grp-lsb-bu-admins@` | Controller of the Computing Playground Folder; isolation tests against Business |
| `lsb-owner-ba101@` | Playground owner | none | Owner of the BA 101 playground's projects |
| `lsb-owner-cs100@` | Playground owner | none | Owner of the CS 100 playground's projects |
| `lsb-student1@` to `lsb-student4@` | Student | none | Students 1 and 2 in BA 101, 3 and 4 in CS 100 (API op 06) |

Only the first three are seeded into groups. All other access comes from the platform.

## 2. Tag value catalog (`seed/catalog.csv`, loaded into Firestore)

| Key | Value | Scope (`cost-center-bu`) |
|---|---|---|
| `cost-center-bu` | `business`, `computing` | none |
| `cost-center-code` | `biz-teaching` | `business` |
| `cost-center-code` | `cs-teaching`, `cs-research` | `computing` |
| `cost-category` | `teaching`, `research` | all |

`bu-tracking-code` and `bu-subcategory` are free values (pattern only), not in the catalog. Scenarios use for example `ba101-2026`, `cs100-2026`.

## 3. Test scenarios (`seed/scenarios.md`, run through the API operations)

| School (plain folder under University Sandbox) | Playground Folder (created by IT, with controller) | Playground (created by BU Admin) | Owner |
|---|---|---|---|
| School of Business | `biz-2026` (controller `lsb-bu-biz1@`) | BA 101 Intro Analytics | `lsb-owner-ba101@` |
| School of Computing | `cs-2026` (controller `lsb-bu-cs1@`) | CS 100 Intro Programming | `lsb-owner-cs100@` |

School folders are created once by IT as setup. Negative checks:
- `lsb-bu-cs1@` cannot create anything in `biz-2026`.
- BU Admins cannot change `cost-center-*` values.
- Playground owners cannot create projects.
- Students have no folder access.

## 4. Tag binding test (needs only the first three users; can run before step 6)

Setup as admin@: scratch folder `lsb-tag-test` under University Sandbox, Tag User on it for `lsb-it-admin1@` and `lsb-bu-biz1@` (stands in for the folder-level grants from step 6 and Playground Folder creation). Users added to their groups (allow a few minutes).

| User | Bind `cost-center-bu` | Bind `bu-subcategory` | Remove IT's `cost-center-bu` binding |
|---|---|---|---|
| `lsb-it-admin1@` | expect ✅ | expect ✅ (nested in BU Admins) | n/a |
| `lsb-bu-biz1@` | expect ❌ | expect ✅ | **open question** |

Outcomes:
- All as expected: no spec change.
- IT Admin cannot bind: Tag User on the key is not enough for dynamic values; helloworld-spec section 2 needs Tag User higher up.
- BU Admin can remove IT's binding: needs an IAM deny on binding removal, or a narrower role than Tag User on Playground Folders.

Teardown: remove the bindings, the test memberships and the folder.

## Creating the users

`gcloud` has no command to create Cloud Identity or Workspace users, so [create-users.sh](create-users.sh) creates them with the **Admin SDK Directory API** (curl, token from gcloud), then adds the first three to their service group with `gcloud identity groups memberships add`. It is idempotent (existing users and memberships are skipped) and never deletes anything.

Run in Cloud Shell as a Super Admin (`admin@`):
```bash
cd ~/learning-sandbox/helloworld/src/terraform/control-tower && source ./initialize.sh   # sets QUOTA_PROJECT
cd ../../../seed

# one time: Directory API on the quota project, and an ADC token with the Directory scope
gcloud services enable admin.googleapis.com --project="$QUOTA_PROJECT"
gcloud auth application-default login --no-launch-browser \
  --scopes=https://www.googleapis.com/auth/admin.directory.user,https://www.googleapis.com/auth/cloud-platform

./create-users.sh --dry-run    # shows what it would do
./create-users.sh              # prompts once for the seed password (or set LSB_SEED_PASSWORD)
```

Notes:
- **Password:** one shared seed password, prompted (not echoed) or from `LSB_SEED_PASSWORD`; never written to disk or the repo. `changePasswordAtNextLogin` is off so test sign-ins are smooth.
- **Licences:** users go into the root org unit. If the domain auto-assigns Google Workspace licences, each user takes one; otherwise they are Cloud Identity Free users. Move them to an org unit without auto-licensing if that matters.
- **Memberships:** a just-created user can take a minute to be visible to Cloud Identity. If a membership step fails, re-run the script.
- **Re-running ADC login** replaces the ADC token used by Terraform; that is fine, as it keeps the `cloud-platform` scope.
- **Fallback:** Admin console > Directory > Users > Bulk update users, with a CSV in the Admin console format generated from `users.csv`.
- **Signing in as a test user:** incognito Cloud Shell, or `gcloud auth login <user> --no-launch-browser`.

## Open decisions (continue here)
1. Trim the set or keep all 9 users (the tag test needs only the first three).
2. Delete or keep `seed/backup/`.
3. Generate `catalog.csv` and `scenarios.md` (`users.csv` and `create-users.sh` are done).
