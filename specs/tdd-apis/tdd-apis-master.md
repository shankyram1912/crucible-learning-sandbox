# LSB Control Tower TDD: Learning Sandbox Self Service APIs

> Parent: [tdd-master.md](../tdd-master.md)

The **Learning Sandbox Self Service APIs** are the single entry point for every playground action. There is no web UI yet. Every action is exposed as a **REST endpoint**, and every endpoint has a matching **command line (CLI) command** that renders human-readable, multi-color output in a Linux terminal.

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

## 2. Common specs

| Spec | Covers |
|---|---|
| [tdd-apis-common-stack.md](tdd-apis-common-stack.md) | Tech stack and reasoning, where the CLI runs, packaging |
| [tdd-apis-common-auth.md](tdd-apis-common-auth.md) | Authentication, authorization, tokens; read-only Firestore path for a future UI |
| [tdd-apis-common-acl.md](tdd-apis-common-acl.md) | Access control list: allowed roles per operation, common to CLI and REST, default deny |
| [tdd-apis-common-models.md](tdd-apis-common-models.md) | Conventions, request headers (including session ID), RequestContext, response headers, Accepted, Page, Error, Job, Task |
| [tdd-apis-common-cli.md](tdd-apis-common-cli.md) | Terminal output, global options, exit codes |
| [tdd-apis-common-jobs.md](tdd-apis-common-jobs.md) | **Interim.** Jobs: JobSync, JobAsync, JobTerraform; lifecycle, storage, locks and leases, dispatcher modes, handler contract, testing |
| [tdd-apis-common-config.md](tdd-apis-common-config.md) | Every API and CLI setting in one place (platform keys from `initialize.env`, `LSB_` API keys, CLI keys) |

Naming: `tdd-apis-common-<topic>.md` for cross-cutting specs, `tdd-apis-<domain>.md` for domain specs. This master stays an index (principles, common specs, domain table).

---

## 3. Domain specs

Operations are grouped into **domains**. Each domain has its own spec in this folder (`tdd-apis-<domain>.md`, with `Parent:` this file), which holds the domain's operations and CLI commands. This master keeps only the principles and this index; everything common to all domains is in the common specs (section 2). Build order across domains is global and tracked in [todolist.md](../../todolist.md) section 2.

| Domain | Operations (build #) | CLI group | Spec | Status |
|---|---|---|---|---|
| Health | api (01), db (02), service (03) | `lsb health` | [tdd-apis-health.md](tdd-apis-health.md) | Done (2026-11-09) |
| Jobs | list, show, watch (05) | `lsb jobs` | `tdd-apis-jobs.md` (to write) | To do |
| Templates | list, show (06) | `lsb templates` | `tdd-apis-templates.md` (to write) | To do |
| Playground Folders | create, list, show (07) | `lsb playground-folder` | `tdd-apis-playground-folders.md` (to write) | To do |
| Playgrounds | create (08), later show and configure | `lsb playground` | `tdd-apis-playgrounds.md` (to write) | To do |
| Platform users | role (04); listing with filters later; read-only | `lsb platform-users` | [tdd-apis-platform-users.md](tdd-apis-platform-users.md) | Role built |
| Services | enable, GCS first (09) | `lsb service` | `tdd-apis-services.md` (to write) | To do |

> The first API draft (REST and CLI reference, cohort model) is frozen in [apis-v0-interface.md](../../specs-reference/apis-v0-interface.md); each domain spec states which of its rows it replaces. Each domain spec follows [tdd-master.md](../tdd-master.md) section 2.

**A domain spec is created when its first operation is designed.** Every operation in it uses the same headings: REST method and path, CLI command, request and response (field tables plus a JSON example, per [tdd-apis-common-models.md](tdd-apis-common-models.md)), validation and pre-checks, auth rule, job and tasks (if async), terminal output, test, status. Workflow per operation:

1. **Write** the operation in its domain spec.
2. **Implement** it in the API and the CLI.
3. **Test** it in the live environment (`lsb-control-tower`, org `shankyram.altostrat.com`).
4. **Mark done** in the domain spec, the table above and the to-do list.
