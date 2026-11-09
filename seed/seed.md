# LSB Control Tower Seed Data (proposal)

Status: proposed 2026-11-08. Users in [users.csv](users.csv) (Admin console bulk upload format), **created 2026-11-09**. Groups in [groups.csv](groups.csv) and memberships in [memberships.csv](memberships.csv), created by [create-groups.sh](create-groups.sh) (not run yet). Catalog and scenarios not created yet.

## Principle
Seed only what the platform does not create: **people**, **groups and their memberships** (the platform never writes to the directory), and the **tag value catalog**. Schools, Playground Folders and playgrounds are created through the Self Service API operations as test scenarios, so the seed exercises the real flows instead of bypassing them.

Domain: `shankyram.altostrat.com`. All users are Cloud Identity Free users with **no GCP roles of their own**.

## 1. Users ([users.csv](users.csv))

| Email | Persona | Groups (seeded, see section 1.1) | Used for |
|---|---|---|---|
| `lsb-it-admin1@` | IT Admin | `grp-lsb-it-admins@` | Tag binding test now; creates Playground Folders (API op 06) |
| `lsb-bu-biz1@` | BU Admin, Business | `grp-lsb-bu-admins@` | BU tag test now; controller of the Business Playground Folder |
| `lsb-bu-cs1@` | BU Admin, Computing | `grp-lsb-bu-admins@` | Controller of the Computing Playground Folder; isolation tests against Business |
| `lsb-owner-ba101@` | Playground owner | none | Owner of the BA 101 playground's projects |
| `lsb-owner-cs100@` | Playground owner | none | Owner of the CS 100 playground's projects |
| `lsb-student1@` to `lsb-student4@` | Student | none | Students 1 and 2 in BA 101, 3 and 4 in CS 100 (API op 08) |

**Users, groups and memberships are created by an IT Admin with directory rights (a person), never by the platform**, matching how the university manages its directory. The platform only reads groups; playground admins later **map** the student groups to playground slots.

### 1.1 Groups and memberships ([groups.csv](groups.csv), [memberships.csv](memberships.csv))

| Group | Kind | Members (seeded) | Used for |
|---|---|---|---|
| `grp-lsb-it-admins@` | Service (Day-0 step 4; skipped if present) | `admin@` (Day-0), `lsb-it-admin1@` | `IT_ADMIN` persona |
| `grp-lsb-bu-admins@` | Service (Day-0 step 4; skipped if present) | `grp-lsb-it-admins@` (nested, Day-0), `lsb-bu-biz1@`, `lsb-bu-cs1@` | `BU_ADMIN` and `PLATFORM_ADMIN` personas |
| `grp-ba101-students@` | Students (stands in for a school-managed group) | `lsb-student1@`, `lsb-student2@` | Mapped to the BA 101 playground `students` slot |
| `grp-cs100-students@` | Students | `lsb-student2@`, `lsb-student3@`, `lsb-student4@` | Mapped to the CS 100 playground `students` slot |

`lsb-student2@` is in both student groups, to test a user in several playgrounds ("which playgrounds am I in"). Playground owners stay individual users. New groups are security groups with no owner.

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

Prerequisite: `lsb-it-admin1@` and `lsb-bu-biz1@` are in their service groups (seeded by `create-groups.sh`, section 1.1), so the test can run now.

| User | Bind `cost-center-bu` | Bind `bu-subcategory` | Remove IT's `cost-center-bu` binding |
|---|---|---|---|
| `lsb-it-admin1@` | expect ✅ | expect ✅ (nested in BU Admins) | n/a |
| `lsb-bu-biz1@` | expect ❌ | expect ✅ | **open question** |

Outcomes:
- All as expected: no spec change.
- IT Admin cannot bind: Tag User on the key is not enough for dynamic values; tdd-master section 2 needs Tag User higher up.
- BU Admin can remove IT's binding: needs an IAM deny on binding removal, or a narrower role than Tag User on Playground Folders.

Teardown: remove the bindings, the test memberships and the folder.

## Creating the users

`gcloud` cannot create Cloud Identity or Workspace users, and Google blocks gcloud's own sign-in from requesting the Admin Directory scope ("This app is blocked", verified 2026-11-09). So users are created with the **Admin console bulk upload**, and only the group memberships are scripted.

[users.csv](users.csv) keeps only the Admin console template columns we need (Directory > Users > Bulk update users): the five required ones (first name, last name, email, password, org unit `/`), Employee Title (persona) and Change Password at Next Sign-In (`False`). Header names must match the template exactly; optional columns can be left out. If an upload is ever rejected for missing columns, use the full template header instead. **The Password column is empty in the repo** (public repo); [make-upload-csv.sh](make-upload-csv.sh) fills it in a copy outside the repo just before uploading:

```bash
cd ~/git/learning-sandbox/seed            # Cloud Shell clone path
export LSB_SEED_PASSWORD='...'            # or leave unset to be prompted (not echoed)
./make-upload-csv.sh                      # writes ~/lsb-users-upload.csv (mode 600, outside the repo)
unset LSB_SEED_PASSWORD
# Admin console > Directory > Users > Bulk update users > upload ~/lsb-users-upload.csv
# after the upload completes:
rm ~/lsb-users-upload.csv
```

[make-upload-csv.sh](make-upload-csv.sh) fills the Password column from `LSB_SEED_PASSWORD` (or a prompt), refuses to write inside the repo, and rejects passwords shorter than 8 characters or containing a comma. Setting the variable with `export` leaves it in your shell history; prefix the line with a space (if `HISTCONTROL` ignores spaces) or use the prompt to avoid that.

### Creating the groups and memberships
Run as an IT Admin with directory rights (Super Admin or Groups Admin), signed in to `gcloud` as yourself:
```bash
cd ~/git/learning-sandbox/seed            # or ~/work/code/learning-sandbox/seed on Cloudtop
./create-groups.sh
```
[create-groups.sh](create-groups.sh) reads `DIRECTORY_CUSTOMER_ID` and `QUOTA_PROJECT` from `initialize.env`, creates missing groups (security label, no owner), adds missing memberships (a member reached through nesting counts as present), and never deletes anything. Re-run it if a membership fails right after a group or user was created.

Notes:
- **Licences:** users go into the root org unit. If the domain auto-assigns Google Workspace licences, each user takes one; otherwise they are Cloud Identity Free users.
- **Repeatable alternative:** an own OAuth desktop client (consent screen Internal) with `gcloud auth application-default login --client-id-file=...` would allow the Directory API from a script. Not needed for a one-off seed.
- **Signing in as a test user:** incognito Cloud Shell, or `gcloud auth login <user> --no-launch-browser`.

## Open decisions (continue here)
1. Trim the set or keep all 9 users (the tag test needs only the first three).
2. Delete or keep `seed/backup/`.
3. Generate `catalog.csv` and `scenarios.md` (`users.csv`, `groups.csv`, `memberships.csv` are done).
4. Tag binding test: memberships are added in the Admin console, so it no longer waits for an API operation.
