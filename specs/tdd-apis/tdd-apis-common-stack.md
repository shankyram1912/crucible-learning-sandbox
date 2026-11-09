# LSB Control Tower TDD: APIs, Common Stack

> Parent: [tdd-apis-master.md](tdd-apis-master.md)

Tech stack, where the CLI runs, and packaging, for all API domains.

---

## 1. Tech stack and reasoning

| Part | Choice | Why |
|---|---|---|
| **REST API** | Python 3.12 + **FastAPI** | Same language as the provisioning code (Terraform runner, Cloud Identity, Firestore SDKs). Typed request/response models (Pydantic) with validation built in. Generates OpenAPI docs at `/docs` for free, which is the contract for the CLI now and a UI later. Native async fits long-running jobs. |
| **State** | **Firestore**, two databases in `lsb-control-tower`: `lsb-control-tower-config-db` (config, desired state) and `lsb-control-tower-db` (runtime state and jobs), see [tdd-master.md](../tdd-master.md) section 1.9 | Serverless, no instance to run. Document model fits playgrounds, jobs and tasks. A transaction in the runtime and jobs database enforces one active job per playground. Real-time listeners let a future UI show live job progress without polling (read-only, section 3.5). |
| **Provisioning** | **Terraform** (seed cohort, enable service) + **Google Cloud SDKs** (membership, readiness checks) | Per [tdd-master.md](../tdd-master.md): Terraform only where it adds value; fast directory and data operations use the APIs directly. |
| **CLI commands** | Python + **Typer** | Same author and style as FastAPI: plain functions with type hints become commands. Can reuse the API's Pydantic models so CLI and API cannot drift. Built-in `--help`, nested commands and shell completion. Built on Click, the mature Python CLI standard. |
| **CLI output** | **Rich** | Colors, tables, trees, live in-place updates and spinners (needed for `job watch`), pretty JSON and error panels. Disables color automatically when output is not a terminal or `NO_COLOR` is set. Typer uses Rich for help formatting, so they fit together. |
| **CLI HTTP + auth** | **httpx** + **google-auth** | Small, modern HTTP client. `google-auth` obtains Google ID tokens from the user's gcloud login / ADC without needing the Google Cloud client libraries in the CLI. |
| **CLI name** | `lsb` | Short for Learning Sandbox. |

**Trade-off accepted:** a Python CLI needs Python and a venv where it runs, and starts in about 0.2 to 0.3 seconds. Fine for the MVP. If the CLI is later distributed to university admins as a download, a Go single binary can replace it without touching the API, because the CLI only speaks REST.

---

## 2. Where the CLI can run
The CLI only needs network reach to the API and a Google login. It never talks to GCP or Firestore.

| Setup | How the CLI reaches the API |
|---|---|
| **Same VM** (MVP default) | `LSB_API_URL=http://localhost:8080` |
| **Laptop to API on the Control Tower VM** | SSH tunnel `ssh -L 8080:localhost:8080 <vm>`, then `LSB_API_URL=http://localhost:8080` |
| **Anywhere to API on Cloud Run** (later) | `LSB_API_URL=https://<service>.asia-southeast1.run.app` |
| **Cloud Shell** | Same as Cloud Run, using the Cloud Shell login |

In every setup the bearer token is required.

---

## 3. Packaging
- **API:** `src/api`, runs locally on the Control Tower VM for the MVP; Cloud Run in `asia-southeast1` later.
- **CLI:** `src/cli`, its own small package (Typer, Rich, httpx, google-auth), installable with `pip` from the repo.
