# LSB Control Tower: To-Do List

Tracks the build sequence for the LSB Control Tower. Specs: [tdd-master.md](specs/tdd-master.md), [tdd-control-tower-master.md](specs/tdd-control-tower/tdd-control-tower-master.md), [tdd-apis-master.md](specs/tdd-apis/tdd-apis-master.md), [tdd-playground-master.md](specs/tdd-playground/tdd-playground-master.md).

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
| 4 | `PlaygroundGroupsCreate` | ✅ Done (2026-11-08) | Both groups created as locked security groups (locked label accepted through Terraform). Creates `grp-lsb-it-admins@` and `grp-lsb-bu-admins@` as **locked security groups** (Terraform, `initial_group_config = EMPTY`, no human owners), nests it-admins in bu-admins (Terraform), adds `IT_ADMINS_INITIAL_MEMBERS` (Cloud Identity API in post-apply hook). Runs before the tag step, which grants Tag User to these groups. Spec: tdd-control-tower-master step 4 |
| 5 | `PlaygroundTagsCreate` | ✅ Done (2026-11-08) | Five **dynamic** playground tag keys at org level: `cost-center-bu`, `cost-center-code`, `cost-category`, `bu-tracking-code`, `bu-subcategory`, each with the allowed-values pattern `^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$`, so no tag values are created in GCP. Grants **Tag User on `cost-center-bu`, `cost-center-code`, `cost-category` to `grp-lsb-it-admins@`** and **on `bu-tracking-code` and `bu-subcategory` to `grp-lsb-bu-admins@`**. Allowed values for the three IT-governed keys live in the Firestore catalog, checked by the API before binding. Terraform only: `google_tags_tag_key.allowed_values_regex` exists from google provider 7.20 (verified 2026-11-08: absent in 7.10, present in 7.20, 8.0, 8.10), so this operation pins `~> 8.0` in its own `versions.tf`; ops 1-4 stay on `~> 6.0`. Tag User on a dynamic key is assumed to be enough to bind any matching value (the key is the only IAM resource for a dynamic value); verify live after step 6 (which grants IT Admins Tag User on the school-folder ancestor) and before API op 04, using a test user who is in `grp-lsb-it-admins@` but holds no org-level roles; the Day-0 admin cannot prove it because its org-level roles would allow the binding anyway. Not applied to the Control Tower. Needs Tag Admin at org level. Spec: tdd-master 1.8 |
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

Built one operation at a time per [tdd-apis-master.md](specs/tdd-apis/tdd-apis-master.md) section 4: write the operation spec, implement in API and CLI, test live, mark done. The API first runs locally against the real Firestore (ADC), so it does not wait for steps 7 to 9.

| # | Operation | Status |
|---|---|---|
| 01 | `health` (`GET /v1/health`, `lsb health`) | ⬜ To do |
| 02 | `jobs` (list, show, watch) | ⬜ To do |
| 03 | `templates` (list, show) | ⬜ To do |
| 04 | `playground-folder create` / list / show (creation gate, controllers, playground tags) | ⬜ To do |
| 05 | `playground create` (creation gate, owners, bu-tracking-code, bu-subcategory, template, N projects) | ⬜ To do |
| 06 | `group members` (get / set; IT Admins only for the two service groups) | ⬜ To do |
| 6 | `service enable` (GCS) | ⬜ To do |

---

## 3. Step 6 in detail: `ControlTowerIdentityCreate` (to design)

Access model: [tdd-master.md](specs/tdd-master.md) section 2.

### 3.1 Service groups (created earlier by step 4, `PlaygroundGroupsCreate`)
| Group | Purpose |
|---|---|
| `grp-lsb-it-admins@<domain>` | IT Admins; nested in `grp-lsb-bu-admins@`; **configure Playground Folders**; only they change membership of both groups |
| `grp-lsb-bu-admins@<domain>` | BU Admins (plus IT Admins); **configure playgrounds** inside the Playground Folders they control |

**Standing grant:** `grp-lsb-it-admins@` gets Folder Admin + Tag User + Project Creator on the common ancestor of the school folders. BU Admins need no school-folder grants (their rights come from the Playground Folders where IT names them as controllers).

Step 4 creates them as **locked security groups** (no human owners or managers) with the initial IT Admins; step 6 only adds the IT Admins' standing grant.

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
Membership changes of the two locked groups need a directory admin role: **open decision**: grant IT Admins Groups Admin/Editor (user token) or assign Groups Admin to a platform service account (the one exception to "no SA" in the config stage).

### 3.5 Readiness
Groups exist and are locked; service accounts exist; IAM bindings visible (allow a few minutes for propagation).

### 3.6 Written back to `initialize.env`
`CT_SA_API`, `CT_SA_PROVISIONER`, `CT_SA_BUILD` (service account emails).

### 3.7 Open decisions
1. **Common ancestor** for the IT Admins' and `sa-control-tower`'s grants: University Sandbox (`600433119916`) or the org.
2. **Locked-group membership changes:** IT Admins as Groups Admins/Editors (user token) or a platform service account.
3. **Pipeline source for now:** this public repo with a protected `main`, or a private repo now.
4. **Local API runs:** developer ADC impersonates `sa-lsb-api` (closest to production) or uses the admin's own permissions.
