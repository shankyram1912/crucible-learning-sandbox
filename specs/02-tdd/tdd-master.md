# Crucible (Learning Sandbox) Control Tower TDD: Terraform and IAM Principles

Scope: guiding principles for the Crucible Control Tower, the technical counterpart of the business requirements. The BRS says *what*; this master and its domain specs say *how*. These specs supersede the earlier BRS and TDD, which are kept for reference in `specs-reference/`.

Specs (one master per folder; longer designs split into `tdd-<folder>-<topic>.md` sub-files under it):
- [brs/brs-master.md](../01-brs/brs-master.md): business requirements: conceptual framework, personas, organization, core rules, and the IT Admin, BU Admin & Playground Admin, and Student / Designated User journeys with their design decisions
- [../todolist.md](../../todolist.md): build sequence and status (Day-0 steps, Self Service API operations)
- [tdd-control-tower/tdd-control-tower-master.md](tdd-control-tower/tdd-control-tower-master.md): builds the Control Tower: Day-0 bootstrap (Cloud Shell, `initialize.env`, `run.sh`, steps)
- [tdd-playground/tdd-playground-master.md](tdd-playground/tdd-playground-master.md): builds playgrounds: Terraform pipeline (identities, secured source, reliability), with [tdd-playground-services.md](tdd-playground/tdd-playground-services.md) for the GCP service modules
- [tdd-apis/tdd-apis-master.md](tdd-apis/tdd-apis-master.md): Crucible Self Service APIs (REST interface and `lsb` CLI mapping)
- [tdd-data/tdd-data-master.md](tdd-data/tdd-data-master.md): Firestore data design (config, runtime, jobs)
- [tdd-tags-labels/tdd-tags-labels-master.md](tdd-tags-labels/tdd-tags-labels-master.md): tag and label binding deep dive (permissions, who binds which key, validation, how GCP behaves)

---

## 1. Terraform

### 1.1 Where Terraform is used
1. **Day-0 (once, run by a human):** Control Tower project, `sa-control-tower`, the Terraform state bucket, the two service groups, the five playground tag keys, org-level custom roles, org policies and IAM deny guardrails.
2. **Playground lifecycle (by the platform):** Playground Folder creation, playground creation, project shard creation (with billing link, labels, budgets and owner bindings), per-service project initialization driven by the playground's pinned template version, shard expansion, and the billing unlink / relink of decommission and recommission. (A playground is what earlier drafts called a cohort.)
3. **Not Terraform:** group membership of any kind (service groups, BU Admin groups, Playground Admin groups, mapped user groups) is managed by people with directory rights in the Admin console; the platform only reads it. App resources that users create and delete inside their app containers are provisioned by the runner on demand (section 3.2).

### 1.2 Catalog and template model
1. A **service template** maps to a single GCP service and is **versioned**; each service version pins its own **Terraform root module** (path and ref), declares its availability mode (`MANDATORY`, `DEFAULT_ON`, `OPTIONAL`), prerequisite services, required APIs, user group slots, config defaults, quota per project, finite per-user `min`/`max` bounds, and the singleton and app resources it gives users. Adding a service to the catalog means adding a module; existing modules are never edited in place.
2. **Only `MANDATORY` service versions may define user singleton resources.** `DEFAULT_ON` and `OPTIONAL` services define app resources only, so enabling one on a running playground never re-initializes any workspace.
3. A **playground template** is versioned too; a template version pins service versions (optionally promoting availability mode or narrowing allowance bounds within the service's bounds) and sets `max_students_per_project`.
4. A playground is created from the template's **`current` version and stays pinned to it for life**. There is no template upgrade. Prerequisites come from the pinned service versions and determine module run order.
5. Services, templates and their versions are never deleted; every change is **versioned**, and earlier versions remain in version history for the templates and playgrounds pinned to them. Publishing a new version is what takes the previous one out of new selection.

### 1.3 Playground flows (all tracked jobs)
- **Create Playground Folder (IT-05):** create the GCP folder under the chosen parent, bind the three IT tags, bind the BU Admin group and `grp-lsb-it-admins@` (section 2.4), grant the runner Project Creator, apply guardrails, create the folder budget.
- **Create playground (BU-01):** create the playground folder inside the Playground Folder, bind the two BU tags, create `ceil(expected_students / max_students_per_project)` project shards (billing linked, labels copied from the effective tags, `roles/owner` for the BU Admin group, `grp-lsb-it-admins@` and the optional Playground Admin group), create the playground budget and optional shard budgets, then run every enabled service module (mandatory, plus the enabled optional ones) into every shard, binding the mapped user groups to the roles each module defines. Seeds and state go to the Control Tower bucket.
- **Configure playground (BU-03):** enable additional optional services from the pinned template version (new config version, module run into every shard) and adjust per-user allowances within `[min, max]`.
- **Expand capacity (BU-04):** add shards `p(K+1)..pM` initialized with all enabled services and the default shard budget (if set); `p01..pK` are untouched.
- **Rename or update budgets (IT-06, BU-02):** update display names and budget amounts; folder budget, playground budget and shard budgets only.
- **Suspend / restore a user's portal access (BU-05):** a config change only; no GCP change.
- **Decommission (IT-07, BU-08):** unlink billing from every project below (folder cascade or single playground), mark everything decommissioned; delete nothing.
- **Recommission (IT-10, BU-09):** relink every project to the Playground Folder's billing account and mark everything active again.
- **Workspace initialization and app resources (ST-01..ST-04):** section 3.2.

### 1.4 Each service is initialized into the existing project
1. Each service module is `terraform init`-ed with its **own state** and applied into the existing project.
2. The project, the mapped user groups, and prerequisites are **inputs and data-source lookups**, never resources the service module creates or owns.
3. A module only ever plans against its own state, so Console changes to other services do not affect enabling a new service.
4. A missing prerequisite (for example deleted in the Console) fails the data-source lookup before anything is created.
5. **v1 default: fire-and-forget.** A service module is applied once when the service is enabled (and once per new shard) and is not re-applied automatically. State is kept so the module can be re-applied later.

### 1.5 Seeds and state live in the Control Tower
All Terraform inputs and state are stored centrally in one bucket in the Control Tower project, never inside playground projects.

```
gs://<control-tower-bucket>/
  playground-folders/<folder>/
    state/default.tfstate                      folder, tags, IAM, guardrails, budget
  playgrounds/<playground>/
    seeds/v1.tfvars.json, v2.tfvars.json ...   inputs per config version
    state/playground/default.tfstate           playground folder, tags, N projects, billing, budgets, owner bindings
    state/<project>/<service>/default.tfstate  one per project per enabled service
```

- Object versioning and soft delete are enabled.
- Access: `sa-control-tower` read/write; IT Admins read-only.
- Each state path has its own lock, so playgrounds and services never block each other.
- Nothing under `playgrounds/<playground>/` is ever archived or deleted by the platform: decommission and recommission only flip billing, and the state is needed again on recommission.

### 1.6 Execution rules
Full pipeline behavior (triggering, identities, secured source, reliability): [tdd-playground-master.md](tdd-playground/tdd-playground-master.md).

1. **Pre-check before every run:** the pinned template version and service versions resolve, prerequisites are present, a mapped group exists for every user group slot, the Playground Folder (and playground) is active. Any failure stops the job before Terraform runs.
2. **One active job per playground** (and one per Playground Folder for folder-scoped jobs).
3. **Step by step with readiness:** each service step completes and its resources are ready before dependent services start. Progress is written to Firestore per task.
4. **An enabled service can never be disabled in a playground.** Services are add-only for the life of the playground: the service API, its resources, and its state stay in place. Disabling an API with resources left in it is unsafe (resources become unmanageable, may keep billing, may be purged later, and dependent services break). The only gate on new user creations is the per-user allowance within `[min, max]`.
5. **IAM in Terraform is always additive** (`google_*_iam_member`), never authoritative (`_binding` / `_policy`), so bindings added in the Console are not wiped.
6. **Guardrails are not enforced by Terraform re-runs.** Rules that must never be broken by Console edits (bucket create/delete, public endpoints, regions) live in org policies and IAM deny.
7. **Read-only while decommissioned:** every mutating job on a decommissioned Playground Folder or playground is rejected by the API; only recommission is accepted.

### 1.7 Billing labels
1. **Billing labels go on projects.** Every project the platform creates is labeled for billing. Project labels attribute all of a project's costs in the billing export, including resources that cannot be labeled (Firestore databases, folders, service accounts), so copying the same labels onto every resource adds nothing.
2. **Resource labels only where values differ within a project**, for example per user or app in shared playground projects, to split that project's cost.
3. **Label set:** the playground tag key names (section 1.8): `cost-center-bu`, `cost-center-code`, `cost-category`, `bu-tracking-code`, `bu-subcategory`. Every project carries all five: the Control Tower from `LABEL_*` configuration, playground projects copied from their effective tags at creation. No `owner` label. `environment` is added only if multiple environments exist.
4. **Control Tower values:** `cost-center-bu=central-it`, `cost-center-code=it-shared`, `cost-category=learning-sandbox`, `bu-tracking-code=it-100-1001`, `bu-subcategory=lsb-control-tower`.
5. **School-specific:** playground projects use the playground tag keys with school values (for example `cost-center-bu=<school>`), so costs can be split per school, category and playground.
6. **Mechanism:** labels come from configuration and are applied to the project by the operation that creates it, never hand-written. Because tags are immutable after creation (section 1.8), labels never need re-syncing.
7. **Reporting** needs Cloud Billing export to BigQuery enabled on the billing account.

### 1.8 Playground tags (folder-level, inherited, immutable)
Folders cannot carry labels, and labels are never inherited. To cover every project under a playground, the billing keys are also defined as **playground tags**: Resource Manager tags bound on folders and inherited by everything below. **They are not applied to the Control Tower**, which keeps its project labels only.

| Tag key | Kind | Allowed values | Who binds it (Tag User on the key) | Bound on |
|---|---|---|---|---|
| `cost-center-bu` | Dynamic | Pattern, plus the **catalog list** (one per school) checked by the API | IT Admins | Playground Folder |
| `cost-center-code` | Dynamic | Pattern, plus the catalog list (codes of that cost center) | IT Admins | Playground Folder |
| `cost-category` | Dynamic | Pattern, plus the catalog list | IT Admins | Playground Folder |
| `bu-tracking-code` | Dynamic | Pattern only, free value (un-cataloged): the BU's own tracking code | BU Admins (and IT Admins, nested) | Playground |
| `bu-subcategory` | Dynamic | Pattern only, free value (un-cataloged) | BU Admins (and IT Admins, nested) | Playground |

1. **All five keys are dynamic tags, created once at org level** by one Day-0 operation (`PlaygroundTagsCreate`). Each key has the allowed-values pattern `^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$`, so any matching value can be bound without creating it first. No tag values are created in GCP and GCP tag state needs no maintenance when schools or categories are onboarded.
2. **Where they are bound:** the **Playground Folder** carries only the three IT-governed keys, set by the IT Admin at creation; the **playground** carries the two BU keys, set by the BU Admin at creation. The IT-governed keys are never bound at playground level. Every project and resource below inherits the effective values.
3. **Bound once, never changed.** Tag bindings are created with the folder or playground and are immutable afterwards, exactly like the parent folder, billing account and admin groups. There is no re-tag job and therefore no tag/label drift.
4. **The Firestore catalog is the only list of allowed values** for the three IT-governed keys; catalog values are literal (what you see is what you get) and follow an add-new or mark-disabled lifecycle. The API checks a value against the catalog before binding. GCP itself only checks the pattern, so a binding made outside the platform is limited to people with Tag User on the key. The BU keys have no catalog: BU Admins choose them freely within the pattern.
5. **Why tags at all, when labels are copied:** tags are inherited by every project and resource below and project owners cannot remove or override them; labels are per project and editable by project owners. Tags are the source of truth; labels are the copy for label-based billing views. Hand-made projects inside a playground are unsupported (section 2.1), so no auto-labeler or project hook exists.
6. **Not used in IAM conditions or org policies:** dynamic tag values cannot be used there. Policy switches that need tags (for example enabling GPUs per playground) get their own small **defined** key with fixed values, designed with the guardrails operation (`PlaygroundGuardrailsCreate`), separate from these billing keys.
7. **One value format for tags and labels:** starts with a lowercase letter, then lowercase letters, digits and hyphens, ends with a letter or digit, max 63 characters (the pattern above), so the same value is valid as a tag value and a project label.
8. **No separate `playground` key** for now: the playground folder identifies the playground in inventory.
9. **Control Tower:** not tagged. It keeps its project labels (section 1.7 rule 4), using the same key names as the playground tags.
10. **Who can bind:** Tag User on the key and on the resource; for dynamic values GCP checks the key, so the key grants above decide who binds which keys. Details: [tdd-tags-labels-master.md](tdd-tags-labels/tdd-tags-labels-master.md).
11. **Limits** (to verify against the official quotas): 1,000 tag keys per org, dynamic values unlimited (the 1,000 values per key limit applies only to defined keys), 50 tags attached directly per resource, short names up to 256 characters.

### 1.9 Control Tower data: config, runtime, jobs
The Self Service APIs keep three kinds of data in Firestore, split over two databases in the Control Tower project so that the pipeline can never change desired state. The physical model is in [tdd-data-master.md](tdd-data/tdd-data-master.md).

| | **Config** (desired state) | **Runtime** (observed state) | **Jobs** (operations) |
|---|---|---|---|
| Holds | Tag catalog, service catalog and templates (versioned), Playground Folders, playgrounds (BU Admin group, optional Playground Admin group, mapped user groups, pinned template version, budgets, active/decommissioned state), archived configuration versions | What exists in GCP: folder and project IDs, enabled services, applied config version, shard occupancy; user workspaces with per-user portal access (enabled/suspended), app containers, app resources and allowance counters | Jobs, tasks, step status, log pointers, outputs, one lock per playground / folder |
| Written by | The API only (on behalf of a user) | Runner (`sa-control-tower`), reconciler | Created by the API, updated by the runner |
| Rebuildable | No: source of truth | Yes, from GCP | Not needed: history and audit trail |
| Database | `lsb-control-tower-config-db` (`FIRESTORE_CONFIG_DATABASE`) | `lsb-control-tower-db` (`FIRESTORE_DATABASE`) | `lsb-control-tower-db` (`FIRESTORE_DATABASE`) |
| Protection | PITR, delete protection, weekly backups kept 14 weeks | PITR, delete protection | Same database; kept indefinitely (no TTL) |

1. **The runner reads config, never writes it.** Database-level IAM: `sa-lsb-api` read/write on both; `sa-control-tower` read-only on config, read/write on runtime and jobs (granted in Day-0 step 6 with IAM conditions on the database name).
2. **Runtime and jobs share a database** because the same actors update them at the same moment (a task becomes `READY` as a project is recorded), so both commit in one transaction.
3. **No cross-database transaction is needed:** config versions are immutable; the API writes version N first, then creates the job and takes the lock in one transaction in the runtime and jobs database. A version without a successful job is simply not applied.
4. **Desired vs applied:** a playground's current config is the latest version with a successful job, recorded in runtime as the applied version. Desired version (config) not equal to applied version (runtime) means pending or drifted.
5. **Every change is a job and jobs are the audit trail** (decided): creation, rename and budget updates, configuration changes, shard expansion, portal access suspend/restore, workspace initialization, app-container and app-resource operations, decommission and recommission all run as tracked jobs recording the requester (and, when an admin acts on behalf of a user, both). Job history is kept indefinitely; there are **no TTL policies** (the ones briefly created on 2026-11-09 are deleted through Terraform). Large logs go to the state bucket, not Firestore.
6. **Job visibility follows persona scope:** IT Admins see all folder and playground jobs; BU Admins see folder jobs and playground jobs inside their folders; Playground Admins see playground jobs of their playground; users see their own jobs. Playground jobs are filterable by project shard and by user. Job history stays readable while a playground is decommissioned.
7. **Playground-scoped checks are data-dependent:** route-level ACL decides the persona (section 2.2); the operation then checks that the caller's BU Admin group owns the Playground Folder, or that the caller is in the playground's Playground Admin group, with a live directory lookup per request.

---

## 2. IAM and access model

### 2.1 Structure: Playground Folders and playgrounds
```
<Any existing folder>           ordinary GCP folder, not managed by the platform (chosen by the IT Admin, immutable)
└── Playground Folder           created by the platform (mandatory container)
    └── Playground              folder + project shards (what earlier drafts called a cohort)
        └── projects            created only by the pipeline
```
1. **Two levels only.** No Playground Folder inside a Playground Folder, no playground inside a playground.
2. **Playground Folders are a mandatory container.** Every playground lives inside a Playground Folder.
3. **No designation of existing folders.** Playground Folders and playgrounds are always created by the platform; the parent can be any folder the IT Admin can browse from the organization root, and cannot be changed later.
4. **Ordinary folders stay outside the platform.** Creating folders for organization follows normal GCP folder IAM (ClickOps); the platform only reads them (for example in the folder picker).
5. **Projects created by hand inside a playground are unsupported.** The platform neither labels nor binds them; guardrails still apply to them through inheritance.

### 2.2 Service groups and responsibilities
| Group | Members | Configures | Also |
|---|---|---|---|
| `grp-lsb-it-admins@<domain>` | IT Admins | **Catalogs** (services, templates, tag values) and **Playground Folders** (create, IT tags, BU Admin group, budget, decommission, recommission) | Can do everything a BU Admin can on every Playground Folder and playground; sees every job |
| `grp-lsb-bu-admins@<domain>` | BU Admins, plus `grp-lsb-it-admins@` nested | **Playgrounds** inside the Playground Folders whose BU Admin group they're in (create, BU tags, template, services, allowances, capacity, budgets, suspend/restore users, decommission, recommission) | Each Playground Folder names exactly **one** BU Admin group, which must already be inside `grp-lsb-bu-admins@` |

- Both are created in Day-0 step 4 (`PlaygroundGroupsCreate`) as security groups with no owners or managers, **not locked**.
- **The platform never changes group membership** (decided 2026-11-09) and holds no directory write rights: people with directory rights manage these groups, every BU Admin group, every Playground Admin group and every mapped user group in the Admin console. The platform only reads membership (roster cache for the two service groups; live lookups for folder and playground groups).
- **Route-level ACL by persona, operation-level scope check by data** (section 1.9 rule 7).

### 2.3 Creation gates (checked with the caller's own access token)
| Creating | Caller must be | Caller's own GCP permissions on the parent (via `testIamPermissions`) |
|---|---|---|
| **Playground Folder** (parent: any existing folder) | in `grp-lsb-it-admins@` | `resourcemanager.folders.create`, `resourcemanager.folders.setIamPolicy`, `resourcemanager.tagValueBindings.create` |
| **Playground** (parent: a Playground Folder) | in **that Playground Folder's BU Admin group** (live directory lookup) or in `grp-lsb-it-admins@` | Same three, on the Playground Folder |

- GCP evaluates groups, inheritance and deny rules; all permissions are checked before anything is created, so a folder is never left half-configured.
- The folder picker shows only folders the caller can browse with their own permissions.
- Playground Admins never pass the playground gate: they cannot create, decommission or recommission playgrounds.

### 2.4 Who gets what
**Standing grants (outside individual playgrounds):**
| Principal | Granted on | Roles | Why |
|---|---|---|---|
| `grp-lsb-it-admins@` | Common ancestor of the folders where Playground Folders may be created (section 3.2 item 4) | Folder Admin, Tag User | IT Admins create and configure Playground Folders anywhere below; no Project Creator (projects come only from the pipeline) |
| `grp-lsb-it-admins@` | Tag keys `cost-center-bu`, `cost-center-code`, `cost-category` | Tag User | Only IT Admins set the governed cost codes |
| `grp-lsb-bu-admins@` | Tag keys `bu-tracking-code`, `bu-subcategory` | Tag User | BU Admins set their tracking code and subcategory on their playgrounds |
| Terraform runner service account | Every billing account used for playgrounds | Billing Account User (and the platform Billing Account Costs Manager for budgets) | Links projects to billing, creates budgets; prerequisites of the platform setup IaC |

**Per Playground Folder and playground (bound by the platform at creation, immutable afterwards):**
| Principal | Playground Folder | Playground folder | Projects in the playground |
|---|---|---|---|
| **BU Admin group**: exactly one group, already inside `grp-lsb-bu-admins@`, named by the IT Admin at folder creation | **Folder Admin + Tag User** (create and configure playgrounds; no Project Creator) | Inherited | **`roles/owner`**, bound **per project** |
| `grp-lsb-it-admins@` | Inherited from the standing grant | Inherited | **`roles/owner`**, bound **per project** |
| **Playground Admin group**: at most one existing group, optionally named by the BU Admin at playground creation | Nothing | **Browser** only | **`roles/owner`**, bound **per project** |
| **Mapped user groups**: one existing group per template user group slot, fixed at playground creation | Nothing | Nothing | Per project (baseline usage roles) and per own resource only, as each service module defines |
| Terraform runner service account (pipeline stage, section 2.10) | **Project Creator**, bound on each Playground Folder at its creation | Inherited | Owner (creator of every playground project; as owner it also links and unlinks billing) |

1. **BU Admins need no grants on the parent folders.** All their GCP rights come from the Playground Folders whose BU Admin group they're in.
2. **Admin rights on folders are inherited; on projects they're bound explicitly.** The BU Admin group's folder rights flow to everything below. On every playground project, the BU Admin group, `grp-lsb-it-admins@` and the Playground Admin group (if any) are each bound `roles/owner`. Users are never bound on a folder.
3. **Project creation** inside a playground is done only by the Terraform pipeline, which also links each project to the Playground Folder's billing account. Admins work inside the projects it creates.
4. **Isolation between schools:** BU Admins control only the Playground Folders whose BU Admin group they're in; Playground Admins see only their playground.
5. **Folder Admin also includes `folders.delete` and `folders.move`**, so admins could delete (empty) or move folders in the Console. Optional later hardening: an IAM deny on move/delete for non-IT principals, or a custom role without them.
6. **Billing:** only the Terraform runner links, unlinks (decommission) and relinks (recommission) projects to billing: as each project's creator it is owner, and it holds Billing Account User on every billing account used for playgrounds. The platform creates folder, playground and shard budgets with Billing Account Costs Manager. Admins hold no billing rights.
7. **Suspension is portal-only.** Suspending a user's portal access changes nothing in GCP IAM; it only blocks that user's platform actions in that playground.

### 2.5 Owner bindings and labels at creation
Platform-created projects get their labels (section 1.7) and their three owner bindings (section 2.4) in the creation job. Because tags, the BU Admin group, the Playground Admin group and the mapped user groups are immutable, no follow-up job ever rewrites labels or owner bindings. Hand-made projects are unsupported (section 2.1 rule 5); there is no project hook or auto-labeler.

### 2.6 Principles
1. **Groups only.** Every binding the platform makes is to a group: the two service groups, one BU Admin group per Playground Folder, at most one Playground Admin group per playground, and the mapped user groups. Named users are never bound.
2. **Config stage acts as the user; pipeline stage acts as the platform** (section 2.10). Portal membership grants no GCP access by itself.
3. **Group-to-role bindings are structure and live in Terraform.** Group membership is data, managed in the Admin console by people with directory rights; the platform only reads it.
4. **User group slots come from the pinned template version.** The BU Admin maps exactly one existing group to each slot at playground creation (for example `students`). The "admins" are always the BU Admin group, `grp-lsb-it-admins@` and the optional Playground Admin group; enabling a new optional service reuses the same mapped groups.
5. **Roles are defined inside each service's Terraform module**, per user group slot, never in the catalog or the template. Elevated privileges are a separate service definition, not a flag.
6. **Prefer standard roles** when the binding scope already gives the isolation needed. Use a custom role only to remove permissions that would bypass the platform (for example delete, or import that runs as a shared service agent).
7. **Custom roles are global:** defined once at org level so they can be bound in any playground project.

### 2.7 Binding scope for users
1. **Users are bound on their own resources** (their service account, bucket, logical database, Cloud Run service, data store) so classmates in a shared project stay isolated.
2. Project-level user bindings are limited to permissions that are safe project-wide (for example `serviceusage.services.use`, Gemini usage, Cloud SQL connect).
3. Mapped user groups are bound only within their playground's projects and resources, never higher up. Deny-rule exceptions use groups the platform knows at Day-0 (the runner and `grp-lsb-bu-admins@`, which nests `grp-lsb-it-admins@`); how Playground Admin groups are exempted is an open item (section 3.2).
4. Group names are whatever the school already uses; the platform never names or creates groups. The pre-check only verifies that a mapped group exists for every slot.

### 2.8 Service role mapping (per module)
Each service module declares the roles it binds per user group slot and for the admin groups. Example for GCS (agreed so far); other services are added as they are designed in [tdd-playground-services.md](tdd-playground/tdd-playground-services.md).

| Service | Admin groups (BU Admin, IT Admins, Playground Admin) | Users (mapped group) | Guardrail |
|---|---|---|---|
| GCS | `roles/owner` (project) | `roles/storage.admin` on own bucket | IAM deny on `buckets.create` / `buckets.delete` for everyone except `sa-control-tower` and the admin groups |
| Cloud SQL | `roles/owner` (project) | `roles/cloudsql.client` + `roles/cloudsql.instanceUser` (project); database isolation via Postgres roles | TBD |
| Cloud Run | `roles/owner` (project) | TBD (standard vs custom without delete) | Org policy: no public ingress / invoker IAM required |
| Vertex AI Search | `roles/owner` (project) | TBD (custom without delete and import) | Imports brokered by the platform |

### 2.9 Guardrails
1. Org policies are applied on each **Playground Folder** at creation (allowed locations, no service account keys, uniform bucket-level access, Cloud SQL without public IP, domain-restricted sharing, skip default network), adding to whatever the organization and the parent folders already enforce; every playground project inherits them.
2. IAM deny rules use "deny everyone except platform SA and admin groups", so they never need editing when new playgrounds are created.

### 2.10 Execution identities and pipeline security
```
User ── ID token + access token ──▶ Self Service APIs (Cloud Run)
  ├─ CONFIG STAGE (no service account; acts as the user with the user's access token)
  │    Playground Folders and playgrounds: create folders, bind admin groups, bind tags,
  │    record configuration in Firestore. Audit logs show the real user.
  └─ PIPELINE STAGE (only after a playground is configured)
       Cloud Run's service account starts a predefined Cloud Build trigger;
       Terraform runs as a dedicated runner service account (projects, billing, budgets, services, user bindings).
```
1. **Config stage uses the user's token, no service account.** The user's own permissions (section 2.3) are what make the change; nothing is created that the user could not create themselves.
2. **Pipeline stage:** identities, secured source (variables only, predefined trigger, protected branch, pinned versions and image) and reliability are specified in [tdd-playground-master.md](tdd-playground/tdd-playground-master.md).
3. **Decided (2026-11-09):** no platform identity has directory write rights. Group creation and membership (service groups, admin groups, user groups) are done by people with directory rights; admins map existing groups to playground slots at creation as a JobSync IAM association.

---

## 3. Open items (to come back to)

Tracked here until each is decided or applied. Decisions they depend on are in [brs/brs-master.md](../01-brs/brs-master.md) and the persona journey docs.

### 3.1 Sub-specs to align with this master and the BRS
1. **tdd-data:** `user_allowance_bounds.unlimited` must go (finite `max` only); `singleton_resources` allowed only on `MANDATORY` service versions; the AI template example makes Service Account, Gemini, Cloud Storage and Cloud SQL `MANDATORY`; add per-user portal access state, active/decommissioned state, recommission, and job types for renames, budget updates and suspend/restore; journey references `BU-01..BU-09`, `IT-01..IT-10`.
2. **tdd-apis:** operations for rename / budget update (IT-06, BU-02), suspend / restore (BU-05), decommission and recommission (IT-07, IT-10, BU-08, BU-09), job listing per persona scope filtered by project shard and user (IT-09, BU-07, ST-06), read-only enforcement while decommissioned, playground-scoped checks for Playground Admins, capacity-exhausted response at workspace initialization.
3. **tdd-playground:** decommission / recommission as pipeline jobs (billing unlink / relink per project); shard expansion inheriting the default shard budget; module run per new shard; remove any teardown flow.
4. **tdd-tags-labels:** drop re-tagging and the project hook; tags bound once at creation.
5. **todolist:** remove the project hook (6a) and template-upgrade work; add recommission operations.

### 3.2 Open design items
1. **2.8:** roles for Cloud SQL, Cloud Run and Vertex AI Search, decided as each service module is designed.
2. **2.4 rule 5:** optional hardening so admins can't delete or move folders.
3. **1.8 rule 11:** tag limits to verify against the official quotas.
4. **2.4:** the common ancestor for IT Admins' standing grant, given that a Playground Folder may sit under any folder the IT Admin can browse (Day-0 step 6 decision).
5. **Decommission and recommission mechanics (IT-07, IT-10, BU-08, BU-09):** billing unlink per project and relink to the Playground Folder's billing account; how GCP treats resources in projects left unbilled for long periods (some services suspend or purge resources), and whether that conflicts with the "nothing is deleted" rule; whether budgets need to be paused.
6. **Per-user resources (ST-01, ST-03, ST-04):** singletons at workspace initialization and app resources inside app containers are created by the runner on demand; decide per service module whether that is Terraform with per-user state or direct GCP API calls, and how allowance counters and the capacity-exhausted check are enforced atomically.
7. **2.7 rule 3:** how a playground's optional Playground Admin group is exempted from IAM deny rules that use a fixed admin exception list (per-playground deny policy on the playground folder, or an org-level admin umbrella group that directory admins maintain).
8. **Playground-scoped ACL (section 1.9 rule 7):** live directory lookup cost per request versus a short-lived cache for folder and playground group membership.
