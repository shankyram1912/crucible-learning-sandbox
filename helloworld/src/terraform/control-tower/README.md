# Control Tower Day-0 Bootstrap

Creates the Learning Sandbox **Control Tower** foundation, one operation at a time. Run once by an org admin.

Full design: [day0-bootstrap-spec.md](../../../specs/day0-bootstrap-spec.md)

---

## 1. What you need

| Requirement | Detail |
|---|---|
| Account | Org admin with **Folder Creator** on the parent folder, **Project Creator**, and **Billing User** on the billing account |
| Quota project | An existing project with these APIs enabled: Resource Manager, Service Usage, Cloud Billing, Cloud Storage |
| Tools | `terraform` 1.5+, `gcloud`, `jq`, `envsubst`, `git` (all preinstalled in Cloud Shell) |

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
   git clone https://github.com/shankyram1912/learning-sandbox.git
   cd learning-sandbox/helloworld/src/terraform/control-tower
   ```
3. Create your settings file and fill it in:
   ```bash
   cp initialize.env.example initialize.env
   ```
   Required for the first operation: `QUOTA_PROJECT`, `ORG_ID`, `BILLING_ACCOUNT_ID`, `CT_FOLDER_NAME`, `CT_FOLDER_PARENT`, `CT_PROJECT_ID`, `REGION`, `TF_STATE_BUCKET`.
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
| `Status` | Progress of all operations: status, time, who ran it, git commit |
| `Restore` | In a fresh Cloud Shell: pulls `initialize.env`, `controltower.status` and logs back from the state bucket |

More operations (APIs, Firestore, service accounts, pipelines) are added one by one.

### Flags
| Flag | Effect |
|---|---|
| `--validate-only` | Run the operation's checks only, change nothing |
| `--describe` | Print the operation's long description only |
| `--yes` | Skip the `Proceed?` prompt |
| `--force` | Run even if the previous operation is not `DONE` |
| `--no-tmux` | Run in the current shell instead of the `lsb-day0` tmux session |

---

## 4. Files

| File | Purpose | In git? |
|---|---|---|
| `initialize.env.example` | Settings template | Yes |
| `initialize.env` | Your settings, plus values written back by operations (generated section) | No |
| `initialize.sh` | Loads and validates settings. `run.sh` uses it automatically; source it yourself (`source ./initialize.sh`) only for ad-hoc `terraform` or `gcloud` commands | Yes |
| `run.sh` | Operation runner | Yes |
| `controltower.status` | Progress per operation | No |
| `logs/` | One log per run | No |
| `01-control-tower-project-create/` | Terraform for the first operation, plus `operation.md` (its long description) | Yes |

After each successful operation, `initialize.env`, `controltower.status` and `logs/` are copied to `gs://<TF_STATE_BUCKET>/control-tower/_runner/`.

---

## 5. Re-runs and recovery

- **Re-running a `DONE` operation is safe.** Terraform shows no changes.
- **Interrupted or failed run:** fix the cause shown in the error, then run the same operation again. Terraform continues from its state.
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
| `initialize.sh must be sourced` | Use `source ./initialize.sh`, or just use `./run.sh` |
| `quota project ... is missing APIs` | Run the `gcloud services enable ...` command printed in the message |
| `quota project ... not reachable` | Check you can access it, and that Resource Manager API is enabled on it |
| `billing account ... not visible` | You need Billing User (or Viewer) on the billing account |
| Project create fails with `already exists` | Project IDs are global and never reusable. Set a different `CT_PROJECT_ID` in `initialize.env` and re-run (the folder is kept) |
| Bucket create fails right after project creation | Billing can take a minute to propagate. Re-run the operation |
| `... must be DONE before ...` | Run the earlier operation first, or use `--force` deliberately |
| `A tmux session 'lsb-day0' already exists` | A run may still be going: `tmux attach -t lsb-day0`. If it is finished or stale: `tmux kill-session -t lsb-day0` |
