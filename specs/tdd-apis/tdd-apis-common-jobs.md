# LSB Control Tower TDD: APIs, Common Jobs

> Parent: [tdd-apis-master.md](tdd-apis-master.md)

> **Status: interim.** This is the working design for jobs. Each part becomes binding only when the first operation that needs it is built, and is refined then, so this spec will change as operations are built one by one. Each operation spec states which parts of this file it relies on.

Every change the platform makes is a **job**: one record, made of ordered **tasks**, that says who asked, what was done, and how it ended. Jobs come in three **kinds** that differ only in who runs the work, as whom, and when. This spec defines the kinds, the shared lifecycle, storage, concurrency, the handler contract, and how each kind is run and tested. The jobs domain ([tdd-apis-jobs.md](tdd-apis-jobs.md), to write) exposes jobs to the CLI and UI. Models: [tdd-apis-common-models.md](tdd-apis-common-models.md) sections 6 and 7. Settings: [tdd-apis-common-config.md](tdd-apis-common-config.md).

---

## 1. The three kinds

| | **JobSync** | **JobAsync** | **JobTerraform** |
|---|---|---|---|
| Use when | The caller's own IAM rights must authorize the change: creating Playground Folders and playgrounds (API operations 07 and 08). **Future use:** group management, or associating groups or users with IAM roles, when the caller's own IAM must be leveraged | Platform-identity work, high volume or retry-heavy (for example 1,000 students entering a playground at once) | Infrastructure declared in Terraform state (playground projects, enabling services) |
| Runs | Inside the API request | A worker, after the response | The Cloud Build pipeline |
| Identity | **The caller**: their OAuth access token from `X-LSB-Access-Token`, used only during the request, never stored | `sa-lsb-worker` | `sa-control-tower` |
| Response | `200` / `201` with the finished Job (`SUCCEEDED` or `FAILED`) | `202` with `Accepted` (`job_id`) | `202` with `Accepted` (`job_id`) |
| Expected duration | Within `LSB_JOB_SYNC_TIMEOUT_SECONDS` (default 30) | Seconds per job; bursts are queued | Minutes |
| Retries | None automatic; the caller re-runs | Automatic with backoff, up to `LSB_JOB_MAX_ATTEMPTS` | Re-run the job; Terraform continues from state |

**Decision rule:** if the caller's own IAM must authorize it, JobSync. Otherwise, if it belongs in Terraform state, JobTerraform. Otherwise, JobAsync. Each operation spec states its kind and why.

---

## 2. Lifecycle

### 2.1 Common steps for every kind (in the request)
1. **Authenticate and authorize** (RequestContext, personas, membership).
2. **Pre-check:** validate the whole request against current state. On any problem, return `422 PRECHECK_FAILED` with every problem listed; **no job is created** (the attempt is logged with its request ID).
3. **Create the job and take the target lock in one transaction** (section 4). If the target already has an active job: `409 JOB_IN_PROGRESS`, no job created.
4. Continue per kind (sections 5 to 7).

### 2.2 Job status

```
JobSync:       RUNNING ─────────────────────────► SUCCEEDED | FAILED
JobAsync:      QUEUED ──► RUNNING ──────────────► SUCCEEDED | FAILED
                  ▲          │ transient error, attempts left
                  └──────────┘
JobTerraform:  QUEUED ──► RUNNING ──────────────► SUCCEEDED | FAILED
```
- `SUCCEEDED`: every task is `DONE` or `SKIPPED`.
- `FAILED`: the job stopped; `error` says why (section 3.2); tasks show how far it got. **Nothing is rolled back.** Steps are idempotent, so running the operation again finishes what is missing.
- Terminal states never change again; a re-run is a new job.

### 2.3 Task status
Tasks are declared when the job is created (all `PENDING`), in execution order, and updated as they run: `PENDING` → `APPLYING` → (`CREATED` → `GETTING_READY` →) `DONE`, or `FAILED`, or `SKIPPED` (nothing to do, for example a member already present). `CREATED` and `GETTING_READY` are used when a resource exists but is not usable yet (eventual consistency).

---

## 3. Shared model and storage

### 3.1 Storage (runtime and jobs database, [tdd-master.md](../tdd-master.md) section 1.9)

```
lsb-control-tower-db
  jobs/{job_id}                    Job fields (models section 6) + internal fields below
  jobs/{job_id}/tasks/{task_id}    Task fields (models section 7), plus "order"
  locks/{target_kind}:{target_id}  { job_id, kind, acquired_at, lease_expires_at }
```
- **Job IDs:** `job-<YYYYMMDD>-<8 hex>` (date plus random), for example `job-20261109-7f3a9c21`. No sequence counter, so no write hotspot.
- **Internal fields** (stored, not returned by the API): `lease_expires_at`, `attempt`, `dispatch` (`{mode, ref}`: Cloud Tasks task name or Cloud Build build ID), `request` (the validated request body, no tokens), `handler_version`.
- **Never stored:** access tokens or any credential.
- **Retention:** kept indefinitely ([tdd-master.md](../tdd-master.md) section 1.9).

### 3.2 Additions to the Job model
| Field | Type | Description |
|---|---|---|
| `kind` | enum | `SYNC`, `ASYNC`, `TERRAFORM` |
| `attempt` | integer | Run attempts so far (`1` for JobSync) |
| `error` | `{code, message}` | Set when `FAILED`. Codes: `TASK_FAILED` (a task failed; see its `detail`), `TIMEOUT` (JobSync time budget exceeded), `INTERRUPTED` (the runner stopped without finishing, found by lease expiry), `DISPATCH_FAILED` (could not be queued), `ATTEMPTS_EXHAUSTED` (JobAsync retries used up), `INTERNAL` |

---

## 4. Concurrency: one active job per target

1. Every job has a **target** (`{kind, id}`, for example `PLAYGROUND:ba101-2026`, `GROUP:grp-lsb-bu-admins@...`).
2. Creating a job and writing `locks/{target_kind}:{target_id}` happen in **one Firestore transaction**. If the lock exists and its lease has not expired, the request gets `409 JOB_IN_PROGRESS`.
3. The lock is **released in the same transaction** that sets the job's terminal status.
4. **Leases** make crashes harmless: the runner renews `lease_expires_at` (heartbeat) while working. A lock whose lease has expired is stale: the next job for that target, or the reconcile job, marks the old job `FAILED` with `INTERRUPTED` and takes over.
5. Operations that touch many independent targets (for example students entering a playground) use **one job per student**, each with its own target, so they never block each other.

---

## 5. JobSync execution

1. After section 2.1, the job is created as `RUNNING` (`attempt` 1, lease = `LSB_JOB_SYNC_TIMEOUT_SECONDS` plus a margin).
2. The handler runs **in the request**, with credentials built from the caller's `X-LSB-Access-Token`. GCP enforces the caller's own IAM; a `PERMISSION_DENIED` from GCP fails the task with that message.
3. Each task is written to Firestore as it changes, so `lsb jobs show` sees progress even during the call.
4. On finish: terminal status, lock released, response `200` (existing target) or `201` (created) with the full Job. A `FAILED` job is still a `200`/`201` response; the CLI exits `1` (job failed).
5. If the time budget is exceeded: the job is marked `FAILED` with `TIMEOUT` at the task reached. An operation that cannot reliably finish in the budget is in the wrong kind.
6. If the API process dies mid-request, the lease expires and section 4 rule 4 marks the job `INTERRUPTED`.

---

## 6. JobAsync execution

### 6.1 Submit (in the request)
1. After section 2.1, the job is created as `QUEUED`.
2. `dispatcher.submit(job_id)` (section 6.3). If submitting fails, the job is set to `FAILED` with `DISPATCH_FAILED`, the lock is released, and the request returns `500` with the job ID.
3. Response `202` with `Accepted`.

### 6.2 Run (worker)
1. **Claim** in a transaction: a `QUEUED` job (or a `RUNNING` job whose lease has expired) becomes `RUNNING`, `attempt` + 1, new lease of `LSB_JOB_LEASE_SECONDS`. A job that is terminal, or `RUNNING` with a valid lease, is acknowledged and skipped (duplicate delivery is harmless).
2. **Run** the handler with platform credentials (`sa-lsb-worker`), renewing the lease while working and updating tasks.
3. **Finish:**
   - Success: `SUCCEEDED`, lock released, acknowledge.
   - Permanent error (bad state, denied): `FAILED` with `TASK_FAILED`, lock released, acknowledge.
   - Transient error (quota, `UNAVAILABLE`, timeout) with attempts left: job set back to `QUEUED` (keeping completed tasks), and the delivery is answered with an error so it is retried with backoff.
   - Attempts used up: `FAILED` with `ATTEMPTS_EXHAUSTED`, lock released, acknowledge.
4. **Idempotency:** every step checks before acting (exists, already a member, already granted), so a retried or duplicated run only finishes what is missing.

### 6.3 Dispatcher modes (`LSB_JOB_DISPATCHER`)

| Mode | `submit(job_id)` does | Worker | Use |
|---|---|---|---|
| `inline` (default locally) | Starts the run in the API process right after the response | The API process itself | Day-to-day development and live tests: `lsb ...` then `lsb jobs watch` behaves as in production |
| `http` | `POST {LSB_WORKER_URL}/internal/jobs/{job_id}/run` | `lsb-api-server.sh --worker` on another port | Testing the real worker contract without GCP queues |
| `cloudtasks` | Creates a Cloud Task named after `job_id` (de-duplication) on `LSB_TASKS_QUEUE`, targeting the worker URL with an OIDC token | Cloud Run service `lsb-worker` (same image), only invocable by the API's identity | Deployed |

- The **queue** sets the burst behavior: maximum concurrent dispatches and dispatches per second (protecting GCP quotas), maximum attempts and backoff.
- **Lost dispatch:** the reconcile job re-submits jobs `QUEUED` for longer than a few minutes.
- The worker endpoint is internal: in `cloudtasks` mode only Cloud Tasks can call it (Cloud Run IAM); in `http` mode it listens on localhost only.

---

## 7. JobTerraform execution (contract)

1. After section 2.1, the job is created as `QUEUED`.
2. The dispatcher **starts the predefined Cloud Build trigger** with the job ID, target and config version; the build ID is stored in `dispatch`. Response `202`.
3. The pipeline's runner (shared runner core, [tdd-playground-master.md](../tdd-playground/tdd-playground-master.md) section 6) claims the job, runs one task per Terraform module, updates tasks in Firestore, and finishes the job and releases the lock.
4. **Lost status:** if a job stays `RUNNING` past its lease, the API checks the build (`builds.get`) and corrects the job.

Details (identities, secured source, policy gate) are in the playground pipeline spec.

---

## 8. Handler contract (code)

One handler per job `type`, registered with its kind:
```python
@job_handler(type="SET_PLATFORM_USERS", kind=JobKind.ASYNC)
class SetPlatformUsers(JobHandler):
    def tasks(self, request) -> list[TaskSpec]: ...        # declared up front, in order
    async def run(self, job: Job, ctx: JobContext) -> None: ...
```
- `ctx.task(task_id)` is a context manager that sets `APPLYING`, then `DONE` (or `FAILED` with the exception message); `ctx.skip(task_id, why)`, `ctx.progress(task_id, status, detail)` for `CREATED` / `GETTING_READY`.
- `ctx.gcp` gives the GCP clients for the job's identity: the caller's credentials (JobSync) or platform credentials (JobAsync). Always real GCP: there is no fake or simulated mode.
- `ctx` renews the lease automatically while `run` is active.
- Handlers raise `TransientError` for retryable failures and any other exception for permanent ones.
- Code layout: `src/api/lsb_api/jobs/` (`model.py`, `store.py` (Firestore, transactions, locks), `dispatch.py`, `runner.py`, `registry.py`), with handlers next to their domain router.

---

## 9. Development and testing

| Level | How |
|---|---|
| Unit | Code-level tests of pure logic: store transaction rules (lock conflict, claim, lease expiry, release) and handler step logic, with test doubles inside the test only |
| Local end to end | `./lsb-api-server.sh` with `LSB_JOB_DISPATCHER=inline` (default) against the real Firestore and real GCP in the live environment |
| Worker contract | `LSB_JOB_DISPATCHER=http` with a local `--worker` process |
| Deployed | `cloudtasks`, Cloud Run worker |

No fake, simulated or dry-run handling: jobs always act on real GCP, and no request carries a test flag. The only switch is how JobAsync jobs are dispatched.

---

## 10. Settings (added to [tdd-apis-common-config.md](tdd-apis-common-config.md))

| Key | Default | Meaning |
|---|---|---|
| `LSB_JOB_DISPATCHER` | `inline` | `inline`, `http` or `cloudtasks` |
| `LSB_WORKER_URL` | `http://127.0.0.1:8081` | Worker base URL (`http` and `cloudtasks` modes) |
| `LSB_TASKS_QUEUE` | `lsb-jobs` | Cloud Tasks queue name (`cloudtasks` mode, in `REGION`) |
| `LSB_JOB_SYNC_TIMEOUT_SECONDS` | `30` | JobSync time budget |
| `LSB_JOB_LEASE_SECONDS` | `120` | JobAsync lease, renewed while running |
| `LSB_JOB_MAX_ATTEMPTS` | `5` | JobAsync attempts before `ATTEMPTS_EXHAUSTED` |
