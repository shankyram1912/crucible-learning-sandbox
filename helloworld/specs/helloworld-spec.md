# Hello World Spec: Terraform and IAM Principles

Scope: guiding principles for the hello world prototype (one Playground Folder, one playground, a few services). These principles carry forward into the main `specs/` once validated.

Related specs:
- [../todolist.md](../todolist.md): build sequence and status (Day-0 steps, Self Service API operations)
- [day0-bootstrap-spec.md](day0-bootstrap-spec.md): Day-0 Control Tower bootstrap (Cloud Shell, `initialize.env`, `run.sh`, steps)
- [terraform-pipeline-spec.md](terraform-pipeline-spec.md): playground Terraform pipeline (identities, secured source, reliability)
- [apiservices-spec.md](apiservices-spec.md): Learning Sandbox Self Service APIs (REST interface and `lsb` CLI mapping)
- [gcpservices-spec.md](gcpservices-spec.md): GCP services

---

## 1. Terraform

### 1.1 Where Terraform is used
1. **Day-0 (once, run by a human):** Control Tower project (`lsb-control-tower`), `sa-control-tower`, the Terraform state bucket, org/root-folder policies, org-level custom roles, and IAM deny guardrails.
2. **Playground lifecycle (by the platform):** Playground Folder and playground creation, playground project creation and per-service project initialization, driven by a playground template. (A playground is what earlier drafts called a cohort; all cohort concepts apply.)
3. **Not Terraform:** user-to-group membership (bulk Cloud Identity API operation), and anything students create on demand later.

### 1.2 Playground template model
1. A folder is designated as a **playground**.
2. In the GUI, a **playground template** is selected for the playground, along with which of the template's **services** are enabled.
3. Each service in a template maps to **its own Terraform root module**. Adding a new service to a template means adding a new module; existing modules are not edited.
4. Service prerequisites (for example Vertex AI Search needs Service Account and GCS) are declared in the template and determine run order.

### 1.3 Playground flows
- **Create playground:** create the playground (its folder inside a Playground Folder), select template, create N projects from the template with billing ID linked, create the playground's preset groups. Seeds and state saved to the Control Tower bucket.
- **Configure playground:** select services, run the enabled services' modules into the existing project(s) per the template. Seeds and state saved to the Control Tower bucket.

### 1.4 Each service is initialized into the existing project
1. Each service module is `terraform init`-ed with its **own state** and applied into the existing project.
2. The project, playground groups, and prerequisites are **inputs and data-source lookups**, never resources the service module creates or owns.
3. A module only ever plans against its own state, so Console changes to other services do not affect enabling a new service.
4. A missing prerequisite (for example deleted in the Console) fails the data-source lookup before anything is created.
5. **v1 default: fire-and-forget.** A service module is applied once when the service is enabled and is not re-applied automatically. State is still kept so the module can be re-applied or torn down later.

### 1.5 Seeds and state live in the Control Tower
All Terraform inputs and state are stored centrally in one bucket in `lsb-control-tower`, never inside playground projects.

```
gs://lsb-control-tower-bucket/
  playgrounds/<playground>/
    seeds/v1.tfvars.json, v2.tfvars.json ...   inputs per config version
    state/playground/default.tfstate           playground folder, groups, N projects + billing
    state/<project>/<service>/default.tfstate  one per project per enabled service
```

- Object versioning and soft delete are enabled.
- Access: `sa-control-tower` read/write; IT Admins read-only.
- Each state path has its own lock, so playgrounds and services never block each other.
- Playground teardown archives `playgrounds/<playground>/` instead of deleting it.

### 1.6 Execution rules
Full pipeline behavior (triggering, identities, secured source, reliability): [terraform-pipeline-spec.md](terraform-pipeline-spec.md).

1. **Pre-check before every run:** template valid, prerequisites present, required groups defined with at least one member. Any failure stops the job before Terraform runs.
2. **One active job per playground.**
3. **Step by step with readiness:** each service step completes and its resources are ready before dependent services start. Progress is written to Firestore per task.
4. **An enabled service can never be disabled in a playground.** Services are add-only for the life of the playground: the service API, its resources, and its state stay in place. Disabling an API with resources left in it is unsafe (resources become unmanageable, may keep billing, may be purged later, and dependent services break). Resources are only removed when the whole playground is torn down.
   - **No "block new creations" in the default operating model.** Restricting new creations for an enabled service (for example near end of term) is not a portal feature. It is a backend action, decided case by case by the platform team, never a default behavior.
5. **IAM in Terraform is always additive** (`google_*_iam_member`), never authoritative (`_binding` / `_policy`), so bindings added in the Console are not wiped.
6. **Guardrails are not enforced by Terraform re-runs.** Rules that must never be broken by Console edits (bucket create/delete, public endpoints, regions) live in org policies and IAM deny.

### 1.7 Billing labels
1. **Billing labels go on projects.** Every project the platform creates is labeled for billing. Project labels attribute all of a project's costs in the billing export, including resources that cannot be labeled (Firestore databases, folders, service accounts), so copying the same labels onto every resource adds nothing.
2. **Resource labels only where values differ within a project**, for example per student or app in shared playground projects later, to split that project's cost.
3. **Label set:** the playground tag key names (section 1.8): `cost-center-bu`, `cost-center-code`, `cost-category`, `bu-tracking-code`, `bu-subcategory`. Every project carries all five: the Control Tower from `LABEL_*` configuration, playground projects copied from their tags. No `owner` label. `environment` is added only if multiple environments exist.
4. **Control Tower values:** `cost-center-bu=central-it`, `cost-center-code=it-shared`, `cost-category=learning-sandbox`, `bu-tracking-code=it-100-1001`, `bu-subcategory=lsb-control-tower`.
5. **School-specific:** playground projects use the playground tag keys (section 1.8) with school values (for example `cost-center-bu=<school>`), so costs can be split per school, category and playground (see section 1.8).
6. **Mechanism:** labels come from configuration (`LABEL_*` keys) and are applied to the project by the operation that creates it, never hand-written.
7. **Reporting** needs Cloud Billing export to BigQuery enabled on the billing account.

### 1.8 Playground tags (folder-level, inherited)
Folders cannot carry labels, and labels are never inherited. To cover every project under a playground folder (including projects humans create in the Console), the billing keys are also defined as **playground tags**: Resource Manager tags bound on folders and inherited by everything below. They are named for playgrounds because playgrounds are what they exist for. **They are not applied to the Control Tower**, which keeps its project labels only (left unchanged for posterity).

| Tag key | Kind | Allowed values | Who binds it (Tag User on the key) |
|---|---|---|---|
| `cost-center-bu` | Dynamic | Pattern, plus the **catalog list** (for example `central-it`, one per school) checked by the API | IT Admins |
| `cost-center-code` | Dynamic | Pattern, plus the catalog list | IT Admins |
| `cost-category` | Dynamic | Pattern, plus the catalog list | IT Admins |
| `bu-tracking-code` | Dynamic | Pattern only, free value: the BU's own tracking code (for example a grant, project or course code) under the school's cost center | BU Admins (and IT Admins, nested) |
| `bu-subcategory` | Dynamic | Pattern only, free value set per playground | BU Admins (and IT Admins, nested) |

1. **All five keys are dynamic tags, created once at org level** by one Day-0 operation (`PlaygroundTagsCreate`). Each key has the allowed-values pattern `^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$`, so any matching value can be bound without creating it first. No tag values are created in GCP, there is no per-key value cap, and GCP tag state needs no maintenance when schools or categories are onboarded.
2. **Where they are bound:** the **Playground Folder** carries `cost-center-bu`, `cost-center-code`, `cost-category` and defaults for `bu-tracking-code` and `bu-subcategory`; a **playground** may override `bu-tracking-code` and `bu-subcategory` with its own values (a direct binding overrides the inherited value). The three IT-governed keys are never overridden at playground level. Every project and resource below inherits the effective values.
3. **The Firestore catalog is the only list of allowed values** for `cost-center-bu`, `cost-center-code` and `cost-category`. IT Admins maintain it through the platform, and the API checks a value against it before binding. GCP itself only checks the pattern, so a binding made outside the platform (Console, gcloud) is limited to people with Tag User on the key: IT Admins for the three governed keys. `bu-tracking-code` and `bu-subcategory` have no catalog list: BU Admins choose them freely within the pattern, so a BU can split its costs under the IT-assigned cost center without changing who pays.
4. **Why tags at all, when labels are copied:** tags on the folder are inherited by every project and resource below, including Console-created projects, and project owners cannot remove or override them. Labels are per project and editable by project owners. Tags are the source of truth; labels are a copy for label-based billing views.
5. **Not used in IAM conditions or org policies:** dynamic tag values cannot be used there. Policy switches that need tags (for example enabling GPUs per playground) get their own small **defined** key with fixed values, designed with the guardrails operation (`PlaygroundGuardrailsCreate`), separate from these billing keys.
6. **One value format for tags and labels:** starts with a lowercase letter, then lowercase letters, digits and hyphens, ends with a letter or digit, max 63 characters (the pattern above), so the same value is valid as a tag value and a project label.
7. **Every playground project carries labels copied from its playground's tags** (decided). Tags give inheritance (everything under the folder, including Console-created projects); labels keep label-based billing views consistent with the Control Tower. Folder tags never turn into project labels on their own, so the platform sets them:
   - **Platform-created projects:** labeled at creation with the playground folder's tag values.
   - **Console-created projects:** an event-driven auto-labeler (project-creation audit log event → small function in the Control Tower) copies the folder's tag values onto the new project within seconds.
   - **Re-tagging a playground** updates the folder's tag bindings **and** the labels on all its projects in the same job, so tags and labels never drift.
8. **No separate `playground` key** for now: the playground folder identifies the playground in inventory.
9. **Control Tower:** not tagged. It keeps its project labels (`cost-center-bu=central-it`, `cost-center-code=it-shared`, `cost-category=learning-sandbox`, `bu-tracking-code=it-100-1001`, `bu-subcategory=lsb-control-tower`), using the same key names as the playground tags.
10. **Limits** (to verify against the official quotas): 1,000 tag keys per org, dynamic values unlimited (the 1,000 values per key limit applies only to defined keys), 50 tags attached directly per resource, short names up to 256 characters.

### 1.9 Control Tower data: config, runtime, jobs
The Self Service APIs keep three kinds of data in Firestore, split over two databases in the Control Tower project so that the pipeline can never change desired state.

| | **Config** (desired state) | **Runtime** (observed state) | **Jobs** (operations) |
|---|---|---|---|
| Holds | Tag catalog, Playground Folders, playgrounds, owners and controllers, immutable config versions (v1..vN), template selections | What exists in GCP: folder and project IDs, effective tags, label sync, enabled services, applied config version, drift | Jobs, tasks, step status, log pointers, outputs, one lock per playground |
| Written by | The API only (on behalf of a user) | Runner (`sa-control-tower`), project hook, reconciler | Created by the API, updated by the runner |
| Rebuildable | No: source of truth | Yes, from GCP | Not needed: history |
| Database | `lsb-control-tower-config-db` (`FIRESTORE_CONFIG_DATABASE`) | `lsb-control-tower-db` (`FIRESTORE_DATABASE`) | `lsb-control-tower-db` (`FIRESTORE_DATABASE`) |
| Protection | PITR, delete protection, weekly backups kept 14 weeks | PITR, delete protection | Same database; documents expire through TTL (`expireAt`) |

1. **The runner reads config, never writes it.** Database-level IAM: `sa-lsb-api` read/write on both; `sa-control-tower` read-only on config, read/write on runtime and jobs (granted in Day-0 step 6 with IAM conditions on the database name).
2. **Runtime and jobs share a database** because the same actors update them at the same moment (a task becomes `READY` as a project is recorded), so both commit in one transaction.
3. **No cross-database transaction is needed:** config versions are immutable; the API writes version N first, then creates the job and takes the playground lock in one transaction in the runtime and jobs database. A version without a successful job is simply not applied.
4. **Desired vs applied:** a playground's current config is the latest version with a successful job, recorded in runtime as the applied version. Desired version (config) not equal to applied version (runtime) means pending or drifted.
5. **Layout:**

```
lsb-control-tower-config-db
  catalog/{key}/values/{value}           IT-governed tag values, scoped by cost-center-bu
  playgroundFolders/{id}                 school folder, controllers, IT tag values, default bu-* tags
  playgrounds/{id}                       Playground Folder, owners, template, bu-* overrides
  playgrounds/{id}/versions/{vN}         immutable config versions (tfvars source)

lsb-control-tower-db
  runtime/playgroundFolders/{id}         GCP folder ID, effective tags, IAM bound
  runtime/playgrounds/{id}               folder ID, projects, applied version, services
  runtime/projects/{projectId}           labels synced, owners bound, last reconcile
  jobs/{jobId}, jobs/{jobId}/tasks/{id}  type, target, config version, status, requested by, expireAt
  locks/{playgroundId}                   one active job per playground
```

---

## 2. IAM and access model

### 2.1 Structure: Playground Folders and playgrounds
```
<School folder>                 ordinary GCP folder, not managed by the platform
└── Playground Folder           created by the platform (mandatory container)
    └── Playground              folder + projects (what earlier drafts called a cohort)
        └── projects
```
1. **Two levels only.** No Playground Folder inside a Playground Folder, no playground inside a playground.
2. **Playground Folders are a mandatory container.** Every playground lives inside a Playground Folder.
3. **No designation of existing folders.** Playground Folders and playgrounds are always created by the platform.
4. **Ordinary folders stay outside the platform.** Creating folders for organization follows normal GCP folder IAM (ClickOps); the platform only reads them (for example in the folder picker).

### 2.2 Service groups and responsibilities
| Group | Members | Configures | Also |
|---|---|---|---|
| `grp-lsb-it-admins@<domain>` | IT Admins | **Playground Folders** (create, set the IT-governed tags, name the BU Admin controllers) | Only IT Admins add or remove members of both groups; control of every Playground Folder and playground by default |
| `grp-lsb-bu-admins@<domain>` | BU Admins, plus `grp-lsb-it-admins@` nested | **Playgrounds** inside the Playground Folders they control (owners, `bu-tracking-code` and `bu-subcategory` overrides, template, services) | |

- Both are created in Day-0 step 4 (`PlaygroundGroupsCreate`, before the tag operation that grants them Tag User) as **locked groups** (`cloudidentity.googleapis.com/groups.locked` plus the security label): only Super Admins and Groups Admins can change membership; group owners, managers and self-join are blocked.
- Membership changes go through the platform, which enforces "IT Admins only". No human owners or managers on these groups.
- Drift detection: Admin audit log alert on membership changes not made through the platform; platform-recorded intended membership compared periodically.

### 2.3 Creation gates (checked with the caller's own access token)
| Creating | Caller must be in | Caller's own GCP permissions on the parent (via `testIamPermissions`) |
|---|---|---|
| **Playground Folder** (parent: a school folder) | `grp-lsb-it-admins@` | `resourcemanager.folders.create`, `resourcemanager.folders.setIamPolicy`, `resourcemanager.tagValueBindings.create` |
| **Playground** (parent: a Playground Folder) | `grp-lsb-bu-admins@` (IT Admins included) | Same three, on the Playground Folder |

- GCP evaluates groups, inheritance and deny rules; all permissions are checked before anything is created, so a folder is never left half-configured.
- The folder picker shows only folders the caller can browse with their own permissions.

### 2.4 Who gets what
**Standing grants (outside individual playgrounds):**
| Principal | Granted on | Roles | Why |
|---|---|---|---|
| `grp-lsb-it-admins@` | Common ancestor of the school folders (for example University Sandbox) | Folder Admin, Tag User, Project Creator | IT Admins create and configure Playground Folders in any school |
| `grp-lsb-it-admins@` | Tag keys `cost-center-bu`, `cost-center-code`, `cost-category` | Tag User | Only IT Admins set the governed cost codes |
| `grp-lsb-bu-admins@` | Tag keys `bu-tracking-code`, `bu-subcategory` | Tag User | BU Admins set their tracking code and subcategory on their Playground Folders and playgrounds; the cost center itself stays with IT |

**Per Playground Folder and playground (bound by the platform at creation):**
| Principal | Playground Folder | Playground folder | Projects in the playground |
|---|---|---|---|
| **Playground Folder controllers**: BU Admin users or groups (1..N) named by the IT Admin at creation | **Folder Admin + Tag User + Project Creator** (create and configure playgrounds, create projects) | Inherited | Owner (inherited) |
| `grp-lsb-it-admins@` | Inherited from the standing grant | Inherited | Inherited |
| **Playground owners**: 1..N users or groups named at playground creation (editable later) | Nothing | **Browser** only; **no Project Creator** | **`roles/owner`**, bound **per project** |
| Students and Student Admins (preset groups) | Nothing | Nothing | Per project (baseline usage roles) and per own resource only |
| Terraform runner service account (pipeline stage, section 2.10) | Project Creator via the common ancestor | Inherited | Owner (creator of pipeline-made projects) |

1. **BU Admins need no grants on school folders.** All their GCP rights come from the Playground Folders where an IT Admin named them as controllers.
2. **Admin rights are inherited; student rights are not.** Controllers' rights are bound on the Playground Folder and flow to everything below. Playground owners are bound on each project. Students are never bound on a folder.
3. **Project creation** inside a playground is done only by Playground Folder controllers, IT Admins, or the Terraform pipeline. Playground owners work inside the projects they are given.
4. **Isolation between schools:** BU Admins control only the Playground Folders they were named on.
5. **Folder Admin also includes `folders.delete` and `folders.move`**, so controllers could delete (empty) or move folders in the Console. Optional later hardening: an IAM deny on move/delete for non-IT principals, or a custom role without them.
6. **Billing:** linking a new project to billing additionally requires Billing Account User on the billing account (account-wide; scoped per school only by using separate billing accounts).

### 2.5 Playground project hook
An event-driven hook in the Control Tower (project-creation audit log event to a small function) runs for every project created in a playground, including projects created in the Console:
1. Copies the playground's **effective tag values** onto the project as **labels** (section 1.8).
2. Binds the **playground owners** as `roles/owner` on the project.

Platform-created projects get both at creation. Changing a playground's owners or tags runs a job that updates all its projects.

### 2.6 Principles
1. **Prefer groups over individual users.** Named users are allowed only as Playground Folder controllers and playground owners; everything else is granted to groups.
2. **Config stage acts as the user; pipeline stage acts as the platform** (section 2.10). Portal membership grants no GCP access by itself.
3. **Group-to-role bindings are structure and live in Terraform.** User-to-group membership is data, managed by a bulk Cloud Identity API operation (initial load and later changes), not Terraform.
4. **Preset groups come from the playground template** (Student Admins, Students). The template's "admins" slot is filled by the playground owners. Enabling a new service reuses the existing playground groups.
5. **Roles are service specific.** Each service in a template maps each preset group to a standard (predefined) role or a service-specific custom role.
6. **Prefer standard roles** when the binding scope already gives the isolation needed. Use a custom role only to remove permissions that would bypass the platform (for example delete, or import that runs as a shared service agent).
7. **Custom roles are global:** defined once at org level so they can be bound in any playground project.

### 2.7 Binding scope for students
1. **Students and Student Admins** are bound on **their own resources** (their service account, bucket, Cloud Run service, data store) so classmates in a shared project stay isolated.
2. Project-level student bindings are limited to permissions that are safe project-wide (for example `serviceusage.services.use`, Gemini usage, Cloud SQL connect).
3. Playground groups are bound only within their playground. Anything that must apply higher up (deny exceptions) goes through an umbrella group with playground groups nested in it, to stay within the IAM limit of 250 groups per policy.
4. Group names are set by the platform (for example `grp-lsb-<school>-<playground>-students@<domain>`). A preset group that an enabled service binds a role to must exist and have at least one member, or the pre-check fails.

### 2.8 Service role mapping (template table)
Each service in a template declares its role per preset group. Example for GCS (agreed so far); other services are added as they are designed.

| Service | Playground owners | Student Admins | Students | Guardrail |
|---|---|---|---|---|
| GCS | `roles/owner` (project) | `roles/storage.admin` on own bucket | `roles/storage.admin` on own bucket | IAM deny on `buckets.create` / `buckets.delete` for everyone except `sa-control-tower` and the admins umbrella group |
| Cloud SQL | `roles/owner` (project) | TBD | `roles/cloudsql.client` + `roles/cloudsql.instanceUser` (project); database isolation via Postgres roles | TBD |
| Cloud Run | `roles/owner` (project) | TBD | TBD (standard vs custom without delete) | Org policy: no public ingress / invoker IAM required |
| Vertex AI Search | `roles/owner` (project) | TBD | TBD (custom without delete and import) | Imports brokered by the platform |

### 2.9 Guardrails
1. Org policies set at Playground Folder level (or a common ancestor) are inherited by every playground project (allowed locations, no service account keys, uniform bucket-level access, Cloud SQL without public IP, domain-restricted sharing, skip default network).
2. IAM deny rules use "deny everyone except platform SA and admins umbrella group", so they never need editing when new playground groups are created.

### 2.10 Execution identities and pipeline security
```
User ── ID token + access token ──▶ Self Service APIs (Cloud Run)
  ├─ CONFIG STAGE (no service account; acts as the user with the user's access token)
  │    Playground Folders and playgrounds: create folders, bind controllers/owners, bind tags,
  │    record configuration in Firestore. Audit logs show the real user.
  └─ PIPELINE STAGE (only after a playground is configured)
       Cloud Run's service account starts a predefined Cloud Build trigger;
       Terraform runs as a dedicated runner service account (projects, billing, services, student bindings).
```
1. **Config stage uses the user's token, no service account.** The user's own permissions (section 2.3) are what make the change; nothing is created that the user could not create themselves.
2. **Pipeline stage:** identities, secured source (variables only, predefined trigger, protected branch, pinned versions and image) and reliability are specified in [terraform-pipeline-spec.md](terraform-pipeline-spec.md).
3. **Open:** membership changes of the two locked groups need a directory admin role; either IT Admins hold Groups Admin/Editor (user token) or a platform service account does it (the one exception to "no service account" in the config stage).
