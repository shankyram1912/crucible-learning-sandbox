# ManualGround: Shared-Shard Multi-Student Provisioner and Isolation Verifier

ManualGround provisions and verifies strict cross-student isolation for up to 80 students inside a single Google Cloud shard project across six managed services:

1. **Unified Student Service Account and Vertex AI Gemini (`gemini`)**: Dedicated `sa-<student>` identity per student with zero service account keys, zero API keys, and scoped `custom_ntu_gemini_caller` access.
2. **Cloud Storage (`gcs`)**: Dedicated `bkt-<project>-<student>` bucket per student in asia-southeast1 with Uniform Bucket-Level Access and Public Access Prevention enforced.
3. **Cloud Run and Artifact Registry (`run`)**: Dedicated `ar-<student>` Docker repository per student paired with **On-Demand ClickOps + Eventarc Auto-Owner (`ntu-run-auto-owner`)**, allowing students to deploy services on demand while automatically binding per-service `custom_ntu_run_owner` permissions and enforcing `MAX_SERVICES_PER_STUDENT=3`.
4. **Cloud SQL for PostgreSQL 16 (`sql`)**: Shared `sql-<project>` instance with per-student logical database `db_<student>`, IAM database users (`CLOUD_IAM_USER` and `CLOUD_IAM_SERVICE_ACCOUNT`), `REVOKE ALL ON DATABASE ... FROM PUBLIC`, and connection limits.
5. **Firestore (`firestore`)**: Named Native database `fs-<student>` per student (leaving `(default)` uncreated so unconfigured SDK calls fail fast) secured by conditional v3 IAM bindings (`custom_ntu_firestore_db_user`).
6. **Vertex AI Search (`search`)**: Unstructured GCS Data Store `ds-<student>` and Search Engine `eng-<student>` per student with data store access control enabled.

## Two-Layer Architecture

Onboarding 80 students across six services creates over 1,100 resources and IAM bindings per shard project. Putting static shard foundations and per-student resources into a single Terraform state causes state-refresh API storms, Cloud Resource Manager `409 ABORTED` ETag collisions, and serialized Cloud SQL operation lockouts. ManualGround splits the workflow into two clean layers:

* **Layer 1 (`terraform/`)**: Declarative Terraform operations executed once per shard to establish folder guardrails (Org Policies and IAM Deny v2), the shard project and custom IAM roles, the `ntu-run-auto-owner` Cloud Run service and Eventarc audit-log triggers, and the shared PostgreSQL 16 instance.
* **Layer 2 (`./mg` Python CLI and `manualground` library)**: Idempotent, token-bucket rate-paced bulk API runner and adversarial cross-student verifier (`Student A` vs `Student B`). `manualground.core` and `manualground.services` have zero CLI or UI dependencies so Crucible can import and execute them directly.

## Prerequisites

* Python 3.12+ and `uv`
* Google Cloud SDK (`gcloud`) authenticated with Application Default Credentials (`gcloud auth login` and `gcloud auth application-default login`)
* `jq` and `envsubst` (for `terraform/run.sh`)
* Terraform 1.5+ (available on this workstation at `/usr/local/google/home/shankyram/workspace/code-sandbox/tools/terraform-1.17.1/terraform` or `~/.local/bin/terraform`)
* Optional: `psql` client when executing live PostgreSQL 16 data-plane isolation DDL directly

## Step 1: Configure `initialize.env`

Copy the template and fill in your organization, folder, project, billing, and group values:

```bash
cd src/manualground
cp initialize.env.example initialize.env
# Edit initialize.env with your shard settings, then validate exports:
source ./initialize.sh
```

 Note that `initialize.env` and `uv.lock` are gitignored and must never be committed.

## Step 2: Run Layer 1 Terraform Baseline (`terraform/run.sh`)

Inspect or execute the four Layer 1 operations in order:

```bash
./terraform/run.sh --operation=Status
./terraform/run.sh --operation=RunAll
```

You can also run a single operation or validate without applying changes:

```bash
./terraform/run.sh --operation=FolderGuardrailsCreate --validate-only
./terraform/run.sh --operation=ShardProjectCreate
./terraform/run.sh --operation=CloudRunAutoOwnerCreate
./terraform/run.sh --operation=SharedCloudSqlCreate
```

### LONG-RUNNING Layer 1 Operations and Live Watch Commands

Two Layer 1 Terraform operations provision asynchronous Google Cloud control-plane resources that take more than five minutes. Both carry explicit Terraform `timeouts` blocks and can be monitored from a second terminal while `terraform apply` runs:

| Operation | Resource | Typical Duration | Terraform Timeout | Live Watch Command |
| :--- | :--- | :--- | :--- | :--- |
| `03-cloud-run-auto-owner` (`CloudRunAutoOwnerCreate`) | **LONG-RUNNING**: Cloud Audit Log Eventarc triggers (`v1` and `v2` `CreateService`) and Pub/Sub transport readiness | **5 to 12 minutes** | `20m` | `watch -n 10 "gcloud eventarc triggers list --location=$REGION --project=$MG_PROJECT_ID"` |
| `04-shared-cloud-sql` (`SharedCloudSqlCreate`) | **LONG-RUNNING**: Shared Cloud SQL for PostgreSQL 16 instance (`sql-<project>`) creation and initial backup configuration | **10 to 20 minutes** | `45m` | `watch -n 15 "gcloud sql operations list --instance=sql-$MG_PROJECT_ID --project=$MG_PROJECT_ID --limit=5"` |

Additional diagnostic commands during Layer 1 provisioning:

```bash
# Check ntu-run-auto-owner Cloud Run service health:
gcloud run services describe ntu-run-auto-owner --region="$REGION" --project="$MG_PROJECT_ID"

# Check Cloud SQL instance state (target state: RUNNABLE) and IAM authentication flag:
gcloud sql instances describe "sql-$MG_PROJECT_ID" --project="$MG_PROJECT_ID" \
  --format="table(name,state,databaseVersion,settings.databaseFlags)"
```

Set `ENABLE_CLOUD_SQL=false` in `initialize.env` if a cohort does not require Cloud SQL and you want to skip Operation 04.

## Step 3: Install and Inspect the Layer 2 CLI (`./mg`)

Synchronize the local `.venv` with `uv` and run `./mg --help`:

```bash
uv sync
./mg --help
./mg status
./mg baseline status
```

## Step 4: Provision a Student Roster and Verify Isolation

1. **Validate the roster CSV offline** (checks email syntax, normalized slugs, 30-character service account truncation, 63-character bucket/database bounds, and collision detection):

   ```bash
   ./mg roster validate rosters/sample-2students.csv
   ```

2. **Run shard preflight checks** (verifies enabled APIs, instance states, and shard quota headroom):

   ```bash
   ./mg preflight --roster rosters/sample-2students.csv
   ```

3. **Apply Layer 2 per-student slices** (resumable via checkpoint ledger in `state/<project_id>-ledger.json`):

   ```bash
   # Provision all active services for every student in the CSV:
   ./mg roster apply rosters/sample-2students.csv

   # Filter to specific services or a single student, or emit JSON:
   ./mg roster apply rosters/sample-2students.csv --services gemini,gcs,run --student lsb-student1
   ./mg roster apply rosters/sample-2students.csv --dry-run --json
   ```

   `./mg roster apply` executes three stages:
   * **Stage A (Identity Barrier)**: Creates `sa-<student>` accounts and per-SA impersonation policies first, pausing 15 seconds when new service accounts are created so downstream resource IAM bindings resolve cleanly.
   * **Stage B (Rate-Paced Service Drivers)**: Runs each service through dedicated `TokenBucketLimiter` budgets (`sql_admin` enforced at `concurrency=1` with LRO polling) and writes atomic per-slice checkpoints to `state/<project_id>-ledger.json`. Re-running `./mg roster apply` automatically skips `COMPLETED` slices unless `--no-resume` is passed.
   * **Stage C (Single-Shot Coalesced Project IAM Commit)**: Merges all conditional v3 IAM bindings (`custom_ntu_firestore_db_user`) into a single `projects.getIamPolicy` / `projects.setIamPolicy` cycle (`requestedPolicyVersion=3`) with automatic `409 ABORTED` ETag retry and hard safety stops at **1,400 principals** and **95 conditional bindings**.

4. **Verify positive access and adversarial cross-student isolation (`Student A` vs `Student B`)**:

   ```bash
   ./mg verify rosters/sample-2students.csv
   ./mg verify rosters/sample-2students.csv --services gcs,firestore,run --json
   ```

## Enforced API Rate Budgets

| Limiter Name | Pacing (RPM) | Spacing | Target Operations |
| :--- | :--- | :--- | :--- |
| `iam` | 45 RPM | 1.33s | `serviceAccounts.create`, `serviceAccounts.setIamPolicy` |
| `storage_bucket` | 24 RPM | 2.50s | `buckets.insert` (under GCP project bucket creation spike limits) |
| `storage_iam` | 60 RPM | 1.00s | `buckets.getIamPolicy`, `buckets.setIamPolicy` |
| `artifact_registry` | 25 RPM | 2.40s | `repositories.create` (below 30 RPM regional cap) |
| `cloud_run` | 30 RPM | 2.00s | On-demand verification `services.create` / `patch` / `delete` |
| `sql_admin` | 20 RPM | 3.00s (`concurrency=1`) | Serialized `databases.insert`, `users.insert`, and `operations.get` |
| `firestore_admin` | 15 RPM | 4.00s | `projects.databases.create` Native mode LROs |
| `discovery_engine` | 15 RPM | 4.00s | `dataStores.create`, `engines.create`, and resource `setIamPolicy` |
| `import_documents` | 5 RPM | 12.00s | `documents:import` GCS synchronization |
| `crm_iam` | 15 RPM | 4.00s | Coalesced `projects:getIamPolicy` and `projects:setIamPolicy` |

## Testing

Run the fast offline unit and static Terraform validation suite (zero live network calls):

```bash
uv run pytest tests/unit
```

Run the live end-to-end Student A vs Student B cross-tenant verification matrix against a deployed shard:

```bash
MG_LIVE_E2E=1 uv run pytest -m e2e
```
