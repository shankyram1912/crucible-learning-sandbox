# Hello World: To-Do List

Tracks the build sequence for the hello world MVP. Specs: [helloworld-spec.md](specs/helloworld-spec.md), [day0-bootstrap-spec.md](specs/day0-bootstrap-spec.md), [apiservices-spec.md](specs/apiservices-spec.md).

---

## 1. Day-0 Control Tower bootstrap

| # | Operation | Status | Notes |
|---|---|---|---|
| 1 | `ControlTowerProjectCreate` | ✅ Done (2026-11-08) | Folder "Control Tower" under University Sandbox, project `lsb-control-tower-e26`, billing, state bucket |
| 2 | `ControlTowerApisEnable` | ✅ Done (2026-11-08) | 16 baseline APIs, service agents (Cloud Run, Cloud Build, Artifact Registry); no Compute |
| 3 | `ControlTowerFirestoreCreate` | ✅ Done (2026-11-08) | Firestore Native `lsb-control-tower-db`, asia-southeast1, PITR, delete protection |
| 3a | Re-run `ControlTowerProjectCreate` to apply billing labels | ⬜ To do | Plan verified read-only: 0 to add, 2 to change (project + bucket labels), 0 to destroy. Ops 2 and 3: no changes |
| 3b | Enable Cloud Billing export to BigQuery | ⬜ To do (Console, manual) | Needed to report costs by label |
| 4 | `ControlTowerIdentityCreate` | ⬜ To design (section 3) | Service accounts and least-privilege IAM |
| 5 | `ControlTowerRegistryCreate` | ⬜ To do | Artifact Registry Docker repo `lsb`, cleanup policy |
| 6 | `ControlTowerApiServiceCreate` | ⬜ To do | Cloud Run service for the Self Service APIs (placeholder image, runs as `sa-lsb-api`, env from `initialize.env`) |
| 7 | `ControlTowerPipelinesCreate` | ⬜ To do | Cloud Build GitHub connection (one manual GitHub App authorization), build trigger, deploy to Cloud Run |
| 8 | Networking | ⬜ To do | Access model for university-wide access, Compute, remove default network, load balancer / Cloud Armor if needed |
| 9 | Guardrails | ⬜ To do | Org policies, IAM deny rules and custom roles on the playground root |

---

## 2. Self Service APIs (after Day-0 step 4)

Built one operation at a time per [apiservices-spec.md](specs/apiservices-spec.md) section 4: write the operation spec, implement in API and CLI, test live, mark done. The API first runs locally against the real Firestore (ADC), so it does not wait for steps 5 to 7.

| # | Operation | Status |
|---|---|---|
| 01 | `health` (`GET /v1/health`, `lsb health`) | ⬜ To do |
| 02 | `jobs` (list, show, watch) | ⬜ To do |
| 03 | `templates` (list, show) | ⬜ To do |
| 04 | `playground designate` / list / show | ⬜ To do |
| 05 | `cohort define` | ⬜ To do |
| 06 | `group members` (get / set) | ⬜ To do |
| 07 | `service enable` (GCS) | ⬜ To do |

---

## 3. Step 4 in detail: `ControlTowerIdentityCreate` (to design)

### 3.1 Service accounts (in the Control Tower project)
| Service account | Purpose | Proposed roles |
|---|---|---|
| `sa-lsb-api` | Runtime identity of the Self Service APIs (Cloud Run, or local runs via impersonation) | On the CT project: `roles/datastore.user` (Firestore), `roles/logging.logWriter`, `roles/monitoring.metricWriter`. On `sa-control-tower`: `roles/iam.serviceAccountTokenCreator` (to act as it for provisioning) |
| `sa-control-tower` | Provisioning identity: creates playground folders, cohort projects, groups, IAM bindings, budgets | On the playground parent folder: `roles/resourcemanager.folderAdmin`, `roles/resourcemanager.projectCreator`, `roles/serviceusage.serviceUsageAdmin`. On the billing account: `roles/billing.user`, `roles/billing.costsManager`. On the state bucket: `roles/storage.objectAdmin`. **Manual:** Groups Admin in the Admin console |
| `sa-lsb-build` | CI/CD identity for Cloud Build triggers (step 7) | On the CT project: `roles/artifactregistry.writer`, `roles/run.developer`, `roles/logging.logWriter`. On `sa-lsb-api`: `roles/iam.serviceAccountUser` (deploy Cloud Run running as it) |

### 3.2 Principles
1. **Least privilege, split identities:** the API's runtime identity holds almost nothing; privileged provisioning runs as `sa-control-tower` through short-lived impersonation, which is auditable.
2. **No service account keys.** Cloud Run and Cloud Build attach identities directly; humans impersonate.
3. **IAM is additive** (`google_*_iam_member`), never authoritative.
4. **Bindings target the narrowest scope** (bucket, service account, folder) rather than the whole org.

### 3.3 Manual step (cannot be done in Terraform)
Admin console > Account > Admin roles > **Groups Admin** > Assign service accounts > `sa-control-tower@<CT_PROJECT_ID>.iam.gserviceaccount.com`. Needed for the API to create cohort groups and manage members.

### 3.4 Readiness
Service accounts exist; IAM bindings are visible in the policies; allow for IAM propagation (can take a few minutes).

### 3.5 Written back to `initialize.env`
`CT_SA_API`, `CT_SA_PROVISIONER`, `CT_SA_BUILD` (service account emails), used by later operations (Cloud Run service, pipelines) and local API runs.

### 3.6 Open decisions
1. **Scope of `sa-control-tower`:** which folder does it administer? Options: (a) a fixed playground parent folder from `initialize.env` (for example University Sandbox `600433119916`), granted in Day-0; (b) granted per folder when the IT Admin designates a playground (needs admin rights at designation time).
2. **Impersonation model:** API runs as `sa-lsb-api` and impersonates `sa-control-tower` for provisioning (recommended), or runs directly as `sa-control-tower` (simpler, broader runtime privileges).
3. **Local API runs:** developer ADC impersonates `sa-lsb-api` (closest to production) or uses the admin's own permissions.
4. **IT Admins group access** to the Control Tower project (read-only), now or later.
