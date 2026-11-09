# LSB Control Tower Spec: Playground Terraform Pipeline

> Parent: [control-tower-spec.md](control-tower-spec.md)

How playground Terraform runs: when it is triggered, which identities it uses, how its source is secured, and how every run is made predictable, safe to retry and visible. Day-0 Terraform (run by hand with `run.sh`) is covered by [day0-bootstrap-spec.md](day0-bootstrap-spec.md); both share one runner core (section 6).

> No pipeline can guarantee that every run succeeds (eventual consistency, quotas, transient errors). The goal is that every run is **predictable, safe to retry, never destructive and fully visible**, so a failed run is fixed by re-running it.

---

## 1. Purpose and stages

1. **Config stage (no Terraform):** Playground Folders and playgrounds are created by the Self Service APIs with the **user's own token** ([control-tower-spec.md](control-tower-spec.md) section 2.10).
2. **Pipeline stage (Terraform):** only after a playground is **configured** (template, services, owners, groups), the API starts the pipeline for that playground and config version.
3. **Tasks:** each Terraform module of the playground (project creation, then each enabled service in dependency order) is one task in the job, with its own state and readiness check.

```
API (config vN in the config database, job + lock in the runtime and jobs database)
  └─ start predefined Cloud Build trigger (playground ID, config version)
       ├─ prepare: read config vN (read-only), generate tfvars, validate schema, pre-checks
       ├─ for each module in order:
       │    init → plan → policy gate → apply (retry transient) → readiness → task status
       └─ finalize: job status, logs, outputs and runtime state to the runtime and jobs database
```

---

## 2. Identities

| Identity | Does | Rights |
|---|---|---|
| **Cloud Run's service account** (`sa-lsb-api`) | Only **starts** the predefined trigger | Permission to run that trigger and act as the runner. No folder, project or billing rights |
| **Terraform runner** (`sa-control-tower`) | **Runs** Terraform inside Cloud Build | Project Creator on Playground Folders (via the common ancestor), Billing Account User, state bucket access, and what enabled services need |

The internet-facing service never holds provisioning rights.

---

## 3. Secured source (no injected code)

1. **Variables only:** the API passes the playground ID and config version; tfvars are generated from the config database (which the runner can read but not write) and schema-validated. User input never becomes HCL, shell commands or build steps.
2. **Predefined trigger:** the build config (`cloudbuild.yaml`) lives in the repo; only allow-listed substitutions can be passed.
3. **Pinned source:** the trigger is bound to one repo and one protected branch (required reviews, no force-push); modules referenced by tag or commit SHA; providers pinned and the lock file committed.
4. **Pinned builder image:** the Terraform image is referenced by digest (`@sha256:...`), never `:latest`.
5. **Small admin circle:** only a small group can change the trigger, the repo protections or the runner's IAM; changes are audited.
6. **Repo for production:** an org-owned private repo (protected GitHub org repo or Secure Source Manager). This public repo is acceptable only with a protected `main`.

---

## 4. Reliability

### 4.1 Prevent failures before they start
| Control | Catches |
|---|---|
| **Merge checks** on the repo: `terraform fmt -check`, `validate`, a linter, `terraform test` per module | Broken code never reaches the pipeline |
| **Schema-validated inputs** before the build starts | Bad or missing values |
| **Pre-checks before triggering:** runner permissions, required APIs, billing enabled, name availability, quotas | Most "fails halfway" causes |
| **Plan policy gate** inside the build: `terraform plan` → JSON policy check (for example conftest/OPA) → fail if the plan deletes or replaces protected resources, or touches resources outside its playground | Accidental destroys, wrong blast radius |

### 4.2 Reproducible runs
- Pinned builder image (digest), providers (lock file) and modules (tag or SHA).
- Every attempt uses the same versioned tfvars (config version `vN`), so a retry runs exactly the same thing.

### 4.3 Absorb eventual consistency
- **Readiness checks between modules:** project `ACTIVE`, billing enabled, APIs `ENABLED`, service agents present, before the next module runs. No blind `time_sleep`.
- **Retry transient errors only:** a wrapper retries `terraform apply` (for example 3 times with backoff) for recognized retryable errors (billing not yet enabled right after linking, 429 rate limits, propagation errors). Anything else fails immediately.
- **Timeout hierarchy:** Terraform resource timeouts < build step timeout < build timeout, so Terraform exits cleanly and releases its lock.

### 4.4 Make failure harmless
- **Idempotent modules:** additive IAM, no destroys in normal operation, `prevent_destroy` on critical resources. A re-run continues from state and only finishes what is missing.
- **One active job per playground** (Firestore transaction) and **per-playground, per-service state with locking**, so runs never collide.
- **Stale-lock and interruption handling** (as in `run.sh`): failure trap records the error; a stale lock is removed only when the previous run is known to have failed.
- **Never auto-destroy on failure.** A failed job stays `FAILED` with details; the remedy is a re-run.

### 4.5 Make every run visible
- **Each module is a task** with status in the runtime and jobs database (`PENDING → APPLYING → READY / FAILED`); CLI and UI show where a run stopped and why.
- **Build logs** stored in the state bucket and linked from the job.
- **Lost-status reconciliation:** if a build dies before writing its final status, the API reads the build state (`builds.get`) and corrects the job.
- **Nightly read-only `terraform plan`** per playground reports drift.

### 4.6 Quotas that bite at scale
- **Project creation quota** per creating identity and **projects per billing account**: request increases early; pre-check remaining quota.
- **Concurrent Cloud Build builds:** queue or batch playground jobs instead of starting all at once.

### 4.7 Prove it before production
- A **canary Playground Folder** where every pipeline change runs end to end first.

---

## 5. MVP scope
1. **First:** sections 4.2, 4.3, 4.4 and 4.5 (most of the logic already exists in `run.sh`).
2. **Before the first real playground:** the plan policy gate (4.1).
3. **Later:** quota pre-checks (4.6) and nightly drift plans (4.5).

---

## 6. Shared runner core
Day-0 (`run.sh`) and the playground pipeline use the **same runner logic**: plan with detailed exit codes, policy gate, apply, readiness checks, transient retries, failure traps, stale-lock handling, status updates. It is written and tested once and used in both places; only the trigger (human in Cloud Shell vs Cloud Build) and the status target (`controltower.status` vs Firestore) differ.
