# LSB Control Tower: To-Do List

Tracks the build sequence for the LSB Control Tower. Specs: [tdd-master.md](specs/02-tdd/tdd-master.md), [tdd-control-tower-master.md](specs/02-tdd/tdd-control-tower/tdd-control-tower-master.md), [tdd-apis-master.md](specs/02-tdd/tdd-apis/tdd-apis-master.md), [tdd-playground-master.md](specs/02-tdd/tdd-playground/tdd-playground-master.md).

---

## 1. Day-0 Control Tower bootstrap

| # | Operation | Status | Notes |
|---|---|---|---|
| 1 | `ControlTowerProjectCreate` | ✅ Done (2026-11-08) | Folder "Control Tower" under University Sandbox, project `lsb-control-tower-e26`, billing, state bucket |
| 2 | `ControlTowerApisEnable` | ✅ Done (2026-11-08) | 16 baseline APIs, service agents (Cloud Run, Cloud Build, Artifact Registry); no Compute |
| 3 | `ControlTowerFirestoreCreate` | ✅ Done (2026-11-08) | Firestore Native `lsb-control-tower-db`, asia-southeast1, PITR, delete protection |
| 3a | Re-run `ControlTowerProjectCreate` to apply billing labels | ✅ Done (2026-11-08) | Project `lsb-control-tower-e26` labeled `cost-center-bu=central-it`, `cost-center` / `category` / `subcategory` = `lsb-control-tower` (1 in-place change; ops 2 and 3 unchanged) |
| 3b | Enable Cloud Billing export to BigQuery | ⏭️ Skipped (2026-11-08) | Skipped because this is a dev environment. Manual Console step; enable it in a production setup to report costs by label |
| 3c | Re-run `ControlTowerProjectCreate` to rename billing labels | ✅ Done (2026-11-08) | Align the Control Tower labels with the playground tag key names: `cost-center` → `cost-center-code`, `category` → `cost-category`, `subcategory` → `bu-subcategory` (rename the three `LABEL_*` keys in `initialize.env`), and add `bu-tracking-code`. New values: `cost-center-code=it-shared`, `cost-category=learning-sandbox`, `bu-tracking-code=it-100-1001`, `bu-subcategory=lsb-control-tower`. Expected plan: 1 in-place change on the project; the three old labels are removed, four labels added, `cost-center-bu=central-it` unchanged |
| 3d | Re-run `ControlTowerFirestoreCreate` to add the config database | ✅ Done (2026-11-09) | Add `FIRESTORE_CONFIG_DATABASE=lsb-control-tower-config-db` to `initialize.env`. Expected plan: 4 to add (config database `lsb-control-tower-config-db`, weekly backup schedule, TTL on `jobs.expireAt` and `tasks.expireAt` in `lsb-control-tower-db`, later removed, see 3e), existing database unchanged. Spec: tdd-master 1.9, tdd-control-tower-master step 3 |
| 3e | Remove the TTL policies (keep job history forever) | ✅ Done (2026-11-09) | Re-run `ControlTowerFirestoreCreate`. Expected plan: 0 to add, 0 to change, **2 to destroy** (`google_firestore_field.ttl["jobs"]`, `["tasks"]`). LONG-RUNNING: 20 to 40 minutes; if Terraform times out, re-run to finish. Check with `gcloud firestore fields ttls list --database=lsb-control-tower-db --project=lsb-control-tower-e26` |
| 4 | `PlaygroundGroupsCreate` | ✅ Done (2026-11-08) | Both groups created (first as locked security groups, locked label accepted through Terraform; to be unlocked, see 4a). Creates `grp-lsb-it-admins@` and `grp-lsb-bu-admins@` as security groups (Terraform, `initial_group_config = EMPTY`, no human owners), nests it-admins in bu-admins (Terraform), adds `IT_ADMINS_INITIAL_MEMBERS` (Cloud Identity API in post-apply hook). Runs before the tag step, which grants Tag User to these groups. Spec: tdd-control-tower-master step 4 |
| 4a | Re-run `PlaygroundGroupsCreate` to unlock the two groups | ⬜ To do (coded) | Decided 2026-11-09: the platform never changes group membership (people with directory rights do, in the Admin console), so the locked label is removed. Expected plan: 2 in-place changes (labels). If the API refuses to remove the label, unlock in the Admin console (Groups > group > Group settings) and re-run |
| 5 | `PlaygroundTagsCreate` | ✅ Done (2026-11-08) | Five **dynamic** playground tag keys at org level: `cost-center-bu`, `cost-center-code`, `cost-category`, `bu-tracking-code`, `bu-subcategory`, each with the allowed-values pattern `^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$`, so no tag values are created in GCP. Grants **Tag User on `cost-center-bu`, `cost-center-code`, `cost-category` to `grp-lsb-it-admins@`** and **on `bu-tracking-code` and `bu-subcategory` to `grp-lsb-bu-admins@`**. Allowed values for the three IT-governed keys live in the Firestore catalog, checked by the API before binding. Terraform only: `google_tags_tag_key.allowed_values_regex` exists from google provider 7.20 (verified 2026-11-08: absent in 7.10, present in 7.20, 8.0, 8.10), so this operation pins `~> 8.0` in its own `versions.tf`; ops 1-4 stay on `~> 6.0`. **Tag binding check passed (2026-11-09)**, on a throwaway folder with Tag User granted on it to both groups (simulating step 6), using test users with no org-level roles: `lsb-it-admin1@` bound `cost-center-bu` and `bu-tracking-code` (via nesting); `Bad_Value` was rejected by GCP's pattern check (`INVALID_ARGUMENT`); `lsb-bu-biz1@` bound `bu-subcategory` and was denied `cost-category` (`PERMISSION_DENIED`, checked on the tag key). So Tag User on a dynamic key plus Tag User on the folder is enough; for dynamic values GCP checks the tag side on the key. A second run covered the full matrix (5 keys × IT and BU Admin): IT Admins bound all five, BU Admins only the two BU keys. Test bindings, grants and folders removed. Spec: [tdd-tags-labels-master.md](specs/02-tdd/tdd-tags-labels/tdd-tags-labels-master.md) Not applied to the Control Tower. Needs Tag Admin at org level. Spec: tdd-master 1.8 |
| 6 | `ControlTowerIdentityCreate` | ⬜ To design (section 3) | Service accounts and least-privilege IAM |
| 6a | Playground project hook | ⬜ To do (after step 6) | For every project in a playground (platform- or Console-created): copies the effective playground tags onto the project as labels, and binds the playground owners as `roles/owner`. Event-driven (project-creation audit log → function in the Control Tower); re-tag / owner-change jobs update all projects. Spec: tdd-master 1.8 rule 5, 2.5 |
| 6b | Shared Terraform runner core | ⬜ To do | Extract `run.sh`'s plan/apply/readiness/retry/trap/lock/status logic into one core used by Day-0 and the playground pipeline. Spec: tdd-playground-master 6 |
| 6c | Plan policy gate | ⬜ To do (before the first real playground) | `terraform plan` JSON → policy check (no deletes/replaces of protected resources, nothing outside the playground). Spec: tdd-playground-master 4.1 |
| 7 | `ControlTowerRegistryCreate` | ⬜ To do | Artifact Registry Docker repo `lsb`, cleanup policy |
| 8 | `ControlTowerApiServiceCreate` | ⬜ To do | Cloud Run service for the Self Service APIs (placeholder image, runs as `sa-lsb-api`, env from `initialize.env`) |
| 9 | `ControlTowerPipelinesCreate` | ⬜ To do | Cloud Build GitHub connection (one manual GitHub App authorization), build trigger, deploy to Cloud Run |
| 10 | `ControlTowerNetworkCreate` | ⬜ To do | Access model for university-wide access, Compute, remove default network, load balancer / Cloud Armor if needed |
| 11 | `PlaygroundGuardrailsCreate` | ⬜ To do | Org policies, IAM deny rules and custom roles on the playground root |

---

## 2. Self Service APIs (after Day-0 step 6)

Built one operation at a time per [tdd-apis-master.md](specs/02-tdd/tdd-apis/tdd-apis-master.md) section 4: write the operation in its domain spec (`specs/02-tdd/tdd-apis/tdd-apis-<domain>.md`), implement in API and CLI, test live, mark done. The API first runs locally against the real Firestore (ADC), so it does not wait for steps 7 to 9.

| # | Operation | Status |
|---|---|---|
| 01 | `health api` (`GET /v1/health/api`, `lsb health api`): the API process is up, no dependencies (liveness). Spec: [tdd-apis-health.md](specs/02-tdd/tdd-apis/tdd-apis-health.md) | ✅ Done (2026-11-09) |
| 02 | `health db` (`GET /v1/health/db`, `lsb health db`): one small read on each Firestore database (`lsb-control-tower-config-db`, `lsb-control-tower-db`) with a short timeout; reports status and latency per database. Spec: [tdd-apis-health.md](specs/02-tdd/tdd-apis/tdd-apis-health.md) | ✅ Done (2026-11-09) |
| 03 | `health service` (`GET /v1/health/service`, `lsb health service`): same data check as health db, answered only as `OK` / `NOT_OK` for the service, `config` and `runtime_jobs`; no database IDs, latency or error codes. Spec: [tdd-apis-health.md](specs/02-tdd/tdd-apis/tdd-apis-health.md) | ✅ Done (2026-11-09) |
| 04 | `platform roles` (`GET /v1/platform-users/me/roles` and `/{email}/roles`, `lsb platform-users roles [EMAIL]`): every role held (USER, BU_ADMIN, IT_ADMIN, PLATFORM_ADMIN) from the in-memory admin roster (members of the settings groups, direct or nested; loaded at startup, refreshed every 5 minutes). Spec: [tdd-apis-platform-users.md](specs/02-tdd/tdd-apis/tdd-apis-platform-users.md) | ✅ Done (2026-11-09) |
| 04a | Live test of `LSB_ROLE_CHECK_USE_CACHE=false`: restart the API with it set (`--no-tmux`, so the variable reaches the process), run `lsb health db` as an admin and check the API log shows `admin roster refreshed for <email>: ...`; `lsb health api`, `lsb health service` and `lsb platform-users roles` log no refresh line. Spec: [tdd-apis-platform-users.md](specs/02-tdd/tdd-apis/tdd-apis-platform-users.md) section 1 rule 6 | ✅ Done (2026-11-09) |
| 05 | `jobs` (list, show, watch) | ⬜ To do |
| 06 | `templates` (list, show) | ⬜ To do |
| 07 | `playground-folder create` / list / show (creation gate, controllers, playground tags) | ⬜ To do |
| 08 | `playground create` (creation gate, owners, bu-tracking-code, bu-subcategory, template, N projects). **Come back to platform users here:** `lsb platform-users roles lsb-student1@...` shows `USER` with no groups, because the roles answer only lists admin groups from settings and students are never cached. Decide how non-admin groups (course groups such as `grp-ba101-students@`, mapped to playground slots) are read and shown: a live `GET /v1/platform-users/{email}/groups` (+ `/me/groups`) via `DirectoryReader.user_groups`, or inside the playground operations; and how student and playground role checks work. See [tdd-apis-platform-users.md](specs/02-tdd/tdd-apis/tdd-apis-platform-users.md) section 1 rule 2 | ⬜ To do |
| 09 | `service enable` (GCS) | ⬜ To do |

---

## 3. Step 6 in detail: `ControlTowerIdentityCreate` (to design)

Access model: [tdd-master.md](specs/02-tdd/tdd-master.md) section 2.

### 3.1 Service groups (created earlier by step 4, `PlaygroundGroupsCreate`)
| Group | Purpose |
|---|---|
| `grp-lsb-it-admins@<domain>` | IT Admins; nested in `grp-lsb-bu-admins@`; **configure Playground Folders**; only they change membership of both groups |
| `grp-lsb-bu-admins@<domain>` | BU Admins (plus IT Admins); **configure playgrounds** inside the Playground Folders they control |

**Standing grant:** `grp-lsb-it-admins@` gets Folder Admin + Tag User + Project Creator on the common ancestor of the school folders. BU Admins need no school-folder grants (their rights come from the Playground Folders where IT names them as controllers).

Step 4 creates them as security groups (no human owners or managers, not locked) with the initial IT Admins; step 6 only adds the IT Admins' standing grant. Membership is managed outside the platform.

### 3.2 Service accounts (in the Control Tower project)
| Service account | Purpose | Proposed roles |
|---|---|---|
| `sa-lsb-api` | Runtime identity of the Self Service APIs (config-stage changes use the **user's** token, not this SA) | On the CT project: `roles/datastore.user`, `roles/logging.logWriter`, `roles/monitoring.metricWriter`. Permission to start the predefined Terraform trigger (Cloud Build) and act as the Terraform runner |
| `sa-control-tower` (Terraform runner) | **Pipeline stage only:** runs Terraform in Cloud Build after a playground is configured (projects, billing, services, student bindings, budgets) | On the common ancestor of school folders (e.g. University Sandbox `600433119916`): Project Creator (+ what services need). On the billing account: `roles/billing.user`, `roles/billing.costsManager`. On the state bucket: `roles/storage.objectAdmin` |
| `sa-lsb-build` | CI/CD (step 9) | On the CT project: `roles/artifactregistry.writer`, `roles/run.developer`, `roles/logging.logWriter`. On `sa-lsb-api`: `roles/iam.serviceAccountUser` |

### 3.3 Principles
1. **Config stage acts as the user, pipeline stage acts as the platform:** Playground Folders and playgrounds are created with the user's own token (no SA); only the Terraform pipeline runs as `sa-control-tower`, started by `sa-lsb-api` through a predefined trigger from a secured repo (tdd-master 2.10).
2. **No service account keys.**
3. **IAM is additive** (`google_*_iam_member`), never authoritative.
4. **Firestore IAM per database** (tdd-master 1.9), using IAM conditions on the database name: `sa-lsb-api` read/write on both databases; `sa-control-tower` **read-only on `lsb-control-tower-config-db`**, read/write on `lsb-control-tower-db`. Verify that Firestore IAM conditions on the database name work as expected.

### 3.4 Manual steps (cannot be done in Terraform)
Decided (2026-11-09): no platform identity gets a directory admin role; group membership is managed by people in the Admin console.

### 3.5 Readiness
Groups exist; service accounts exist; IAM bindings visible (allow a few minutes for propagation). Tag binding re-check: as an IT Admin test user with no org-level roles, bind one IT-governed key on a throwaway folder under the ancestor, relying only on the step 6 grant ([tdd-tags-labels-master.md](specs/02-tdd/tdd-tags-labels/tdd-tags-labels-master.md) section 5).

### 3.6 Written back to `initialize.env`
`CT_SA_API`, `CT_SA_PROVISIONER`, `CT_SA_BUILD` (service account emails).

### 3.7 Open decisions
1. **Common ancestor** for the IT Admins' and `sa-control-tower`'s grants: University Sandbox (`600433119916`) or the org.
2. ~~Locked-group membership changes~~ **Decided:** managed outside the platform by people with directory rights.
3. **Pipeline source for now:** this public repo with a protected `main`, or a private repo now.
4. **Local API runs:** developer ADC impersonates `sa-lsb-api` (closest to production) or uses the admin's own permissions.
