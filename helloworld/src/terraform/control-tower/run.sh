#!/usr/bin/env bash
# Learning Sandbox Day-0 Control Tower bootstrap runner.
#
#   ./run.sh --operation=<OperationName> [--validate-only] [--describe] [--yes] [--force] [--no-tmux]
#
# Operations:
#   Status                      progress of all bootstrap operations
#   Restore                     pull initialize.env, controltower.status and logs back from the state bucket
#   ControlTowerProjectCreate   (order 1) Control Tower folder, project, billing link, state bucket
#
# Flags (bootstrap operations):
#   --validate-only   run the operation's validation and stop (no changes)
#   --describe        print the operation's long description and stop
#   --yes             skip the confirmation prompt
#   --force           run even if the previous operation is not DONE
#   --no-tmux         do not relaunch inside the tmux session (default: interactive runs use tmux session lsb-day0)
#
# See helloworld/specs/day0-bootstrap-spec.md

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

STATUS_FILE="$ROOT/controltower.status"
LOG_DIR="$ROOT/logs"
RUNNER_PREFIX="control-tower/_runner"
MIN_TERRAFORM="1.5.0"

# ---------------------------------------------------------------------------
# Operation registry (order = position in BOOTSTRAP_OPS)
# ---------------------------------------------------------------------------
BOOTSTRAP_OPS=(ControlTowerProjectCreate)
declare -A OP_DIR=(
  [ControlTowerProjectCreate]="01-control-tower-project-create"
)
declare -A OP_TITLE=(
  [ControlTowerProjectCreate]="Control Tower folder + project + state bucket"
)
declare -A OP_KEYS=(
  [ControlTowerProjectCreate]="QUOTA_PROJECT ORG_ID BILLING_ACCOUNT_ID CT_FOLDER_NAME CT_FOLDER_PARENT CT_PROJECT_ID REGION TF_STATE_BUCKET"
)
# APIs that must be enabled on QUOTA_PROJECT for the operation's calls
declare -A OP_QUOTA_APIS=(
  [ControlTowerProjectCreate]="cloudresourcemanager.googleapis.com serviceusage.googleapis.com cloudbilling.googleapis.com storage.googleapis.com"
)

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
if [[ -t 1 && -z "${NO_COLOR-}" ]]; then
  C_RESET=$'\e[0m'; C_BOLD=$'\e[1m'; C_DIM=$'\e[2m'
  C_RED=$'\e[31m'; C_GREEN=$'\e[32m'; C_YELLOW=$'\e[33m'; C_BLUE=$'\e[34m'; C_MAGENTA=$'\e[35m'; C_CYAN=$'\e[36m'; C_GRAY=$'\e[90m'
else
  C_RESET=""; C_BOLD=""; C_DIM=""; C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_MAGENTA=""; C_CYAN=""; C_GRAY=""
fi

info()  { printf '%s\n' "  ${C_BLUE}›${C_RESET} $*"; }
ok()    { printf '%s\n' "  ${C_GREEN}✔${C_RESET} $*"; }
warn()  { printf '%s\n' "  ${C_YELLOW}!${C_RESET} $*"; }
err()   { printf '%s\n' "  ${C_RED}✖${C_RESET} $*" >&2; }
die()   { err "$*"; exit 2; }
title() { printf '\n%s\n\n' " ${C_BOLD}$*${C_RESET}"; }

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
OP=""; YES=0; FORCE=0; DESCRIBE=0; VALIDATE_ONLY=0; NO_TMUX=0
for arg in "$@"; do
  case "$arg" in
    --operation=*) OP="${arg#*=}" ;;
    --yes)         YES=1 ;;
    --force)       FORCE=1 ;;
    --describe)    DESCRIBE=1 ;;
    --validate-only) VALIDATE_ONLY=1 ;;
    --no-tmux)     NO_TMUX=1 ;;
    -h|--help)     usage 0 ;;
    *)             err "Unknown argument: $arg"; usage 2 ;;
  esac
done
[[ -n "$OP" ]] || { err "Missing --operation=<OperationName>"; usage 2; }

# ---------------------------------------------------------------------------
# tmux: bootstrap operations relaunch themselves inside a tmux session so a
# closed browser tab or dropped connection does not kill a running apply.
# Skipped for Status/Restore, --describe, --validate-only, --no-tmux,
# non-interactive runs, when already inside tmux, or when tmux is missing.
# ---------------------------------------------------------------------------
TMUX_SESSION="${LSB_TMUX_SESSION:-lsb-day0}"
maybe_relaunch_in_tmux() {
  case "$OP" in Status|Restore) return 0 ;; esac
  (( DESCRIBE || VALIDATE_ONLY || NO_TMUX )) && return 0
  [[ -n "${TMUX-}" ]] && return 0
  [[ -t 0 && -t 1 ]] || return 0
  command -v tmux >/dev/null 2>&1 || { warn "tmux not found: running without it (a disconnect can interrupt the run)"; return 0; }

  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    err "A tmux session '$TMUX_SESSION' already exists (a run may be in progress)."
    err "Reattach:  tmux attach -t $TMUX_SESSION     or close it:  tmux kill-session -t $TMUX_SESSION"
    exit 2
  fi

  local cmd q
  cmd="$(printf '%q ' "$ROOT/run.sh" "$@")"
  q="echo; read -r -p '  Run finished. Press Enter to close this tmux session. ' _"
  info "Starting in tmux session ${C_BOLD}${TMUX_SESSION}${C_RESET}  (detach: Ctrl-b then d   reattach: tmux attach -t ${TMUX_SESSION})"
  sleep 1
  exec tmux new-session -s "$TMUX_SESSION" -c "$ROOT" "$cmd; $q"
}
maybe_relaunch_in_tmux "$@"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_config() {
  # shellcheck disable=SC1091
  LSB_QUIET=1 source "$ROOT/initialize.sh" || die "Could not load initialize.env (see message above)."
}

# Set KEY="value" in a KEY=value file: replace in place, or append.
kv_set() {
  local file="$1" key="$2" val="$3" line tmp
  val="${val//\\/\\\\}"; val="${val//\"/\\\"}"
  line="${key}=\"${val}\""
  touch "$file"
  tmp="$(mktemp)"
  if grep -qE "^${key}=" "$file"; then
    KV_LINE="$line" awk -v k="$key" 'index($0, k"=") == 1 { print ENVIRON["KV_LINE"]; next } { print }' "$file" > "$tmp"
  else
    cat "$file" > "$tmp"
    printf '%s\n' "$line" >> "$tmp"
  fi
  cat "$tmp" > "$file"
  rm -f "$tmp"
}

# Write an operation output back to initialize.env (generated section).
env_write_back() {
  local key="$1" val="$2"
  if ! grep -qE "^${key}=" "$LSB_ENV_FILE" && ! grep -q '^# ---- generated by run.sh' "$LSB_ENV_FILE"; then
    printf '\n# ---- generated by run.sh (do not edit) ----\n' >> "$LSB_ENV_FILE"
  fi
  kv_set "$LSB_ENV_FILE" "$key" "$val"
  ok "initialize.env  ${key}=${val}"
}

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
status_get() { # op field
  [[ -f "$STATUS_FILE" ]] || return 0
  # shellcheck disable=SC2016
  bash -c '. "$1"; n="$2"; printf "%s" "${!n-}"' _ "$STATUS_FILE" "${1}_${2}"
}
status_set() { kv_set "$STATUS_FILE" "${1}_${2}" "$3"; }
now_utc()    { date -u +%Y-%m-%dT%H:%MZ; }
git_commit() { git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown; }
gcloud_account() { gcloud config get-value account 2>/dev/null || true; }

op_index() {
  local i
  for i in "${!BOOTSTRAP_OPS[@]}"; do [[ "${BOOTSTRAP_OPS[$i]}" == "$1" ]] && { echo "$i"; return 0; }; done
  return 1
}

next_op() {
  local op
  for op in "${BOOTSTRAP_OPS[@]}"; do
    [[ "$(status_get "$op" STATUS)" == "DONE" ]] || { echo "$op"; return 0; }
  done
  echo ""
}

# ---------------------------------------------------------------------------
# Bucket backup / restore of runner files
# ---------------------------------------------------------------------------
bucket_exists() { [[ -n "${TF_STATE_BUCKET-}" ]] && gcloud storage buckets describe "gs://${TF_STATE_BUCKET}" --format="value(name)" >/dev/null 2>&1; }

backup_runner_files() {
  bucket_exists || return 0
  local remote="gs://${TF_STATE_BUCKET}/${RUNNER_PREFIX}"
  gcloud storage cp --quiet "$LSB_ENV_FILE" "$remote/initialize.env" >/dev/null 2>&1 || warn "Backup of initialize.env to bucket failed"
  if [[ -f "$STATUS_FILE" ]]; then
    gcloud storage cp --quiet "$STATUS_FILE" "$remote/controltower.status" >/dev/null 2>&1 || warn "Backup of controltower.status to bucket failed"
  fi
  if [[ -d "$LOG_DIR" ]]; then
    gcloud storage rsync --recursive --quiet "$LOG_DIR" "$remote/logs" >/dev/null 2>&1 || warn "Backup of logs to bucket failed"
  fi
  return 0
}

# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------
version_ge() { [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" == "$2" ]]; }

# Terraform version as x.y.z: JSON output first, then the plain "Terraform vX.Y.Z" line.
terraform_version() {
  local v
  v="$(terraform version -json 2>/dev/null | jq -r '.terraform_version // empty' 2>/dev/null || true)"
  if [[ -z "$v" ]]; then
    v="$(terraform version 2>/dev/null | sed -nE 's/^Terraform v([0-9]+\.[0-9]+\.[0-9]+).*/\1/p' | head -n1 || true)"
  fi
  printf '%s' "$v"
}

# Shared checks run for every bootstrap operation.
validate_common() {
  local tool tfv
  for tool in terraform gcloud jq envsubst git; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      if [[ "$tool" == "terraform" ]]; then
        problems+=("tool not found: terraform (install it with: ./install-terraform.sh   then: export PATH=\"\$HOME/.local/bin:\$PATH\")")
      else
        problems+=("tool not found: $tool")
      fi
    fi
  done
  if command -v terraform >/dev/null 2>&1; then
    tfv="$(terraform_version)"
    if [[ -z "$tfv" ]]; then
      problems+=("could not determine terraform version from $(command -v terraform) (output: '$(terraform version 2>&1 | head -n1)'). This looks like a broken or placeholder terraform: run ./install-terraform.sh (installs to ~/.local/bin, which run.sh then prefers)")
    elif ! version_ge "$tfv" "$MIN_TERRAFORM"; then
      problems+=("terraform $tfv is older than $MIN_TERRAFORM (upgrade with: ./install-terraform.sh)")
    fi
  fi

  account="$(gcloud_account)"
  [[ -n "$account" ]] || problems+=("no active gcloud account (run: gcloud auth login)")

  if [[ -n "${QUOTA_PROJECT-}" ]]; then
    gcloud projects describe "$QUOTA_PROJECT" --format="value(projectId)" >/dev/null 2>&1 \
      || problems+=("quota project $QUOTA_PROJECT not reachable by $account (check access, and that cloudresourcemanager.googleapis.com is enabled on it: gcloud services enable cloudresourcemanager.googleapis.com --project=$QUOTA_PROJECT)")
  fi
}

# Checks declared in the operation registry: required keys and APIs on the quota project.
validate_registry() { # op
  local op="$1" key api enabled missing_apis=()
  for key in ${OP_KEYS[$op]-}; do
    [[ -n "${!key-}" ]] || problems+=("initialize.env: $key is empty")
  done
  if [[ -n "${OP_QUOTA_APIS[$op]-}" && -n "${QUOTA_PROJECT-}" ]]; then
    enabled="$(gcloud services list --enabled --project="$QUOTA_PROJECT" --format="value(config.name)" 2>/dev/null || true)"
    for api in ${OP_QUOTA_APIS[$op]}; do
      grep -qx "$api" <<<"$enabled" || missing_apis+=("$api")
    done
    if (( ${#missing_apis[@]} )); then
      problems+=("quota project $QUOTA_PROJECT is missing APIs: ${missing_apis[*]}  (fix: gcloud services enable ${missing_apis[*]} --project=$QUOTA_PROJECT)")
    fi
  fi
}

# Full validation for one operation: shared checks + registry checks + validate_<Operation> hook.
# Hooks add to the caller's problems / warnings arrays.
validate() { # op
  local op="$1" account="" problems=() warnings=() p
  title "Validate ${C_MAGENTA}${op}${C_RESET}"

  validate_common
  validate_registry "$op"
  if declare -F "validate_${op}" >/dev/null; then "validate_${op}"; fi

  for p in "${warnings[@]}"; do warn "$p"; done
  if (( ${#problems[@]} )); then
    err "Validate failed (${#problems[@]} problem(s))"
    for p in "${problems[@]}"; do printf '%s\n' "      • $p" >&2; done
    printf '\n%s\n' "  Nothing was changed." >&2
    return 1
  fi
  ok "account ${account}, quota project ${QUOTA_PROJECT}, all checks passed"
}

# ---------------------------------------------------------------------------
# Describe
# ---------------------------------------------------------------------------
folder_mode() {
  if [[ "${CT_FOLDER_MANAGED-}" == "true" ]]; then
    echo "keep managing folder ${CT_FOLDER_ID} (created by this operation earlier)"
  elif [[ -n "${CT_FOLDER_ID-}" ]]; then
    echo "use existing folder ${CT_FOLDER_ID} (no folder is created)"
  else
    echo "create folder \"${CT_FOLDER_NAME-}\" under ${CT_FOLDER_PARENT-}"
  fi
}

describe() { # op
  local op="$1" file="$ROOT/${OP_DIR[$op]}/operation.md" idx
  idx="$(op_index "$op")"
  export LSB_ACCOUNT LSB_FOLDER_MODE
  LSB_ACCOUNT="$(gcloud_account)"
  LSB_FOLDER_MODE="$(folder_mode)"
  printf '\n %s%s%s%*s%s\n' "$C_BOLD$C_MAGENTA" "$op" "$C_RESET" 30 "" "${C_GRAY}order $((idx + 1)) of ${#BOOTSTRAP_OPS[@]}${C_RESET}"
  envsubst < "$file" | while IFS= read -r line; do
    case "$line" in
      "# "*)  ;;
      "## "*) printf '\n %s\n' "${C_BOLD}${C_CYAN}${line#\#\# }${C_RESET}" ;;
      *)      printf '   %s\n' "$line" ;;
    esac
  done
  echo
}

# ---------------------------------------------------------------------------
# Terraform helpers
# ---------------------------------------------------------------------------
write_backend() { # dir prefix
  cat > "$1/backend.tf" <<EOF
# Generated by run.sh after the state bucket exists. Do not commit.
terraform {
  backend "gcs" {
    prefix = "$2"
  }
}
EOF
}

tf_init() { # dir
  if [[ -f "$1/backend.tf" ]]; then
    terraform -chdir="$1" init -input=false
  else
    TF_CLI_ARGS_init="" terraform -chdir="$1" init -input=false
  fi
}

confirm() {
  (( YES )) && return 0
  local ans=""
  # Prefer the terminal; fall back to stdin when there is no controlling terminal (e.g. piped/automated runs).
  if { exec 3</dev/tty; } 2>/dev/null; then
    read -r -p "  Proceed? [y/N] " ans <&3 || true
    exec 3<&-
  else
    printf '  Proceed? [y/N] '
    read -r ans || true
  fi
  [[ "$ans" =~ ^[Yy]$ ]]
}

wait_for() { # description timeout_seconds command...
  local desc="$1" timeout="$2"; shift 2
  local waited=0
  until "$@" >/dev/null 2>&1; do
    (( waited >= timeout )) && { err "Timed out after ${timeout}s waiting for: $desc"; return 1; }
    printf '%s\n' "  ${C_YELLOW}…${C_RESET} waiting for $desc (${waited}s)"
    sleep 10; waited=$((waited + 10))
  done
  ok "$desc"
}

# ---------------------------------------------------------------------------
# Operation hooks
# ---------------------------------------------------------------------------
LOCAL_STATE=0

# ControlTowerProjectCreate: local state until the bucket exists, then migrate.
pre_init_ControlTowerProjectCreate() { # dir prefix
  local dir="$1" prefix="$2"
  if [[ -f "$dir/backend.tf" ]]; then
    info "using remote state gs://${TF_STATE_BUCKET}/${prefix}"
  elif gcloud storage ls "gs://${TF_STATE_BUCKET}/${prefix}/default.tfstate" >/dev/null 2>&1; then
    write_backend "$dir" "$prefix"
    info "found existing remote state, using gs://${TF_STATE_BUCKET}/${prefix}"
  else
    LOCAL_STATE=1
    info "no state bucket yet: starting with local state, will move it into the bucket after apply"
  fi
}

# Adds a problem unless the folder exists, is accessible and is ACTIVE.
check_folder_active() { # folder_id label
  local state
  state="$(gcloud resource-manager folders describe "$1" --format="value(lifecycleState)" 2>/dev/null || true)"
  if [[ -z "$state" ]]; then
    problems+=("$2 not found or not accessible by $account")
  elif [[ "$state" != "ACTIVE" ]]; then
    problems+=("$2 is $state (not ACTIVE): choose an active folder")
  fi
}

validate_ControlTowerProjectCreate() {
  # Billing account visible to the admin
  if [[ -n "${BILLING_ACCOUNT_ID-}" ]]; then
    gcloud billing accounts describe "$BILLING_ACCOUNT_ID" --format="value(name)" >/dev/null 2>&1 \
      || problems+=("billing account $BILLING_ACCOUNT_ID not visible to $account (needs Billing User or Viewer)")
  fi
  # Folder parent exists, is accessible and ACTIVE (a folder being deleted still "exists")
  case "${CT_FOLDER_PARENT-}" in
    folders/*)  check_folder_active "${CT_FOLDER_PARENT#folders/}" "CT_FOLDER_PARENT ${CT_FOLDER_PARENT}" ;;
    organizations/*)
      gcloud organizations describe "${CT_FOLDER_PARENT#organizations/}" --format="value(name)" >/dev/null 2>&1 \
        || problems+=("CT_FOLDER_PARENT ${CT_FOLDER_PARENT} not found or not accessible by $account") ;;
  esac
  # Existing folder (when CT_FOLDER_ID is set) is accessible and ACTIVE
  if [[ -n "${CT_FOLDER_ID-}" ]]; then
    check_folder_active "$CT_FOLDER_ID" "CT_FOLDER_ID ${CT_FOLDER_ID}"
  fi
  # Project ID and bucket name are global: warn if they already exist before this operation is DONE
  if [[ "$(status_get ControlTowerProjectCreate STATUS)" != "DONE" && -n "${CT_PROJECT_ID-}" ]]; then
    if gcloud projects describe "$CT_PROJECT_ID" --format="value(projectId)" >/dev/null 2>&1; then
      warnings+=("project $CT_PROJECT_ID already exists: apply will fail unless it came from an interrupted earlier run of this operation")
    fi
  fi
}

post_apply_ControlTowerProjectCreate() { # dir prefix
  local dir="$1" prefix="$2" out
  if (( LOCAL_STATE )); then
    CURRENT_STEP="moving Terraform state into gs://${TF_STATE_BUCKET}/${prefix}"
    info "$CURRENT_STEP"
    write_backend "$dir" "$prefix"
    terraform -chdir="$dir" init -input=false -migrate-state -force-copy
    mkdir -p "$LOG_DIR/local-state-backup"
    for f in "$dir"/terraform.tfstate "$dir"/terraform.tfstate.backup; do
      if [[ -f "$f" ]]; then
        mv "$f" "$LOG_DIR/local-state-backup/$(basename "$f").$(date -u +%Y%m%dT%H%M%SZ)"
      fi
    done
    ok "state stored in gs://${TF_STATE_BUCKET}/${prefix}"
  fi

  CURRENT_STEP="readiness check"
  wait_for "project ${CT_PROJECT_ID} ACTIVE" 180 \
    bash -c '[[ "$(gcloud projects describe "$1" --format="value(lifecycleState)")" == "ACTIVE" ]]' _ "$CT_PROJECT_ID"
  wait_for "billing enabled on ${CT_PROJECT_ID}" 180 \
    bash -c '[[ "$(gcloud billing projects describe "$1" --format="value(billingEnabled)")" == "True" ]]' _ "$CT_PROJECT_ID"

  CURRENT_STEP="writing outputs back to initialize.env"
  out="$(terraform -chdir="$dir" output -json)"
  env_write_back CT_FOLDER_ID      "$(jq -r '.folder_id.value' <<<"$out")"
  env_write_back CT_FOLDER_MANAGED "$(jq -r '.folder_managed.value' <<<"$out")"
  env_write_back CT_PROJECT_NUMBER "$(jq -r '.project_number.value' <<<"$out")"
}

# ---------------------------------------------------------------------------
# Run a bootstrap operation
# ---------------------------------------------------------------------------
CURRENT_OP=""; CURRENT_STEP=""

on_fail() {
  local rc=$?
  trap - ERR INT TERM
  if [[ -n "$CURRENT_OP" ]]; then
    status_set "$CURRENT_OP" STATUS FAILED
    status_set "$CURRENT_OP" AT "$(now_utc)"
    status_set "$CURRENT_OP" ERROR "failed at: ${CURRENT_STEP:-unknown step} (exit $rc), see ${LOG_FILE-logs}"
    backup_runner_files || true
    err "${CURRENT_OP} FAILED at: ${CURRENT_STEP:-unknown step}"
    err "Log: ${LOG_FILE-}"
  fi
  exit 1
}

run_operation() { # op
  local op="$1" idx dir prefix prev rc prev_status
  idx="$(op_index "$op")"
  dir="$ROOT/${OP_DIR[$op]}"
  prefix="control-tower/${OP_DIR[$op]}"

  if (( VALIDATE_ONLY )); then
    validate "$op" || exit 2
    return 0
  fi

  describe "$op"
  (( DESCRIBE )) && return 0

  validate "$op" || exit 2

  if (( idx > 0 )); then
    prev="${BOOTSTRAP_OPS[$((idx - 1))]}"
    if [[ "$(status_get "$prev" STATUS)" != "DONE" ]]; then
      (( FORCE )) || die "$prev must be DONE before $op (use --force to override)."
      warn "--force: running $op although $prev is not DONE"
    fi
  fi

  mkdir -p "$LOG_DIR"
  LOG_FILE="$LOG_DIR/${op}-$(date -u +%Y%m%dT%H%M%SZ).log"
  exec > >(tee -a "$LOG_FILE") 2>&1

  CURRENT_OP="$op"
  prev_status="$(status_get "$op" STATUS)"
  trap on_fail ERR INT TERM
  status_set "$op" STATUS RUNNING
  status_set "$op" AT "$(now_utc)"
  status_set "$op" BY "$(gcloud_account)"
  status_set "$op" COMMIT "$(git_commit)"
  status_set "$op" ERROR ""

  title "Running ${C_MAGENTA}${op}${C_RESET}  ${C_GRAY}(log: ${LOG_FILE#"$ROOT"/})${C_RESET}"

  CURRENT_STEP="terraform init"
  if declare -F "pre_init_${op}" >/dev/null; then "pre_init_${op}" "$dir" "$prefix"; fi
  tf_init "$dir"

  CURRENT_STEP="terraform plan"
  # Exit code 2 means "changes present". Capture it via || so neither errexit nor the ERR trap fires.
  rc=0
  terraform -chdir="$dir" plan -input=false -detailed-exitcode -out=tfplan || rc=$?
  case "$rc" in
    0) ok "No changes needed." ;;
    2) printf '\n'
       if ! confirm; then
         warn "Cancelled. Nothing was changed."
         status_set "$op" STATUS "${prev_status:-NOT_STARTED}"
         CURRENT_OP=""; trap - ERR INT TERM; rm -f "$dir/tfplan"; exit 0
       fi
       CURRENT_STEP="terraform apply"
       terraform -chdir="$dir" apply -input=false tfplan ;;
    *) false ;;
  esac
  rm -f "$dir/tfplan"

  if declare -F "post_apply_${op}" >/dev/null; then "post_apply_${op}" "$dir" "$prefix"; fi

  status_set "$op" STATUS DONE
  status_set "$op" AT "$(now_utc)"
  # reload so the backup includes written-back values
  load_config
  backup_runner_files
  CURRENT_OP=""
  trap - ERR INT TERM
  title "${C_GREEN}✔ ${op} DONE${C_RESET}"
}

# ---------------------------------------------------------------------------
# Utility operations
# ---------------------------------------------------------------------------
op_status() {
  title "Control Tower Day-0    ${C_GRAY}project ${CT_PROJECT_ID-?}${C_RESET}"
  local i op st at by commit errm sym color
  for i in "${!BOOTSTRAP_OPS[@]}"; do
    op="${BOOTSTRAP_OPS[$i]}"
    st="$(status_get "$op" STATUS)"; st="${st:-NOT_STARTED}"
    at="$(status_get "$op" AT)"; by="$(status_get "$op" BY)"; commit="$(status_get "$op" COMMIT)"; errm="$(status_get "$op" ERROR)"
    case "$st" in
      DONE)    sym="✔"; color="$C_GREEN" ;;
      FAILED)  sym="✖"; color="$C_RED" ;;
      RUNNING) sym="◐"; color="$C_YELLOW"; st="INTERRUPTED" ;;
      *)       sym="○"; color="$C_GRAY" ;;
    esac
    printf '  %s%s %d  %-28s %-12s%s %-18s %-30s %s\n' "$color" "$sym" "$((i + 1))" "$op" "$st" "$C_RESET" "${at:-}" "${by%%@*}${by:+@}" "${commit:-}"
    if [[ "$st" == "FAILED" && -n "$errm" ]]; then printf '        %s\n' "${C_RED}${errm}${C_RESET}"; fi
  done
  echo
}

op_restore() {
  [[ -n "${TF_STATE_BUCKET-}" ]] || die "TF_STATE_BUCKET is empty in initialize.env"
  local remote="gs://${TF_STATE_BUCKET}/${RUNNER_PREFIX}" f tmp
  title "Restore from ${remote}"
  bucket_exists || die "Bucket gs://${TF_STATE_BUCKET} not found or not accessible."
  for f in initialize.env controltower.status; do
    tmp="$(mktemp)"
    if gcloud storage cp --quiet "$remote/$f" "$tmp" >/dev/null 2>&1; then
      if [[ -f "$ROOT/$f" ]] && ! cmp -s "$ROOT/$f" "$tmp"; then
        diff -u "$ROOT/$f" "$tmp" || true
        if ! confirm; then warn "kept local $f"; rm -f "$tmp"; continue; fi
        cp "$ROOT/$f" "$ROOT/$f.bak"
        info "saved previous local copy as $f.bak"
      fi
      mv "$tmp" "$ROOT/$f"
      ok "restored $f"
    else
      rm -f "$tmp"
      warn "$f not found in bucket"
    fi
  done
  mkdir -p "$LOG_DIR"
  gcloud storage rsync --recursive --quiet "$remote/logs" "$LOG_DIR" >/dev/null 2>&1 && ok "restored logs" || warn "no logs in bucket"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
load_config

case "$OP" in
  Status)  op_status ;;
  Restore) op_restore ;;
  *)
    op_index "$OP" >/dev/null || die "Unknown operation: $OP (known: Status Restore ${BOOTSTRAP_OPS[*]})"
    run_operation "$OP" ;;
esac
