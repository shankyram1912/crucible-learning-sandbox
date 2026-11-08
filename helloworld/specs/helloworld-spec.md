# Hello World Spec: Terraform and IAM Principles

Scope: guiding principles for the hello world prototype (one playground folder, one cohort, a few services). These principles carry forward into the main `specs/` once validated.

Related specs:
- [../todolist.md](../todolist.md): build sequence and status (Day-0 steps, Self Service API operations)
- [day0-bootstrap-spec.md](day0-bootstrap-spec.md): Day-0 Control Tower bootstrap (Cloud Shell, `initialize.env`, `run.sh`, steps)
- [apiservices-spec.md](apiservices-spec.md): Learning Sandbox Self Service APIs (REST interface and `lsb` CLI mapping)
- [gcpservices-spec.md](gcpservices-spec.md): GCP services

---

## 1. Terraform

### 1.1 Where Terraform is used
1. **Day-0 (once, run by a human):** Control Tower project (`lsb-control-tower`), `sa-control-tower`, the Terraform state bucket, org/root-folder policies, org-level custom roles, and IAM deny guardrails.
2. **Cohort lifecycle (by the platform):** cohort project creation and per-service project initialization, driven by a playground template.
3. **Not Terraform:** user-to-group membership (bulk Cloud Identity API operation), and anything students create on demand later.

### 1.2 Playground template model
1. A folder is designated as a **playground**.
2. In the GUI, a **playground template** is selected for the playground, along with which of the template's **services** are enabled.
3. Each service in a template maps to **its own Terraform root module**. Adding a new service to a template means adding a new module; existing modules are not edited.
4. Service prerequisites (for example Vertex AI Search needs Service Account and GCS) are declared in the template and determine run order.

### 1.3 Cohort flows
- **Define cohort:** define cohort, select template, create N projects from the template with billing ID linked, create the cohort groups. Seeds and state saved to the Control Tower bucket.
- **Configure cohort:** select services, run the enabled services' modules into the existing project(s) per the template. Seeds and state saved to the Control Tower bucket.

### 1.4 Each service is initialized into the existing project
1. Each service module is `terraform init`-ed with its **own state** and applied into the existing project.
2. The project, cohort groups, and prerequisites are **inputs and data-source lookups**, never resources the service module creates or owns.
3. A module only ever plans against its own state, so Console changes to other services do not affect enabling a new service.
4. A missing prerequisite (for example deleted in the Console) fails the data-source lookup before anything is created.
5. **v1 default: fire-and-forget.** A service module is applied once when the service is enabled and is not re-applied automatically. State is still kept so the module can be re-applied or torn down later.

### 1.5 Seeds and state live in the Control Tower
All Terraform inputs and state are stored centrally in one bucket in `lsb-control-tower`, never inside cohort projects.

```
gs://lsb-control-tower-bucket/
  cohorts/<cohort>/
    seeds/v1.tfvars.json, v2.tfvars.json ...   inputs per config version
    state/cohort/default.tfstate               cohort folder, groups, N projects + billing
    state/<project>/<service>/default.tfstate  one per project per enabled service
```

- Object versioning and soft delete are enabled.
- Access: `sa-control-tower` read/write; IT Admins read-only.
- Each state path has its own lock, so cohorts and services never block each other.
- Cohort teardown archives `cohorts/<cohort>/` instead of deleting it.

### 1.6 Execution rules
1. **Pre-check before every run:** template valid, prerequisites present, required groups defined with at least one member. Any failure stops the job before Terraform runs.
2. **One active job per cohort.**
3. **Step by step with readiness:** each service step completes and its resources are ready before dependent services start. Progress is written to Firestore per task.
4. **An enabled service can never be disabled in a cohort.** Services are add-only for the life of the cohort: the service API, its resources, and its state stay in place. Disabling an API with resources left in it is unsafe (resources become unmanageable, may keep billing, may be purged later, and dependent services break). Resources are only removed when the whole cohort is torn down.
   - **No "block new creations" in the default operating model.** Restricting new creations for an enabled service (for example near end of term) is not a portal feature. It is a backend action, decided case by case by the platform team, never a default behavior.
5. **IAM in Terraform is always additive** (`google_*_iam_member`), never authoritative (`_binding` / `_policy`), so bindings added in the Console are not wiped.
6. **Guardrails are not enforced by Terraform re-runs.** Rules that must never be broken by Console edits (bucket create/delete, public endpoints, regions) live in org policies and IAM deny.

### 1.7 Billing labels
1. **Every project the platform creates is labeled for billing**, and the same labels go on every resource that supports labels. Project labels attribute all of a project's costs in the billing export, including resources that cannot be labeled (Firestore databases, folders, service accounts).
2. **Label set:** `cost-center-bu`, `cost-center`, `category`, `subcategory`. No `owner` label. `environment` is added only if multiple environments exist.
3. **Control Tower values:** `cost-center-bu=central-it`, `cost-center=lsb-control-tower`, `category=lsb-control-tower`, `subcategory=lsb-control-tower`.
4. **Later, school-specific:** cohort projects use the same keys with school values (for example `cost-center-bu=<school>`), plus `playground` and `cohort` labels, so costs can be split per school and cohort.
5. **Mechanism:** labels come from configuration and are applied through the Terraform provider's `default_labels`, never hand-written per resource.
6. **Reporting** needs Cloud Billing export to BigQuery enabled on the billing account.

---

## 2. IAM

### 2.1 Principles
1. **Users are never bound to roles directly.** Access is only granted to groups; users get access through group membership.
2. **Group-to-role bindings are structure and live in Terraform.** User-to-group membership is data and is managed by a bulk Cloud Identity API operation (initial load and later changes), not Terraform.
3. **Preset groups come from the playground template.** Every cohort gets the template's preset groups; enabling a new service reuses the existing cohort groups.
4. **Roles are service specific.** Each service in a template maps each preset group to either a **standard (predefined) role** or a **service-specific custom role**.
5. **Prefer standard roles** when the binding scope already gives the isolation needed. Use a custom role only to remove permissions that would bypass the platform (for example delete, or import that runs as a shared service agent).
6. **Custom roles are global:** defined once at org level so they can be bound in any cohort project.
7. **Tags are for resource guardrails only** (org policy conditions such as blocking public Cloud Run endpoints), not for IAM grants.

### 2.2 Preset cohort groups
| Preset group | Who | Access principle |
|---|---|---|
| **Admins** | Cohort admins (= project admins) | Full access: `roles/owner` on the cohort's projects |
| **Student Admins** | Students with extra responsibilities | Student roles plus additional template-defined rights |
| **Students** | Cohort students | Service-specific roles on their own resources only |

- Group names are set by the platform: `grp-ls-<bu>-<cohort>-<slot>@<domain>` (for example `grp-ls-cs-cs100-students@shankyram.altostrat.com`).
- A preset group that an enabled service binds a role to must exist and have at least one member, or the pre-check fails.

### 2.3 Binding scope
1. **Admins** are bound at the cohort project level.
2. **Students and Student Admins** are bound on **their own resources** (their service account, bucket, Cloud Run service, data store) so classmates in a shared project stay isolated.
3. Project-level student bindings are limited to permissions that are safe project-wide (for example `serviceusage.services.use`, Gemini usage, Cloud SQL connect).
4. Cohort groups are bound only at cohort level. Anything that must apply higher up (deny exceptions, all-admins access) goes through one umbrella group with cohort groups nested in it, to stay within the IAM limit of 250 groups per policy.

### 2.4 Service role mapping (template table)
Each service in a template declares its role per preset group. Example for GCS (agreed so far); other services are added as they are designed.

| Service | Admins | Student Admins | Students | Guardrail |
|---|---|---|---|---|
| GCS | `roles/owner` (project) | `roles/storage.admin` on own bucket | `roles/storage.admin` on own bucket | Root-folder IAM deny on `buckets.create` / `buckets.delete` for everyone except `sa-control-tower` and the admins umbrella group |
| Cloud SQL | `roles/owner` (project) | TBD | `roles/cloudsql.client` + `roles/cloudsql.instanceUser` (project); database isolation via Postgres roles | TBD |
| Cloud Run | `roles/owner` (project) | TBD | TBD (standard vs custom without delete) | Org policy: no public ingress / invoker IAM required |
| Vertex AI Search | `roles/owner` (project) | TBD | TBD (custom without delete and import) | Imports brokered by the platform |

### 2.5 Guardrails (Day-0, root folder)
1. Org policies on the playground root folder are inherited by every cohort project (allowed locations, no service account keys, uniform bucket-level access, Cloud SQL without public IP, domain-restricted sharing, skip default network).
2. IAM deny rules use "deny everyone except platform SA and admins umbrella group", so they never need editing when new cohort groups are created.
