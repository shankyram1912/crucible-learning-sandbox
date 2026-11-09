# LSB Control Tower Seed Data (proposal)

Status: proposed 2026-11-08. Users in [users.csv](users.csv) (Admin console bulk upload format). Not created yet. Replaces the defunct seed in `seed/backup/` (old cohort model).

## Principle
Seed only what the platform cannot create: **people** and the **tag value catalog**. Schools, Playground Folders and playgrounds are created through the Self Service API operations as test scenarios, so the seed exercises the real flows instead of bypassing them.

Domain: `shankyram.altostrat.com`. All users are Cloud Identity Free users with **no GCP roles of their own**.

## 1. Users ([users.csv](users.csv))

| Email | Persona | Service group (added through the platform) | Used for |
|---|---|---|---|
| `lsb-it-admin1@` | IT Admin | `grp-lsb-it-admins@` | Tag binding test now; creates Playground Folders (API op 04) |
| `lsb-bu-biz1@` | BU Admin, Business | `grp-lsb-bu-admins@` | BU tag test now; controller of the Business Playground Folder |
| `lsb-bu-cs1@` | BU Admin, Computing | `grp-lsb-bu-admins@` | Controller of the Computing Playground Folder; isolation tests against Business |
| `lsb-owner-ba101@` | Playground owner | none | Owner of the BA 101 playground's projects |
| `lsb-owner-cs100@` | Playground owner | none | Owner of the CS 100 playground's projects |
| `lsb-student1@` to `lsb-student4@` | Student | none | Students 1 and 2 in BA 101, 3 and 4 in CS 100 (API op 06) |

**The seed creates users only; it never adds group memberships.** Membership of the locked service groups is changed only by IT Admins through the platform (API op 06, `group members`); the only bootstrapped member is `IT_ADMINS_INITIAL_MEMBERS` (Day-0 step 4). All other access also comes from the platform.

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

Prerequisite: `lsb-it-admin1@` and `lsb-bu-biz1@` are in their service groups, added **through the platform** (API op 06, `group members`), so the test runs after that operation exists. Setup as admin@: scratch folder `lsb-tag-test` under University Sandbox, Tag User on it for both users (stands in for the folder-level grants from step 6 and Playground Folder creation).

| User | Bind `cost-center-bu` | Bind `bu-subcategory` | Remove IT's `cost-center-bu` binding |
|---|---|---|---|
| `lsb-it-admin1@` | expect ✅ | expect ✅ (nested in BU Admins) | n/a |
| `lsb-bu-biz1@` | expect ❌ | expect ✅ | **open question** |

Outcomes:
- All as expected: no spec change.
- IT Admin cannot bind: Tag User on the key is not enough for dynamic values; control-tower-spec section 2 needs Tag User higher up.
- BU Admin can remove IT's binding: needs an IAM deny on binding removal, or a narrower role than Tag User on Playground Folders.

Teardown: remove the bindings, the test memberships and the folder.

## Creating the users

`gcloud` cannot create Cloud Identity or Workspace users, and Google blocks gcloud's own sign-in from requesting the Admin Directory scope ("This app is blocked", verified 2026-11-09). So users are created with the **Admin console bulk upload**, and only the group memberships are scripted.

[users.csv](users.csv) keeps only the Admin console template columns we need (Directory > Users > Bulk update users): the five required ones (first name, last name, email, password, org unit `/`), Employee Title (persona) and Change Password at Next Sign-In (`False`). Header names must match the template exactly; optional columns can be left out. If an upload is ever rejected for missing columns, use the full template header instead. **The Password column is empty in the repo**; fill it in a copy outside the repo just before uploading:

```bash
cd ~/learning-sandbox/seed
read -r -s -p "Seed password (min 8 chars): " PW; echo
awk -F, -v OFS=, -v pw="$PW" 'NR>1{$4=pw}1' users.csv > ~/lsb-users-upload.csv; unset PW
# Admin console > Directory > Users > Bulk update users > upload ~/lsb-users-upload.csv
# after the upload completes:
rm ~/lsb-users-upload.csv
```

Group memberships are **not** part of the seed: IT Admins add them through the platform (API op 06).

Notes:
- **Licences:** users go into the root org unit. If the domain auto-assigns Google Workspace licences, each user takes one; otherwise they are Cloud Identity Free users.
- **Repeatable alternative:** an own OAuth desktop client (consent screen Internal) with `gcloud auth application-default login --client-id-file=...` would allow the Directory API from a script. Not needed for a one-off seed.
- **Signing in as a test user:** incognito Cloud Shell, or `gcloud auth login <user> --no-launch-browser`.

## Open decisions (continue here)
1. Trim the set or keep all 9 users (the tag test needs only the first three).
2. Delete or keep `seed/backup/`.
3. Generate `catalog.csv` and `scenarios.md` (`users.csv` is done).
4. Tag binding test timing: it now needs API op 06 for the memberships; move it before API op 04 in the to-do list.
