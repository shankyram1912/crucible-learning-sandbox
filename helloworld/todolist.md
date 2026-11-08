# Hello World: To-Do List

Tracks the build sequence for the hello world MVP. Specs: [helloworld-spec.md](specs/helloworld-spec.md), [day0-bootstrap-spec.md](specs/day0-bootstrap-spec.md), [apiservices-spec.md](specs/apiservices-spec.md).

---

## 1. Day-0 Control Tower bootstrap

| # | Operation | Status | Notes |
|---|---|---|---|
| 1 | `ControlTowerProjectCreate` | ✅ Done (2026-11-08) | Folder "Control Tower" under University Sandbox, project `lsb-control-tower-e26`, billing, state bucket |
| 2 | `ControlTowerApisEnable` | ✅ Done (2026-11-08) | 16 baseline APIs, service agents (Cloud Run, Cloud Build, Artifact Registry); no Compute |
| 3 | `ControlTowerFirestoreCreate` | ✅ Done (2026-11-08) | Firestore Native `lsb-control-tower-db`, asia-southeast1, PITR, delete protection |
| 3a | Re-run `ControlTowerProjectCreate` to apply billing labels | ✅ Done (2026-11-08) | Project `lsb-control-tower-e26` labeled `cost-center-bu=central-it`, `cost-center` / `category` / `subcategory` = `lsb-control-tower` (1 in-place change; ops 2 and 3 unchanged) |
| 3b | Enable Cloud Billing export to BigQuery | ⏭️ Skipped (2026-11-08) | Skipped because this is a dev environment. Manual Console step; enable it in a production setup to report costs by label |
| 4 | `PlaygroundTagsDefinedCreate` | ⬜ To do | Defined (predefined) playground tags: org-level keys `cost-center-bu`, `cost-center`, `category` with values created from the catalog (initial: `central-it`, `lsb-control-tower`); usable in IAM conditions / org policies. Terraform (google provider 6.x). Not applied to the Control Tower. Needs Tag Admin at org level. Spec: helloworld-spec 1.8 |
| 5 | `PlaygroundTagsDynamicCreate` | ⬜ To do | Dynamic playground tag: org-level key `subcategory` with an allowed-values pattern (`^[a-z][a-z0-9-]{0,62}$`), so any matching value can be bound per Playground Folder / playground without pre-creating it. **Pinned google provider v6.50 has no `allowed_values_regex`** → newer provider or `gcloud`/API inside the operation. Verify dynamic values are GA for the org; fallback: platform creates values on demand (1,000 per key). Spec: helloworld-spec 1.8 rule 3 |
| 6 | `ControlTowerIdentityCreate` | ⬜ To design (section 3) | Service accounts and least-privilege IAM |
| 6a | Playground project hook | ⬜ To do (after step 6) | For every project in a playground (platform- or Console-created): copies the effective playground tags onto the project as labels, and binds the playground owners as `roles/owner`. Event-driven (project-creation audit log → function in the Control Tower); re-tag / owner-change jobs update all projects. Spec: helloworld-spec 1.8 rule 5, 2.5 |
| 7 | `ControlTowerRegistryCreate` | ⬜ To do | Artifact Registry Docker repo `lsb`, cleanup policy |
| 8 | `ControlTowerApiServiceCreate` | ⬜ To do | Cloud Run service for the Self Service APIs (placeholder image, runs as `sa-lsb-api`, env from `initialize.env`) |
| 9 | `ControlTowerPipelinesCreate` | ⬜ To do | Cloud Build GitHub connection (one manual GitHub App authorization), build trigger, deploy to Cloud Run |
| 10 | Networking | ⬜ To do | Access model for university-wide access, Compute, remove default network, load balancer / Cloud Armor if needed |
| 11 | Guardrails | ⬜ To do | Org policies, IAM deny rules and custom roles on the playground root |

---

## 2. Self Service APIs (after Day-0 step 6)

Built one operation at a time per [apiservices-spec.md](specs/apiservices-spec.md) section 4: write the operation spec, implement in API and CLI, test live, mark done. The API first runs locally against the real Firestore (ADC), so it does not wait for steps 7 to 9.

| # | Operation | Status |
|---|---|---|
| 01 | `health` (`GET /v1/health`, `lsb health`) | ⬜ To do |
| 02 | `jobs` (list, show, watch) | ⬜ To do |
| 03 | `templates` (list, show) | ⬜ To do |
| 04 | `playground-folder create` / list / show (creation gate, controllers, predefined tags) | ⬜ To do |
| 05 | `playground create` (creation gate, owners, subcategory, template, N projects) | ⬜ To do |
| 06 | `group members` (get / set; IT Admins only for the two service groups) | ⬜ To do |
| 07 | `service enable` (GCS) | ⬜ To do |

---

## 3. Step 6 in detail: `ControlTowerIdentityCreate` (to design)

Access model: [helloworld-spec.md](specs/helloworld-spec.md) section 2.

### 3.1 Service groups (locked)
| Group | Purpose |
|---|---|
| `grp-lsb-it-admins@<domain>` | IT Admins; nested in `grp-lsb-bu-admins@`; only they change membership of both groups (through the platform) |
| `grp-lsb-bu-admins@<domain>` | BU Admins (plus IT Admins); may create Playground Folders and playgrounds with the creation gate |

Created as **locked security groups** (no human owners or managers); initial IT Admins added at creation; `IT_ADMINS_GROUP` / `BU_ADMINS_GROUP` added back to `initialize.env`.

### 3.2 Service accounts (in the Control Tower project)
| Service account | Purpose | Proposed roles |
|---|---|---|
| `sa-lsb-api` | Runtime identity of the Self Service APIs | On the CT project: `roles/datastore.user`, `roles/logging.logWriter`, `roles/monitoring.metricWriter`. On `sa-control-tower`: `roles/iam.serviceAccountTokenCreator` (impersonation for provisioning and membership checks) |
| `sa-control-tower` | Provisioning: Playground Folders, playgrounds, projects, groups, IAM bindings, tags, budgets | On the common ancestor of school folders (e.g. University Sandbox `600433119916`): Folder Creator, Folder IAM Admin, Project Creator, Tag User. On the billing account: `roles/billing.user`, `roles/billing.costsManager`. On the state bucket: `roles/storage.objectAdmin`. **Manual (Admin console):** Groups Admin |
| `sa-lsb-build` | CI/CD (step 9) | On the CT project: `roles/artifactregistry.writer`, `roles/run.developer`, `roles/logging.logWriter`. On `sa-lsb-api`: `roles/iam.serviceAccountUser` |

### 3.3 Principles
1. **Authorize the user, act as the platform:** `sa-lsb-api` holds almost nothing; provisioning runs as `sa-control-tower` through short-lived impersonation. The broad ancestor grants are safe because the API acts only after the creation gate (caller in `grp-lsb-bu-admins@` + caller's own folder-create rights on the parent).
2. **No service account keys.**
3. **IAM is additive** (`google_*_iam_member`), never authoritative.

### 3.4 Manual steps (cannot be done in Terraform)
Admin console > Account > Admin roles > **Groups Admin** > assign to `sa-control-tower@<CT_PROJECT_ID>.iam.gserviceaccount.com`.

### 3.5 Readiness
Groups exist and are locked; service accounts exist; IAM bindings visible (allow a few minutes for propagation).

### 3.6 Written back to `initialize.env`
`CT_SA_API`, `CT_SA_PROVISIONER`, `CT_SA_BUILD` (service account emails).

### 3.7 Open decisions
1. **Common ancestor** for `sa-control-tower`'s grants: University Sandbox (`600433119916`) or the org.
2. **Local API runs:** developer ADC impersonates `sa-lsb-api` (closest to production) or uses the admin's own permissions.
3. **Initial IT Admins** to add to `grp-lsb-it-admins@` at creation.
