# LSB Control Tower Spec: Learning Sandbox Self Service APIs

> Parent: [control-tower-spec.md](control-tower-spec.md)

The **Learning Sandbox Self Service APIs** are the single entry point for every playground action. There is no web UI yet. Every action is exposed as a **REST endpoint**, and every endpoint has a matching **command line (CLI) command** that renders human-readable, multi-color output in a Linux terminal.

---

## 1. Principles

1. **REST first, CLI as a thin client.** The CLI never talks to GCP or Firestore directly. It only calls the REST API, so the same API can later back a web UI.
2. **All changes go through the API; a UI may read live state directly.** Every change (define cohort, set members, enable service) is a REST call. A future web UI may additionally read live state (job and task progress, cohort status, lists) **directly from Firestore with real-time listeners**, under security rules that deny all client writes (section 3.5). The CLI keeps reading through the API.
3. **One endpoint, one command.** Every REST operation has exactly one CLI command (Appendix B).
4. **Async by default.** Mutating calls (define cohort, set members, enable service) return `202 Accepted` with a `job_id`. The work runs as a provisioning job with tasks (see [control-tower-spec.md](control-tower-spec.md) section 1.6).
5. **The CLI follows jobs live.** Mutating commands watch their job until it finishes and show each task's progress. `--no-wait` returns immediately with the `job_id`.
6. **Human output by default, machine output on request.** Default output is colored tables, trees and live progress. `--json` prints the raw API response for scripting.
7. **Fail fast and clearly.** Pre-check failures are returned before any job starts, with every problem listed, not just the first.
8. **Add-only services.** There is no endpoint or command to disable a service (control-tower-spec 1.6.4).
9. **Authentication is always required.** Every API call, including from the same machine (localhost), must carry a verified Google identity (Google ID token or Firebase ID token, section 3.1). There is no unauthenticated or dev bypass mode.

---

## 2. Tech stack and reasoning

| Part | Choice | Why |
|---|---|---|
| **REST API** | Python 3.12 + **FastAPI** | Same language as the provisioning code (Terraform runner, Cloud Identity, Firestore SDKs). Typed request/response models (Pydantic) with validation built in. Generates OpenAPI docs at `/docs` for free, which is the contract for the CLI now and a UI later. Native async fits long-running jobs. |
| **State** | **Firestore**, two databases in `lsb-control-tower`: `lsb-control-tower-config-db` (config, desired state) and `lsb-control-tower-db` (runtime state and jobs), see [control-tower-spec.md](control-tower-spec.md) section 1.9 | Serverless, no instance to run. Document model fits playgrounds, jobs and tasks. A transaction in the runtime and jobs database enforces one active job per playground. Real-time listeners let a future UI show live job progress without polling (read-only, section 3.5). |
| **Provisioning** | **Terraform** (seed cohort, enable service) + **Google Cloud SDKs** (membership, readiness checks) | Per [control-tower-spec.md](control-tower-spec.md): Terraform only where it adds value; fast directory and data operations use the APIs directly. |
| **CLI commands** | Python + **Typer** | Same author and style as FastAPI: plain functions with type hints become commands. Can reuse the API's Pydantic models so CLI and API cannot drift. Built-in `--help`, nested commands and shell completion. Built on Click, the mature Python CLI standard. |
| **CLI output** | **Rich** | Colors, tables, trees, live in-place updates and spinners (needed for `job watch`), pretty JSON and error panels. Disables color automatically when output is not a terminal or `NO_COLOR` is set. Typer uses Rich for help formatting, so they fit together. |
| **CLI HTTP + auth** | **httpx** + **google-auth** | Small, modern HTTP client. `google-auth` obtains Google ID tokens from the user's gcloud login / ADC without needing the Google Cloud client libraries in the CLI. |
| **CLI name** | `lsb` | Short for Learning Sandbox. |

**Trade-off accepted:** a Python CLI needs Python and a venv where it runs, and starts in about 0.2 to 0.3 seconds. Fine for the MVP. If the CLI is later distributed to university admins as a download, a Go single binary can replace it without touching the API, because the CLI only speaks REST.

---

## 3. Deployment and auth

### 3.1 Authentication (always on)
1. Every request carries `Authorization: Bearer <ID token>`. Requests without a valid token get `401`, including requests from localhost. Two token types are accepted:
   - **Google ID token** (issuer `accounts.google.com`), used by the CLI.
   - **Firebase ID token** (issuer `securetoken.google.com/<project>`), used by a future UI signed in with Firebase Auth (Google sign-in).
2. For either type, the API verifies the token signature, issuer, expiry, allowed audience (configured list), and that the user belongs to the org domain (`shankyram.altostrat.com`). The caller's identity is the **email in the verified token**; the rest of the API does not care which type it was.
3. The API **never trusts identity claimed by the client** (for example an `X-User` header).
4. **Authorization** is decided by the API from the verified email, its group memberships and, for creation, the caller's own GCP rights ([control-tower-spec.md](control-tower-spec.md) section 2). Failing it returns `403`.
   - **Personas:** IT Admin (`grp-lsb-it-admins@`), BU Admin (`grp-lsb-bu-admins@`, IT Admins included through nesting), Playground Folder controller, playground owner, student.
   - **Creation gates:** Playground Folders: caller in `grp-lsb-it-admins@`; playgrounds: caller in `grp-lsb-bu-admins@` (IT Admins included). In both cases the caller must also hold `resourcemanager.folders.create`, `resourcemanager.folders.setIamPolicy` and `resourcemanager.tagValueBindings.create` on the parent folder in standard GCP IAM.
   - **Group membership changes** for `grp-lsb-it-admins@` and `grp-lsb-bu-admins@`: IT Admins only.
5. **User access token.** Alongside the ID token, the client sends the caller's Google OAuth **access token** in `X-LSB-Access-Token` (CLI: from the gcloud login / ADC; UI: from Google sign-in with the `cloud-platform` scope). The API uses it, as the user, for the **config stage**: the creation-gate checks (`testIamPermissions`), the folder picker, and creating Playground Folders and playgrounds (folders, IAM bindings, tags). It is used only within the request and never stored. The **pipeline stage** (Terraform after a playground is configured) runs as the platform: Cloud Run's service account starts a predefined Cloud Build trigger that runs as the Terraform runner ([control-tower-spec.md](control-tower-spec.md) section 2.10).

### 3.2 Clients get tokens differently, the API treats them the same
| Client | Where the token comes from |
|---|---|
| **CLI** | The user's gcloud login / ADC, via `google-auth` |
| **Future UI on Cloud Run** (Control Tower) | The user signs in with Google through **Firebase Auth** in the browser; the UI passes the **user's** Firebase ID token to the API as the bearer, and uses the same sign-in for its read-only Firestore listeners |

- A UI backend must **pass the user's token through**, never call the API with its own service account token. Otherwise every request looks like the same service account and persona checks break.
- Adding a UI later needs no change to the API's endpoints; only Firebase ID token verification is added to authentication.

### 3.3 Where the CLI can run
The CLI only needs network reach to the API and a Google login. It never talks to GCP or Firestore.

| Setup | How the CLI reaches the API |
|---|---|
| **Same VM** (MVP default) | `LSB_API_URL=http://localhost:8080` |
| **Laptop to API on the Control Tower VM** | SSH tunnel `ssh -L 8080:localhost:8080 <vm>`, then `LSB_API_URL=http://localhost:8080` |
| **Anywhere to API on Cloud Run** (later) | `LSB_API_URL=https://<service>.asia-southeast1.run.app` |
| **Cloud Shell** | Same as Cloud Run, using the Cloud Shell login |

In every setup the bearer token is required.

### 3.4 Packaging
- **API:** `src/api`, runs locally on the Control Tower VM for the MVP; Cloud Run in `asia-southeast1` later.
- **CLI:** `src/cli`, its own small package (Typer, Rich, httpx, google-auth), installable with `pip` from the repo.


### 3.5 UI live state: read-only Firestore access (future UI)
| Kind of call | UI | CLI |
|---|---|---|
| **Live state** (job and task progress, cohort status, lists) | Reads Firestore directly with real-time listeners | Polls the API (`GET /v1/jobs/{id}`, `lsb job watch`) |
| **Changes** | Calls the Self Service APIs | Calls the Self Service APIs |

What the direct read path requires (added by a later UI operation, not needed for the CLI-first MVP):
1. **Firebase enabled on the Control Tower project** (`firebase` API, a registered Web App for the client config). The existing database `lsb-control-tower-db` is used as is; the Firebase client SDK supports named databases.
2. **Firebase Auth with Google sign-in**, restricted to the org domain.
3. **Security rules on `lsb-control-tower-db`:**
   - **All client writes denied.** Only the API (its service account, through IAM) writes.
   - Reads allowed only for what the caller may see (for example a cohort's jobs only for that cohort's admins).
   - Rules cannot look up Google Group membership, so the API maintains each user's personas and cohorts as **Firebase custom claims** or in a **membership document** the rules read.
4. **The API stays the source of truth.** The UI never derives state on its own beyond displaying what the API wrote.
---

## 4. Operation specs (build one by one)

Each resource operation from Appendix A, together with its CLI command from Appendix B, gets its own spec before it is built.

> Appendices A and B predate the playground model: "cohort" there means **playground**, and playgrounds live inside **Playground Folders** created by the platform (no designation of existing folders). Each operation spec follows [control-tower-spec.md](control-tower-spec.md) section 2. Workflow per operation:

1. **Write** the operation spec (request, response, validation, pre-checks, job tasks, auth rule, CLI command and output).
2. **Implement** it in the API and the CLI.
3. **Test** it in the live environment (`lsb-control-tower`, org `shankyram.altostrat.com`).
4. **Mark done** in the table below.

| # | Operation | CLI | Spec | Status |
|---|---|---|---|---|

---

## 5. Terminal output

### 5.1 Color scheme
| Meaning | Color | Symbol |
|---|---|---|
| Done / succeeded | Green | `✔` |
| Running / applying | Blue (spinner) | `⠋` |
| Created, waiting for ready | Cyan | `◐` |
| Getting ready | Yellow | `…` |
| Pending | Gray | `○` |
| Skipped | Dim | `–` |
| Failed / error | Red | `✖` |
| Identifiers (cohort, project, group) | Bold magenta | |

### 5.2 Example: define cohort (live, updating in place)
```
$ lsb cohort define cs100 --playground learning-sandbox --projects 1 \
      --billing XXXXXX-XXXXXX-XXXXXX \
      --members admins=seed/cs100-admins.csv --members students=seed/cs100-students.csv

 Define cohort cs100 (CS 100) in playground learning-sandbox    job-20261108-0001

  ✔ Pre-check                         template standard, 2 groups, 3 members        0.8s
  ◐ Create project cs100-p01          created, linking billing                      22s
  ○ Create preset groups              grp-ls-cs-cs100-admins, grp-ls-cs-cs100-students
  ○ Load members                      3 members

  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1/4
```

### 5.3 Example: pre-check failure
```
$ lsb service enable cs100 vertex-search

  ✖ Pre-check failed (2 problems)
    • vertex-search requires gcs, which is not enabled on cs100
    • group student-admins has no members

  Nothing was changed.
```

---

## Appendix A. REST interface reference (`/v1`)

> **Reference only, do not edit.** This appendix is the fixed reference list of resources and operations. Each operation is specified individually in its own spec (see section 4) before it is implemented.

### A.1 Resources
| Resource | Meaning |
|---|---|
| **Template** | A playground template: its services, preset group slots, and per-service role mapping. Read-only through the API in the MVP (defined in repo files). |
| **Playground** | A GCP folder designated as a playground, with its template. |
| **Cohort** | A cohort inside a playground: N projects, preset groups, enabled services. |
| **Members** | User emails in one of the cohort's preset groups (bulk, non-Terraform). |
| **Service** | A template service enabled on a cohort (add-only). |
| **Job** | One async provisioning run, made of ordered tasks. |

### A.2 Endpoints
| # | Method and path | Purpose | Response |
|---|---|---|---|
| 1 | `GET /v1/health` | API, Firestore and credentials check | `200` |
| 2 | `GET /v1/templates` | List templates | `200` |
| 3 | `GET /v1/templates/{template_id}` | Template details: services, group slots, roles | `200` |
| 4 | `POST /v1/playgrounds` | Designate a folder as a playground with a template | `201` |
| 5 | `GET /v1/playgrounds` | List playgrounds | `200` |
| 6 | `GET /v1/playgrounds/{playground_id}` | Playground details and its cohorts | `200` |
| 7 | `POST /v1/playgrounds/{playground_id}/cohorts` | **Define cohort**: create N projects with billing, create preset groups, load initial members | `202` + `job_id` |
| 8 | `GET /v1/cohorts` | List cohorts | `200` |
| 9 | `GET /v1/cohorts/{cohort_id}` | Cohort details: projects, groups, services, last job | `200` |
| 10 | `GET /v1/cohorts/{cohort_id}/groups` | Preset groups with member counts | `200` |
| 11 | `GET /v1/cohorts/{cohort_id}/groups/{slot}/members` | Members of one group | `200` |
| 12 | `PUT /v1/cohorts/{cohort_id}/groups/{slot}/members` | Replace a group's member list (platform works out adds and removes) | `202` + `job_id` |
| 13 | `GET /v1/cohorts/{cohort_id}/services` | Enabled and available services | `200` |
| 14 | `POST /v1/cohorts/{cohort_id}/services` | **Configure cohort**: enable one or more template services (add-only) | `202` + `job_id` |
| 15 | `GET /v1/jobs` | List jobs, filter by `cohort_id` and `status` | `200` |
| 16 | `GET /v1/jobs/{job_id}` | Job status with all tasks | `200` |

### A.3 Key request bodies
**Designate playground** (`POST /v1/playgrounds`)
```json
{ "folder_id": "361218745460", "display_name": "Learning Sandbox", "template_id": "standard" }
```

**Define cohort** (`POST /v1/playgrounds/{playground_id}/cohorts`)
```json
{
  "cohort_id": "cs100",
  "display_name": "CS 100",
  "project_count": 1,
  "billing_account_id": "XXXXXX-XXXXXX-XXXXXX",
  "members": {
    "admins":   ["cs100-lecturer@shankyram.altostrat.com"],
    "students": ["cs100-student1@shankyram.altostrat.com", "cs100-student2@shankyram.altostrat.com"]
  }
}
```

**Replace members** (`PUT /v1/cohorts/{cohort_id}/groups/{slot}/members`)
```json
{ "members": ["cs100-student1@shankyram.altostrat.com", "cs100-student3@shankyram.altostrat.com"] }
```

**Enable services** (`POST /v1/cohorts/{cohort_id}/services`)
```json
{ "services": ["gcs"] }
```

### A.4 Job and task model
```json
{
  "job_id": "job-20261108-0001",
  "type": "DEFINE_COHORT",
  "cohort_id": "cs100",
  "status": "RUNNING",
  "counts": { "total": 4, "done": 1, "running": 1, "pending": 2, "failed": 0 },
  "tasks": [
    { "id": "precheck",  "label": "Pre-check",                  "status": "DONE" },
    { "id": "projects",  "label": "Create project cs100-p01",   "status": "GETTING_READY", "detail": "billing not enabled yet (attempt 3)" },
    { "id": "groups",    "label": "Create preset groups",       "status": "PENDING" },
    { "id": "members",   "label": "Load members",               "status": "PENDING" }
  ]
}
```
- Job status: `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`.
- Task status: `PENDING`, `APPLYING`, `CREATED`, `GETTING_READY`, `DONE`, `FAILED`, `SKIPPED`.

### A.5 Errors
All errors use one shape. Pre-check failures return `422` with every problem listed.
```json
{
  "error": {
    "code": "PRECHECK_FAILED",
    "message": "2 problems found",
    "details": [
      { "field": "members.students", "problem": "group has no members" },
      { "field": "members.admins[0]", "problem": "user not found in directory: cs100-lect@shankyram.altostrat.com" }
    ]
  }
}
```
| HTTP | Code | When |
|---|---|---|
| `400` | `INVALID_REQUEST` | Malformed body or parameters |
| `401` | `UNAUTHENTICATED` | Missing, invalid or expired bearer token |
| `403` | `PERMISSION_DENIED` | Caller is authenticated but not allowed this action |
| `404` | `NOT_FOUND` | Unknown template, playground, cohort, slot or job |
| `409` | `JOB_IN_PROGRESS` | The cohort already has an active job |
| `422` | `PRECHECK_FAILED` | Pre-check problems (listed in `details`) |
| `500` | `INTERNAL` | Unexpected failure |

---

---

## Appendix B. CLI mapping reference (`lsb`)

> **Reference only, do not edit.** Fixed reference mapping of CLI commands to Appendix A operations. Each command is specified individually together with its operation.

| # | Command | REST call |
|---|---|---|
| 1 | `lsb health` | `GET /v1/health` |
| 2 | `lsb template list` | `GET /v1/templates` |
| 3 | `lsb template show <template_id>` | `GET /v1/templates/{template_id}` |
| 4 | `lsb playground designate --folder <folder_id> --template <template_id> [--name <display_name>]` | `POST /v1/playgrounds` |
| 5 | `lsb playground list` | `GET /v1/playgrounds` |
| 6 | `lsb playground show <playground_id>` | `GET /v1/playgrounds/{playground_id}` |
| 7 | `lsb cohort define <cohort_id> --playground <playground_id> --projects <N> --billing <billing_id> --members <slot>=<file.csv> ...` | `POST /v1/playgrounds/{playground_id}/cohorts` |
| 8 | `lsb cohort list` | `GET /v1/cohorts` |
| 9 | `lsb cohort show <cohort_id>` | `GET /v1/cohorts/{cohort_id}` |
| 10 | `lsb group list <cohort_id>` | `GET /v1/cohorts/{cohort_id}/groups` |
| 11 | `lsb group members <cohort_id> <slot>` | `GET /v1/cohorts/{cohort_id}/groups/{slot}/members` |
| 12 | `lsb group set-members <cohort_id> <slot> --file <file.csv>` | `PUT /v1/cohorts/{cohort_id}/groups/{slot}/members` |
| 13 | `lsb service list <cohort_id>` | `GET /v1/cohorts/{cohort_id}/services` |
| 14 | `lsb service enable <cohort_id> <service> [<service> ...]` | `POST /v1/cohorts/{cohort_id}/services` |
| 15 | `lsb job list [--cohort <cohort_id>] [--status <status>]` | `GET /v1/jobs` |
| 16 | `lsb job show <job_id>` / `lsb job watch <job_id>` | `GET /v1/jobs/{job_id}` (watch polls every 2s) |

### B.1 Global options
| Option | Effect |
|---|---|
| `--json` | Print the raw API response, no colors |
| `--no-wait` | For mutating commands, return the `job_id` without watching |
| `--api <url>` | Override `LSB_API_URL` |
| `NO_COLOR=1` | Disable colors (standard convention) |

### B.2 Member files
Member CSV files contain one email per line (header `email` optional). The seed files in `seed/` can be used as test input.

### B.3 Exit codes
| Code | Meaning |
|---|---|
| `0` | Success (job `SUCCEEDED`, or read command OK) |
| `1` | Job `FAILED` |
| `2` | Request rejected (`400`, `401`, `403`, `404`, `409`, `422`) |
| `3` | API unreachable or `500` |

---
