# Crucible (Learning Sandbox) Control Tower TDD: Self Service APIs

> Parent: [tdd-master.md](../tdd-master.md)

The **Crucible Self Service APIs** are the single entry point for every playground action. There is no web UI yet. Every action is exposed as a **REST endpoint**, and every endpoint has a matching **command line (CLI) command** that renders human-readable, multi-color output in a Linux terminal.

---

## 1. Principles

1. **REST first, CLI as a thin client.** The CLI never talks to GCP or Firestore directly. It only calls the REST API, so the same API can later back a web UI.
2. **All changes go through the API; a UI may read live state directly.** Every change (define cohort, set members, enable service) is a REST call. A future web UI may additionally read live state (job and task progress, cohort status, lists) **directly from Firestore with real-time listeners**, under security rules that deny all client writes ([tdd-apis-common-auth.md](tdd-apis-common-auth.md) section 3). The CLI keeps reading through the API.
3. **One endpoint, one command.** Every REST operation has exactly one CLI command, defined with it in its domain spec.
4. **Async by default.** Mutating calls (define cohort, set members, enable service) return `202 Accepted` with a `job_id`. The work runs as a provisioning job with tasks (see [tdd-master.md](../tdd-master.md) section 1.6).
5. **The CLI follows jobs live.** Mutating commands watch their job until it finishes and show each task's progress. `--no-wait` returns immediately with the `job_id`.
6. **Human output by default, machine output on request.** Default output is colored tables, trees and live progress. `--json` prints the raw API response for scripting.
7. **Fail fast and clearly.** Pre-check failures are returned before any job starts, with every problem listed, not just the first.
8. **Add-only services.** There is no endpoint or command to disable a service (tdd-master 1.6.4).
9. **Authentication is always required.** Every API call, including from the same machine (localhost), must carry a verified Google identity (Google ID token or Firebase ID token, [tdd-apis-common-auth.md](tdd-apis-common-auth.md)). There is no unauthenticated or dev bypass mode.

---

## 2. Two kinds of APIs: configuration and runtime

The APIs split the same way the data does ([tdd-master.md](../tdd-master.md) section 1.9):

- **Configuration APIs** read and change **desired state**: what IT and BU Admins decide (catalogs, templates, Playground Folders, playgrounds, who may use them). They write only to the configuration database, every change is a tracked job, and the heavy work (projects, services, billing) is handed to the pipeline.
- **Runtime APIs** read and change **observed state**: what exists and what is happening (workspaces and app resources that users create, jobs and their progress, who the caller is, whether the service is healthy). They write only to the runtime and jobs database or to GCP through the runner.

Which journey needs which operation, and which operations are shared across journeys, is in [tdd-apis-cuj-map.md](tdd-apis-cuj-map.md). Operations are grouped into **domains**; each domain has its own spec (`tdd-apis-<domain>.md`, with `Parent:` this file) holding its operations and CLI commands. Build order across domains is global and tracked in [todolist.md](../../../todolist.md) section 2.

### 2.1 Configuration APIs

| Domain | What it covers | Operations | CLI group | Spec | Status |
|---|---|---|---|---|---|
| Catalog: cost tags | The allowed values of the three IT cost tags (`cost-center-bu`, its `cost-center-code`s, `cost-category`): add new, mark disabled, never delete (IT-03, IT-04) | list, create, disable for cost centers, codes and categories | `lsb catalog` | `tdd-apis-catalog.md` (to write) | To do |
| Services | Single-GCP-service templates and their immutable versions: availability mode, module ref, prerequisites, bounds, singletons (mandatory only) and app resources; `current` and retire (IT-01) | list, get, create, retire; versions list, get, create, set-current, retire | `lsb services` | `tdd-apis-services.md` (to write) | To do |
| Templates | Playground templates and their immutable versions: pinned service versions, `max_students_per_project`, group slots; only `current` is used for new playgrounds (IT-02) | list, get (06), create, retire; versions list, get, create, set-current, retire | `lsb templates` | `tdd-apis-templates.md` (to write) | To do |
| GCP lookups | Live pickers read with the caller's own token when configuring a Playground Folder: browsable org folders and visible billing accounts; nothing stored (IT-05) | org-folders list, billing-accounts list | `lsb org-folders`, `lsb billing-accounts` | `tdd-apis-gcp-lookups.md` (to write) | To do |
| Playground Folders | The governed container: immutable parent, billing account, IT tags and BU Admin group; required budget; rename and budget update; reversible decommission (IT-05, IT-06, IT-07, IT-10) | create (07), list, get, update, decommission, recommission | `lsb playground-folder` | `tdd-apis-playground-folders.md` (to write) | To do |
| Playgrounds | A course's playground: pinned `current` template version, expected students and shards, BU tags, budgets, optional Playground Admin group, mapped user groups, add-only services and per-user allowances, grow-only capacity, reversible decommission (BU-01..BU-04, BU-08, BU-09) | create (08), list, get, update, services enable (09), allowance set, expand, decommission, recommission | `lsb playground`, `lsb service` | `tdd-apis-playgrounds.md` (to write) | To do |
| Playground users | The people in a playground's mapped groups, with their workspace state; portal-only suspend and restore; the entry point for acting on behalf of a user (BU-05, BU-06, IT-08) | list (search), get, suspend, restore | `lsb playground users` | `tdd-apis-playground-users.md` (to write) | To do |

### 2.2 Runtime APIs

| Domain | What it covers | Operations | CLI group | Spec | Status |
|---|---|---|---|---|---|
| Workspaces | A user's slice of a playground: the playgrounds they see (with Suspended / Decommissioned status), workspace initialization on entry (automatic shard placement, capacity exhausted), singleton resources, app containers and app resources within the per-user allowance; every `me` operation has a `users/{email}` twin for admins acting on behalf (ST-01..ST-05, BU-06, IT-08) | me playgrounds list; workspace get, initialize; apps list, create, get, delete; app resources list, create, get, delete; and their `users/{email}` twins | `lsb me`, `lsb workspace`, `lsb apps` | `tdd-apis-workspaces.md` (to write) | To do |
| Jobs | Every change as a tracked job: the audit trail. Listing scoped by persona (folder jobs, playground jobs filtered by project shard and user, own jobs), detail and live watch (IT-09, BU-07, ST-06) | list (05), get (05), watch (05), me jobs list | `lsb jobs`, `lsb me jobs` | `tdd-apis-jobs.md` (to write) | To do |
| Platform users | Who the caller is: the roles a user holds (self and, for admins, anyone); read-only | roles self, roles (04); listing with filters later | `lsb platform-users` | [tdd-apis-platform-users.md](tdd-apis-platform-users.md) | Roles done (2026-11-09) |
| Health | Is the API up, is the database reachable, is the service configured | api (01), db (02), service (03) | `lsb health` | [tdd-apis-health.md](tdd-apis-health.md) | Done (2026-11-09) |

> Numbers in parentheses are the build order already assigned in [todolist.md](../../../todolist.md) section 2; unnumbered operations are sequenced when they are picked up. The first API draft (REST and CLI reference, cohort model) is frozen in [apis-v0-interface.md](../../../specs-reference/apis-v0-interface.md); each domain spec states which of its rows it replaces. Each domain spec follows [tdd-master.md](../tdd-master.md) section 2.

**A domain spec is created when its first operation is designed.** Every operation in it uses the same headings: REST method and path, CLI command, request and response (field tables plus a JSON example, per [tdd-apis-common-models.md](tdd-apis-common-models.md)), validation and pre-checks, auth rule, job and tasks (if async), terminal output, test, status. Workflow per operation:

1. **Write** the operation in its domain spec.
2. **Implement** it in the API and the CLI.
3. **Test** it in the live environment (`lsb-control-tower`, org `shankyram.altostrat.com`).
4. **Mark done** in the domain spec, the tables above and the to-do list.

---

## 3. Common specs (across all domains)

| Spec | Covers |
|---|---|
| [tdd-apis-common-stack.md](tdd-apis-common-stack.md) | Tech stack and reasoning, where the CLI runs, packaging |
| [tdd-apis-common-auth.md](tdd-apis-common-auth.md) | Authentication, authorization, tokens; read-only Firestore path for a future UI |
| [tdd-apis-common-acl.md](tdd-apis-common-acl.md) | Access control list: allowed roles per operation, common to CLI and REST, default deny |
| [tdd-apis-common-models.md](tdd-apis-common-models.md) | Conventions, request headers (including session ID), RequestContext, response headers, Accepted, Page, Error, Job, Task |
| [tdd-apis-common-cli.md](tdd-apis-common-cli.md) | Terminal output, global options, exit codes |
| [tdd-apis-common-jobs.md](tdd-apis-common-jobs.md) | **Interim.** Jobs: JobSync, JobAsync, JobTerraform; lifecycle, storage, locks and leases, dispatcher modes, handler contract, testing |
| [tdd-apis-common-config.md](tdd-apis-common-config.md) | Every API and CLI setting in one place (platform keys from `initialize.env`, `LSB_` API keys, CLI keys) |
| [tdd-apis-cuj-map.md](tdd-apis-cuj-map.md) | **Working map.** Every operation once (route, CLI, job kind, roles), which journey needs which, and what is reused across journeys |

Naming: `tdd-apis-common-<topic>.md` for cross-cutting specs, `tdd-apis-<domain>.md` for domain specs. This master stays an index (principles, the two API kinds and their domains, common specs).
