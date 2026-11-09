# Control Tower Day-0 Bootstrap

Creates the Learning Sandbox **Control Tower** foundation, one operation at a time. Run once by an org admin.

Full design: [tdd-control-tower-master.md](../../../specs/02-tdd/tdd-control-tower/tdd-control-tower-master.md)

---

## 1. What you need

| Requirement | Detail |
|---|---|
| Account | Org admin with **Folder Creator** on the parent folder, **Project Creator**, and **Billing User** on the billing account |
| Quota project | An existing project with these APIs enabled: Resource Manager, Service Usage, Cloud Billing, Cloud Storage |
| Tools | `terraform` 1.5+, `gcloud`, `jq`, `envsubst`, `git`. Cloud Shell has all except possibly `terraform`: install it with `./install-terraform.sh` (see below) |

Install Terraform if `terraform version` fails (optional, standalone, no sudo):
```bash
./install-terraform.sh                 # Terraform 1.17.1 into ~/.local/bin, verified against HashiCorp checksums
export PATH="$HOME/.local/bin:$PATH"   # this shell; new shells pick it up from ~/.bashrc
```
Options: `--version=<x.y.z|latest>`, `--dir=<install dir>`, `--no-profile` (do not edit `~/.bashrc`). Safe to re-run.

Enable the APIs on the quota project if needed:
```bash
gcloud services enable cloudresourcemanager.googleapis.com serviceusage.googleapis.com \
  cloudbilling.googleapis.com storage.googleapis.com --project=<QUOTA_PROJECT>
```

---

## 2. Run it (Cloud Shell)

1. Sign in to the Google Cloud console as the org admin and open **Cloud Shell**.
2. Clone the repo and go to this folder:
   ```bash
   git clone https://github.com/shankyram1912/crucible-learning-sandbox.git
   cd learning-sandbox/src/terraform/control-tower
   ```
3. Create your settings file and fill it in:
   ```bash
   cp initialize.env.example initialize.env
   ```
   Required for the first operation: `QUOTA_PROJECT`, `ORG_ID`, `BILLING_ACCOUNT_ID`, `CT_FOLDER_NAME`, `CT_FOLDER_PARENT`, `CT_PROJECT_ID`, `REGION`, `TF_STATE_BUCKET`.
   Billing labels (`LABEL_COST_CENTER_BU`, `LABEL_COST_CENTER_CODE`, `LABEL_COST_CATEGORY`, `LABEL_BU_TRACKING_CODE`, `LABEL_BU_SUBCATEGORY`) are required; they are applied to the Control Tower project, which attributes all its costs in billing.
   `CT_PROJECT_ID` and `TF_STATE_BUCKET` default to names derived from the org ID (for example `lsb-control-tower-e26`); leave them as they are unless you need different names.
4. Check everything before changing anything:
   ```bash
   ./run.sh --operation=ControlTowerProjectCreate --validate-only
   ```
5. Run the operation. It prints a long description, validates, shows the Terraform plan, and asks `Proceed? [y/N]`:
   ```bash
   ./run.sh --operation=ControlTowerProjectCreate
   ```
6. Check progress at any time:
   ```bash
   ./run.sh --operation=Status
   ```

**tmux is built in.** In an interactive terminal, `run.sh` starts the operation inside a tmux session named `lsb-day0`, so a closed browser tab or dropped connection does not kill a running apply.
- Detach on purpose: `Ctrl-b` then `d`
- Reattach after a disconnect: `tmux attach -t lsb-day0`
- When the run finishes, press Enter to close the session.
- If the Cloud Shell VM itself is recycled, the run stops; just run the same operation again (status and Terraform state are kept).

---

## 3. Operations

| Operation | Does |
|---|---|
| `ControlTowerProjectCreate` | Control Tower folder (created, or existing via `CT_FOLDER_ID`), project with billing, Cloud Storage API, Terraform state bucket |
| `ControlTowerApisEnable` | Baseline APIs on the Control Tower project (platform, observability, billing, Firestore, storage, Cloud Run, Artifact Registry, Cloud Build, Secret Manager, Cloud Identity, Directory) and the Cloud Run, Cloud Build and Artifact Registry service agents. Compute is not enabled (networking comes later) |
| `ControlTowerFirestoreCreate` | Two Firestore databases (Native mode, in `REGION`) with point-in-time recovery and delete protection: `FIRESTORE_CONFIG_DATABASE` for config (desired state, weekly backups kept 14 weeks) and `FIRESTORE_DATABASE` for runtime state and jobs (kept indefinitely, no TTL) |
| `PlaygroundGroupsCreate` | Playground service groups `IT_ADMINS_GROUP` and `BU_ADMINS_GROUP` (IT Admins nested in BU Admins), plus the initial IT Admins from `IT_ADMINS_INITIAL_MEMBERS`. Needs a Super Admin (or Groups Admin able to manage locked groups) and the Cloud Identity API on the quota project |
| `PlaygroundTagsCreate` | Five dynamic playground tag keys at org level (`cost-center-bu`, `cost-center-code`, `cost-category`, `bu-tracking-code`, `bu-subcategory`, allowed-values pattern, no values) and Tag User on them: the first three for `IT_ADMINS_GROUP`, `bu-tracking-code` and `bu-subcategory` for `BU_ADMINS_GROUP`. Needs Tag Administrator (or Organization Administrator) on the org. Uses google provider `~> 8.0` |
| `RunAll` | Runs bootstrap operations in order: `--from=<Operation>` (default: first) `--to=<Operation>` (default: last). Each operation still shows its description, validates, shows its plan and asks to proceed (unless `--yes`). Stops at the first failure and prints a summary |
| `Status` | Progress of all operations: status, time, who ran it, git commit |
| `Restore` | In a fresh Cloud Shell: pulls `initialize.env`, `controltower.status` and logs back from the state bucket |

Run them in order: `ControlTowerProjectCreate`, `ControlTowerApisEnable`, `ControlTowerFirestoreCreate`, `PlaygroundGroupsCreate`, `PlaygroundTagsCreate`, or use `RunAll`:
```bash
./run.sh --operation=RunAll                                   # all operations, first to last
./run.sh --operation=RunAll --from=ControlTowerApisEnable      # from an operation to the end
./run.sh --operation=RunAll --to=ControlTowerApisEnable        # from the start to an operation
./run.sh --operation=RunAll --from=ControlTowerApisEnable --to=ControlTowerFirestoreCreate
./run.sh --operation=RunAll --validate-only                   # validate every operation in the range
``` More operations (Firestore, service accounts, pipelines, networking) are added one by one.

### Flags
| Flag | Effect |
|---|---|
| `--validate-only` | Run the operation's checks only, change nothing |
| `--describe` | Print the operation's long description only |
| `--yes` | Skip the `Proceed?` prompt |
| `--force` | Run even if the previous operation is not `DONE` |
| `--no-tmux` | Run in the current shell instead of the `lsb-day0` tmux session |
| `--from=<Operation>` / `--to=<Operation>` | `RunAll` only: first and last operation of the range (defaults: first and last) |

---

## 4. Files

| File | Purpose | In git? |
|---|---|---|
| `initialize.env.example` | Settings template | Yes |
| `initialize.env` | Your settings, plus values written back by operations (generated section) | No |
| `initialize.sh` | Loads and validates settings. `run.sh` uses it automatically; source it yourself (`source ./initialize.sh`) only for ad-hoc `terraform` or `gcloud` commands | Yes |
| `run.sh` | Operation runner | Yes |
| `install-terraform.sh` | Optional standalone Terraform installer | Yes |
| `controltower.status` | Progress per operation | No |
| `logs/` | One log per run | No |
| `01-control-tower-project-create/` | Terraform for the first operation, plus [operation.md](01-control-tower-project-create/operation.md) (its long description) | Yes |
| `02-control-tower-apis-enable/` | Terraform for the second operation, plus [operation.md](02-control-tower-apis-enable/operation.md) | Yes |
| `03-control-tower-firestore-create/` | Terraform for the third operation, plus [operation.md](03-control-tower-firestore-create/operation.md) | Yes |
| `04-playground-groups-create/` | Terraform for the fourth operation, plus [operation.md](04-playground-groups-create/operation.md) | Yes |
| `05-playground-tags-create/` | Terraform for the fifth operation, plus [operation.md](05-playground-tags-create/operation.md) | Yes |

After each successful operation, `initialize.env`, `controltower.status` and `logs/` are copied to `gs://<TF_STATE_BUCKET>/control-tower/_runner/`.

---

## 5. Re-runs and recovery

- **Re-running a `DONE` operation is safe.** Terraform shows no changes.
- **Interrupted or failed run:** fix the cause shown in the error, then run the same operation again. Terraform continues from its state. An interruption (Ctrl-C, killed tmux session, recycled Cloud Shell VM) is recorded as `FAILED` with `interrupted (SIG...)`.
- **Stale state lock:** if an interrupted run left a Terraform state lock in the bucket, the next run shows the lock (ID, who, age) and offers to remove it. It only does so when the previous run of that operation ended `FAILED` or interrupted; with `--yes` it removes it automatically only if the lock is older than 60 minutes.
- **New Cloud Shell or another admin:** clone the repo, create `initialize.env` with at least `QUOTA_PROJECT` and `TF_STATE_BUCKET`, then:
  ```bash
  ./run.sh --operation=Restore
  ./run.sh --operation=Status
  ```

There is no destroy operation. The project, folder and bucket are protected from deletion.

---

## 6. Troubleshooting

| Message | Fix |
|---|---|
| `tool not found: terraform` | Run `./install-terraform.sh`, then `export PATH="$HOME/.local/bin:$PATH"` |
| `initialize.sh must be sourced` | Use `source ./initialize.sh`, or just use `./run.sh` |
| `quota project ... is missing APIs` | Run the `gcloud services enable ...` command printed in the message |
| `quota project ... not reachable` | Check you can access it, and that Resource Manager API is enabled on it |
| `billing account ... not visible` | You need Billing User (or Viewer) on the billing account |
| Project create fails with `already exists` | Project IDs are global and never reusable. Set a different `CT_PROJECT_ID` in `initialize.env` and re-run (the folder is kept) |
| Bucket create fails right after project creation | Billing can take a minute to propagate. Re-run the operation |
| `Error acquiring the state lock` / `State is locked but the previous run is not marked interrupted or failed` | Another run may be in progress. If you are sure it is stale: `terraform -chdir=<operation folder> force-unlock <lock ID>` (the message prints the exact command) |
| `... must be DONE before ...` | Run the earlier operation first, or use `--force` deliberately |
| `A tmux session 'lsb-day0' already exists` | A run may still be going: `tmux attach -t lsb-day0`. If it is finished or stale: `tmux kill-session -t lsb-day0` |
