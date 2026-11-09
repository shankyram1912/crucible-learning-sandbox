# Self Service APIs v0 interface (reference only)

Frozen REST and CLI reference from the first API draft, moved here from `specs/tdd-apis/tdd-apis-master.md` (Appendices A and B) on 2026-11-09. It predates the playground model: "cohort" means **playground**, and playgrounds live inside **Playground Folders** created by the platform. Current specs: [specs/tdd-apis/tdd-apis-master.md](../specs/tdd-apis/tdd-apis-master.md); each domain spec states which rows here it replaces.

## Appendix A. REST interface reference (`/v1`)

> **Reference only, do not edit.** This appendix is the fixed reference list of resources and operations. Each operation is specified in its domain spec before it is implemented.

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
