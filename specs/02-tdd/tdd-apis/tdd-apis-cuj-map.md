# Crucible (Learning Sandbox) Control Tower TDD: APIs, CUJ to Operation Map

> Parent: [tdd-apis-master.md](tdd-apis-master.md) · Journeys: [brs-it-admin-cuj.md](../../01-brs/brs-it-admin-cuj.md), [brs-bu-admin-cuj.md](../../01-brs/brs-bu-admin-cuj.md), [brs-student-cuj.md](../../01-brs/brs-student-cuj.md)

> **Status: working map.** CUJs are UI/UX-centric: one journey is usually several API calls, and most calls serve more than one journey. This map lists every operation once (Operation catalog), then says which operations each CUJ needs (CUJ to operations) and which operations are shared (Reuse across journeys). It shapes the domain specs; each operation is designed in full in its domain spec (`tdd-apis-<domain>.md`) following the master's workflow.

Conventions used here:
- **Operation ID** is the ACL key (`domain.verb`); **route** is `METHOD /v1/...`; **CLI** is `lsb <group> <verb>`.
- **Kind** is the job kind from [tdd-apis-common-jobs.md](tdd-apis-common-jobs.md): `Read` (no job), `Sync` (JobSync: runs in the request, config-only or with the caller's token), `Async` (JobAsync: platform worker), `Terraform` (JobTerraform: pipeline). Every mutating call is a tracked job (BRS rule 9), including config-only ones.
- **Roles**: `IT` = `IT_ADMIN`, `BU` = `BU_ADMIN`, `PGA` = Playground Admin of the target playground, `USER` = any signed-in user. `BU` and `PGA` are always narrowed by a **scope check** in the operation (the caller's BU Admin group owns the Playground Folder, or the caller is in the playground's Playground Admin group, or the user is in a mapped group). How `PGA` is realized in the route-level ACL is open ([tdd-master.md](../tdd-master.md) 3.2 item 8).
- **Admin on behalf of a user:** every `/me/` route has an admin twin under `/users/{email}/` (same operation body, separate ACL entry, acting admin recorded on the job), per the "one route, one operation; `me` alias" rule.

---

## 1. Operation catalog

### Catalog: cost tags (IT-03, IT-04)

| Operation | Route | CLI | Kind | Roles | Notes |
|---|---|---|---|---|---|
| `cost_centers.list` | `GET /v1/catalog/cost-centers` | `lsb catalog cost-centers list` | Read | IT, BU, PGA | Includes disabled entries with a flag |
| `cost_centers.create` | `POST /v1/catalog/cost-centers` | `lsb catalog cost-centers create` | Sync | IT | Literal value, WYSIWYG |
| `cost_centers.disable` | `POST /v1/catalog/cost-centers/{bu}:disable` | `lsb catalog cost-centers disable` | Sync | IT | Never deleted |
| `cost_center_codes.list` | `GET /v1/catalog/cost-centers/{bu}/codes` | `lsb catalog codes list` | Read | IT, BU, PGA | |
| `cost_center_codes.create` | `POST /v1/catalog/cost-centers/{bu}/codes` | `lsb catalog codes create` | Sync | IT | |
| `cost_center_codes.disable` | `POST /v1/catalog/cost-centers/{bu}/codes/{code}:disable` | `lsb catalog codes disable` | Sync | IT | |
| `cost_categories.list` | `GET /v1/catalog/cost-categories` | `lsb catalog categories list` | Read | IT, BU, PGA | |
| `cost_categories.create` | `POST /v1/catalog/cost-categories` | `lsb catalog categories create` | Sync | IT | |
| `cost_categories.disable` | `POST /v1/catalog/cost-categories/{value}:disable` | `lsb catalog categories disable` | Sync | IT | |

### Catalog: services (IT-01)

| Operation | Route | CLI | Kind | Roles | Notes |
|---|---|---|---|---|---|
| `services.list` | `GET /v1/services` | `lsb services list` | Read | IT, BU, PGA | Header rows: `current_version`, status |
| `services.get` | `GET /v1/services/{service}` | `lsb services show` | Read | IT, BU, PGA | |
| `services.create` | `POST /v1/services` | `lsb services create` | Sync | IT | Creates the template and its `v1` |
| `services.retire` | `POST /v1/services/{service}:retire` | `lsb services retire` | Sync | IT | Blocks new selection; never deleted |
| `service_versions.list` | `GET /v1/services/{service}/versions` | `lsb services versions list` | Read | IT, BU, PGA | |
| `service_versions.get` | `GET /v1/services/{service}/versions/{v}` | `lsb services versions show` | Read | IT, BU, PGA | Availability mode, module ref, bounds, singletons (mandatory only), app resources |
| `service_versions.create` | `POST /v1/services/{service}/versions` | `lsb services versions create` | Sync | IT | New immutable version; optionally becomes `current` |
| `service_versions.set_current` | `POST /v1/services/{service}/versions/{v}:set-current` | `lsb services versions set-current` | Sync | IT | |
| `service_versions.retire` | `POST /v1/services/{service}/versions/{v}:retire` | `lsb services versions retire` | Sync | IT | |

### Catalog: playground templates (IT-02)

| Operation | Route | CLI | Kind | Roles | Notes |
|---|---|---|---|---|---|
| `templates.list` | `GET /v1/templates` | `lsb templates list` | Read | IT, BU, PGA | Active templates for pickers; existing build #06 |
| `templates.get` | `GET /v1/templates/{template}` | `lsb templates show` | Read | IT, BU, PGA | Build #06 |
| `templates.create` | `POST /v1/templates` | `lsb templates create` | Sync | IT | Creates the template and its `v1` |
| `templates.retire` | `POST /v1/templates/{template}:retire` | `lsb templates retire` | Sync | IT | |
| `template_versions.list` | `GET /v1/templates/{template}/versions` | `lsb templates versions list` | Read | IT, BU, PGA | |
| `template_versions.get` | `GET /v1/templates/{template}/versions/{v}` | `lsb templates versions show` | Read | IT, BU, PGA | Pinned service versions, effective modes and bounds, `max_students_per_project`, group slots |
| `template_versions.create` | `POST /v1/templates/{template}/versions` | `lsb templates versions create` | Sync | IT | Validates prerequisites DAG and bounds within service bounds |
| `template_versions.set_current` | `POST /v1/templates/{template}/versions/{v}:set-current` | `lsb templates versions set-current` | Sync | IT | Only `current` is used for new playgrounds |
| `template_versions.retire` | `POST /v1/templates/{template}/versions/{v}:retire` | `lsb templates versions retire` | Sync | IT | |

### GCP lookups with the caller's token (IT-05)

| Operation | Route | CLI | Kind | Roles | Notes |
|---|---|---|---|---|---|
| `org_folders.list` | `GET /v1/org-folders?parent=` | `lsb org-folders list` | Read | IT | Folder picker from the org root; only what the caller can browse (`X-LSB-Access-Token`) |
| `billing_accounts.list` | `GET /v1/billing-accounts` | `lsb billing-accounts list` | Read | IT | Accounts the caller can see; nothing stored |

### Playground Folders (IT-05, IT-06, IT-07, IT-10)

| Operation | Route | CLI | Kind | Roles | Notes |
|---|---|---|---|---|---|
| `playground_folders.create` | `POST /v1/playground-folders` | `lsb playground-folder create` | Sync → Terraform | IT | Caller's token creates the folder, binds the 3 IT tags and the admin groups (Sync); platform then applies guardrails, runner Project Creator and the folder budget (Terraform). Build #07 |
| `playground_folders.list` | `GET /v1/playground-folders` | `lsb playground-folder list` | Read | IT, BU | BU sees only folders whose BU Admin group they're in (live lookup). Build #07 |
| `playground_folders.get` | `GET /v1/playground-folders/{folder}` | `lsb playground-folder show` | Read | IT, BU | Immutable fields, budget, state (`ACTIVE` / `DECOMMISSIONED`). Build #07 |
| `playground_folders.update` | `PATCH /v1/playground-folders/{folder}` | `lsb playground-folder update` | Async | IT | Display name and budget amount only; `409` on revision mismatch; rejected while decommissioned |
| `playground_folders.decommission` | `POST /v1/playground-folders/{folder}:decommission` | `lsb playground-folder decommission` | Terraform | IT | Billing unlinked on every project below; cascade marks playgrounds and projects decommissioned |
| `playground_folders.recommission` | `POST /v1/playground-folders/{folder}:recommission` | `lsb playground-folder recommission` | Terraform | IT | Mirror cascade: relink billing, reactivate all |

### Playgrounds (BU-01..BU-04, BU-08, BU-09)

| Operation | Route | CLI | Kind | Roles | Notes |
|---|---|---|---|---|---|
| `playgrounds.create` | `POST /v1/playground-folders/{folder}/playgrounds` | `lsb playground create` | Sync → Terraform | IT, BU | Caller's token: playground folder, 2 BU tags, admin-group bindings (Sync); pipeline: shards, billing, labels, owners, budgets, enabled services, mapped-group bindings (Terraform). Body fixes template (`current`), expected students, BU tags, budgets, optional Playground Admin group, mapped groups per slot, initial services and allowances. Build #08 |
| `playgrounds.list` | `GET /v1/playgrounds?folder=` | `lsb playground list` | Read | IT, BU, PGA | Scoped: BU to their folders, PGA to their playgrounds |
| `playgrounds.get` | `GET /v1/playgrounds/{playground}` | `lsb playground show` | Read | IT, BU, PGA | Pinned template version, state, shards and occupancy, enabled services, allowances, budgets |
| `playgrounds.update` | `PATCH /v1/playgrounds/{playground}` | `lsb playground update` | Async | IT, BU, PGA | Display name, playground budget, shard budgets (default and per-shard); `409` on revision mismatch |
| `playgrounds.services.enable` | `POST /v1/playgrounds/{playground}/services/{service}:enable` | `lsb service enable` | Terraform | IT, BU, PGA | Add-only; prerequisites added; new config version; module run into every shard. Build #09 |
| `playgrounds.allowances.update` | `PUT /v1/playgrounds/{playground}/services/{service}/allowance` | `lsb playground allowance set` | Sync | IT, BU, PGA | Within `[min, max]` and shard quota; non-destructive; new config version |
| `playgrounds.expand` | `POST /v1/playgrounds/{playground}:expand` | `lsb playground expand` | Terraform | IT, BU, PGA | Grow-only `expected_students`; new shards with all enabled services and the default shard budget |
| `playgrounds.decommission` | `POST /v1/playgrounds/{playground}:decommission` | `lsb playground decommission` | Terraform | IT, BU | Not PGA |
| `playgrounds.recommission` | `POST /v1/playgrounds/{playground}:recommission` | `lsb playground recommission` | Terraform | IT, BU | Not PGA; folder must be active |

### Playground users (BU-05, BU-06, IT-08)

| Operation | Route | CLI | Kind | Roles | Notes |
|---|---|---|---|---|---|
| `playground_users.list` | `GET /v1/playgrounds/{playground}/users?q=` | `lsb playground users list` | Read | IT, BU, PGA | Members of the mapped groups (live directory) joined with workspace state: not initialized / initialized (shard) / suspended; `q` searches by email or name |
| `playground_users.get` | `GET /v1/playgrounds/{playground}/users/{email}` | `lsb playground users show` | Read | IT, BU, PGA | Entry point for acting on behalf: workspace, singletons, app containers, allowance usage, recent jobs |
| `playground_users.suspend` | `POST /v1/playgrounds/{playground}/users/{email}:suspend` | `lsb playground users suspend` | Sync | IT, BU, PGA | Portal-only; no GCP change |
| `playground_users.restore` | `POST /v1/playgrounds/{playground}/users/{email}:restore` | `lsb playground users restore` | Sync | IT, BU, PGA | |

### Me: visibility and workspace (ST-01, ST-02)

| Operation | Route | CLI | Kind | Roles | Notes |
|---|---|---|---|---|---|
| `me.playgrounds.list` | `GET /v1/me/playgrounds` | `lsb me playgrounds` | Read | USER | Playgrounds whose mapped groups the caller is in, each with status `ACTIVE` / `SUSPENDED` (for this user) / `DECOMMISSIONED` and workspace state; empty list = "No Sandbox Assigned" |
| `me.workspace.get` | `GET /v1/playgrounds/{playground}/me/workspace` | `lsb workspace show` | Read | USER | Shard, singleton resources with Console links, allowance usage per service |
| `me.workspace.initialize` | `POST /v1/playgrounds/{playground}/me/workspace:initialize` | `lsb workspace init` | Async | USER | Idempotent (returns the existing workspace or the running job); picks a shard with free capacity; `409 CAPACITY_EXHAUSTED` when all shards are full; rejected when suspended or decommissioned. The UI calls it automatically on entry |
| `me.apps.list` | `GET /v1/playgrounds/{playground}/me/apps` | `lsb apps list` | Read | USER | |
| `me.apps.create` | `POST /v1/playgrounds/{playground}/me/apps` | `lsb apps create` | Sync | USER | Registers `app-<name>`; requires initialized workspace, active user and playground |
| `me.apps.get` | `GET /v1/playgrounds/{playground}/me/apps/{app}` | `lsb apps show` | Read | USER | App resources with Console links |
| `me.apps.delete` | `DELETE /v1/playgrounds/{playground}/me/apps/{app}` | `lsb apps delete` | Async | USER | Tears down every app resource inside; frees allowance |

### Me: app resources (ST-03, ST-04)

| Operation | Route | CLI | Kind | Roles | Notes |
|---|---|---|---|---|---|
| `me.app_resources.list` | `GET /v1/playgrounds/{playground}/me/apps/{app}/resources` | `lsb apps resources list` | Read | USER | |
| `me.app_resources.create` | `POST /v1/playgrounds/{playground}/me/apps/{app}/resources` | `lsb apps resources create` | Async | USER | Body: service, kind, name. Two-level cap check (per-user allowance across all apps, shard quota) before the job |
| `me.app_resources.get` | `GET /v1/playgrounds/{playground}/me/apps/{app}/resources/{resource}` | `lsb apps resources show` | Read | USER | |
| `me.app_resources.delete` | `DELETE /v1/playgrounds/{playground}/me/apps/{app}/resources/{resource}` | `lsb apps resources delete` | Async | USER | Frees allowance |

**Admin twins (acting on behalf, BU-06 / IT-08):** every `me.*` operation above except `me.playgrounds.list` has a twin with the same body and job under `/v1/playgrounds/{playground}/users/{email}/...`, operation IDs `users.workspace.get`, `users.workspace.initialize`, `users.apps.*`, `users.app_resources.*`, roles `IT, BU, PGA`, job recording both the acting admin and the target user.

### Jobs (IT-09, BU-07, ST-06)

| Operation | Route | CLI | Kind | Roles | Notes |
|---|---|---|---|---|---|
| `jobs.list` | `GET /v1/jobs?folder=&playground=&project=&user=&type=&status=` | `lsb jobs list` | Read | IT, BU, PGA | Scoped by persona: IT all; BU folder and playground jobs of their folders; PGA playground jobs of their playground (no folder jobs). `project` and `user` filter playground jobs. Build #05 |
| `jobs.get` | `GET /v1/jobs/{job}` | `lsb jobs show` | Read | IT, BU, PGA, USER | USER only for their own jobs (scope check). Build #05 |
| `jobs.watch` | `GET /v1/jobs/{job}:watch` (stream) | `lsb jobs watch` | Read | IT, BU, PGA, USER | Live task progress; used by every CLI mutating command. Build #05 |
| `me.jobs.list` | `GET /v1/me/jobs?playground=` | `lsb me jobs` | Read | USER | Own jobs incl. those run on the user's behalf by an admin; readable while suspended or decommissioned |

### Platform and health (existing)

| Operation | Route | CLI | Kind | Roles | Notes |
|---|---|---|---|---|---|
| `platform_users.roles.self` | `GET /v1/platform-users/me/roles` | `lsb platform-users roles` | Read | USER | Done (build #04) |
| `platform_users.roles` | `GET /v1/platform-users/{email}/roles` | `lsb platform-users roles EMAIL` | Read | IT, BU | Done (build #04) |
| `health.api` / `health.db` / `health.service` | `GET /v1/health/...` | `lsb health ...` | Read | USER / IT / USER | Done (build #01–03) |

---

## 2. CUJ to operations

Each row lists the operations a client needs to complete the journey: the **mutating** call(s) that define the journey, and the **reads** the UI/CLI uses before and after (pickers, validation, confirmation, follow-up). `jobs.watch` is implied after every mutating call and not repeated.

### IT Admin

| CUJ | Mutating operations | Supporting reads |
|---|---|---|
| **IT-01** Manage the service catalog | `services.create`, `service_versions.create`, `service_versions.set_current`, `service_versions.retire`, `services.retire` | `services.list`, `services.get`, `service_versions.list`, `service_versions.get` |
| **IT-02** Manage playground templates | `templates.create`, `template_versions.create`, `template_versions.set_current`, `template_versions.retire`, `templates.retire` | `templates.list`, `templates.get`, `template_versions.list`, `template_versions.get`, `services.list`, `service_versions.list` (to pin service versions) |
| **IT-03** Manage cost centers and codes | `cost_centers.create`, `cost_centers.disable`, `cost_center_codes.create`, `cost_center_codes.disable` | `cost_centers.list`, `cost_center_codes.list` |
| **IT-04** Manage cost categories | `cost_categories.create`, `cost_categories.disable` | `cost_categories.list` |
| **IT-05** Create a Playground Folder | `playground_folders.create` | `org_folders.list` (picker), `billing_accounts.list` (picker), `cost_centers.list`, `cost_center_codes.list`, `cost_categories.list` (active values), `playground_folders.get` (result) |
| **IT-06** Update a Playground Folder | `playground_folders.update` | `playground_folders.get` (revision) |
| **IT-07** Decommission a Playground Folder | `playground_folders.decommission` | `playground_folders.get`, `playgrounds.list?folder=` (what will be affected) |
| **IT-08** Act on any folder, playground or user workspace | Any BU-01..BU-09 mutating operation; `users.workspace.initialize`, `users.apps.*`, `users.app_resources.*` | `playground_folders.list`, `playgrounds.list`, `playground_users.list`, `playground_users.get` |
| **IT-09** View jobs across folders, playgrounds, projects and users | — | `jobs.list` (all scopes, `project=` and `user=` filters), `jobs.get`, `jobs.watch` |
| **IT-10** Recommission a Playground Folder | `playground_folders.recommission` | `playground_folders.get` |

### BU Admin and Playground Admin

| CUJ | Mutating operations | Supporting reads |
|---|---|---|
| **BU-01** Create a playground | `playgrounds.create` | `playground_folders.list` (my folders), `templates.list`, `templates.get`, `template_versions.get` (current: services, modes, bounds, slots, `max_students_per_project`), `playgrounds.get` (result) |
| **BU-02** Update name or budgets | `playgrounds.update` | `playgrounds.get` (revision, shards) |
| **BU-03** Configure services and allowances | `playgrounds.services.enable`, `playgrounds.allowances.update` | `playgrounds.get` (enabled services, bounds), `template_versions.get` (pinned version's optional services) |
| **BU-04** Expand capacity | `playgrounds.expand` | `playgrounds.get` (occupancy, `expected_students`) |
| **BU-05** Suspend or restore portal access | `playground_users.suspend`, `playground_users.restore` | `playground_users.list` (search), `playground_users.get` |
| **BU-06** Search for and act on behalf of a user | `users.workspace.initialize`, `users.apps.create`, `users.apps.delete`, `users.app_resources.create`, `users.app_resources.delete` | `playground_users.list` (search), `playground_users.get`, `users.workspace.get`, `users.apps.list`, `users.apps.get`, `users.app_resources.list` |
| **BU-07** View folder and playground jobs | — | `jobs.list` (BU: `folder=` and `playground=`; PGA: `playground=` only), `jobs.get`, `jobs.watch` |
| **BU-08** Decommission a playground | `playgrounds.decommission` | `playgrounds.get` |
| **BU-09** Recommission a playground | `playgrounds.recommission` | `playgrounds.get`, `playground_folders.get` (folder must be active) |

### Student / Designated User

| CUJ | Mutating operations | Supporting reads |
|---|---|---|
| **ST-01** Select a playground and auto-initialize | `me.workspace.initialize` (called on entry; no-op when already initialized) | `me.playgrounds.list` (status: active / suspended / decommissioned / no sandbox), `me.workspace.get` |
| **ST-02** Create an app container | `me.apps.create` | `me.workspace.get` (initialized?), `me.apps.list` |
| **ST-03** Provision app resources | `me.app_resources.create` | `me.workspace.get` (allowance usage), `playgrounds.get`-lite via `me.workspace.get` (enabled services and resource kinds), `me.apps.get` |
| **ST-04** Delete an app resource or app container | `me.app_resources.delete`, `me.apps.delete` | `me.apps.get`, `me.app_resources.list` |
| **ST-05** Operate in Cloud Console and Antigravity IDE | — | `me.workspace.get`, `me.apps.get` (Console deep links per resource); the Antigravity guide skill wraps the `lsb` CLI |
| **ST-06** View my own jobs | — | `me.jobs.list`, `jobs.get`, `jobs.watch` |

---

## 3. Reuse across journeys

| Operation | Used by |
|---|---|
| `jobs.get`, `jobs.watch` | Every mutating CUJ (CLI follows the job), IT-09, BU-07, ST-06 |
| `jobs.list` | IT-09, BU-07 (persona-scoped) |
| `playgrounds.get` | BU-02, BU-03, BU-04, BU-08, BU-09, IT-07, IT-08, and after BU-01 |
| `playground_folders.get` / `.list` | IT-05, IT-06, IT-07, IT-10, BU-01, BU-09, IT-08 |
| `templates.*`, `template_versions.get` | IT-02 (author), BU-01 (pick), BU-03 (which optional services remain) |
| `services.*`, `service_versions.*` | IT-01 (author), IT-02 (pin) |
| `cost_centers.list`, `cost_center_codes.list`, `cost_categories.list` | IT-03, IT-04 (manage), IT-05 (pick) |
| `playground_users.list` / `.get` | BU-05, BU-06, IT-08, and as the user filter source for `jobs.list` |
| `me.workspace.get` | ST-01, ST-02, ST-03, ST-05; admin twin `users.workspace.get` in BU-06 / IT-08 |
| `me.apps.*`, `me.app_resources.*` and their `users.*` twins | ST-02..ST-05 for users; BU-06 / IT-08 for admins acting on behalf |
| `platform_users.roles.self` | Every client at sign-in to decide which journeys to show |

---

## 4. What this implies for the domain specs

1. **Domains** (one spec each), as listed in [tdd-apis-master.md](tdd-apis-master.md) section 2: configuration — `catalog`, `services`, `templates`, `gcp-lookups`, `playground-folders`, `playgrounds`, `playground-users`; runtime — `workspaces` (`me` and `users` twins together), `jobs`, plus the existing `platform-users` and `health`.
2. **Config-only mutations are JobSync** (catalog, templates, allowances, suspend/restore): they run in the request, write a job record for the audit trail, and return the finished job.
3. **Two-stage creations** (Playground Folder, playground) are one job with a Sync part under the caller's token followed by a Terraform part under the platform; the job record covers both and the client watches one `job_id`.
4. **State guards are uniform:** every mutating operation on a Playground Folder or playground rejects `DECOMMISSIONED` targets (except recommission) with `409 TARGET_DECOMMISSIONED`; every `me.*` mutation rejects `SUSPENDED` users with `403 USER_SUSPENDED`; `me.workspace.initialize` returns `409 CAPACITY_EXHAUSTED` when no shard has room.
5. **Reads carry revisions** (`playground_folders.get`, `playgrounds.get`) so `update` calls can send `If-Match` / `revision` and get `409 CONFLICT` on a stale write.
6. **New ACL entries** for every operation above, with the `PGA` question resolved before the first `PGA` route is built ([tdd-master.md](../tdd-master.md) 3.2 item 8).
