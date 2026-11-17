#!/usr/bin/env bash
# ManualGround Layer 1 Terraform bootstrap runner.
#
#   ./terraform/run.sh --operation=<OperationName> [--validate-only] [--describe] [--auto-approve] [--force] [--no-tmux]
#   ./terraform/run.sh --operation=RunAll [--from=<OperationName>] [--to=<OperationName>] [same flags]
#
# Operations:
#   RunAll                    run Layer 1 operations in order: --from (default: first) to --to (default: last)
#   Status                    progress of all Layer 1 Terraform operations
#   Restore                   pull initialize.env, manualground.status and logs back from TF_STATE_BUCKET
#   FolderGuardrailsCreate    (order 1) Playground guardrail folder, Org Policies, and IAM Deny v2 policy
#   ShardProjectCreate        (order 2) 80-student shard project, baseline APIs, P4SAs, and all 9 custom_ntu_* roles
#   CloudRunAutoOwnerCreate   (order 3) ntu-run-auto-owner Cloud Run v2 receiver + v1/v2 Eventarc CreateService triggers
#   SharedCloudSqlCreate      (order 4) Shared Cloud SQL for PostgreSQL 16 instance (dev|prod preset, IAM DB auth, TLS)
#
# Flags (bootstrap operations):
#   --validate-only   run preflight validation and stop (no changes)
#   --describe        print the operation's long description (incl. LONG-RUNNING watch commands) and stop
#   --auto-approve    approve the Terraform plan without interactive confirmation
#   --force           run even if the previous operation is not marked DONE
#   --no-tmux         do not relaunch inside a tmux session (default: interactive runs use tmux session mg-layer1)

set -Eeuo pipefail

TF_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MG_ROOT="$(cd "${TF_ROOT}/.." && pwd)"
cd "$TF_ROOT"

STATUS_FILE="${MG_ROOT}/manualground.status"
LOG_DIR="${MG_ROOT}/logs"
STATE_ROOT="${MG_ROOT}/state"
RUNNER_PREFIX="manualground/_runner"
MIN_TERRAFORM="1.5.0"

# ---------------------------------------------------------------------------
# Operation registry (order = position in BOOTSTRAP_OPS)
# ---------------------------------------------------------------------------
BOOTSTRAP_OPS=(FolderGuardrailsCreate ShardProjectCreate CloudRunAutoOwnerCreate SharedCloudSqlCreate)
declare -A OP_DIR=(
  [FolderGuardrailsCreate]="01-folder-guardrails"
  [ShardProjectCreate]="02-shard-project-baseline"
  [CloudRunAutoOwnerCreate]="03-cloud-run-auto-owner"
  [SharedCloudSqlCreate]="04-shared-cloud-sql"
)
declare -A OP_TITLE=(
  [FolderGuardrailsCreate]="Playground guardrail folder + Org Policies + IAM Deny v2"
  [ShardProjectCreate]="Shard project + baseline APIs + P4SAs + 9 custom_ntu_* IAM roles"
  [CloudRunAutoOwnerCreate]="Cloud Run v2 auto-owner receiver + Eventarc v1/v2 CreateService triggers (LONG-RUNNING ~5-15m)"
  [SharedCloudSqlCreate]="Shared Cloud SQL PostgreSQL 16 instance with IAM auth & ENCRYPTED_ONLY (LONG-RUNNING ~10-25m)"
)
declare -A OP_KEYS=(
  [FolderGuardrailsCreate]="QUOTA_PROJECT ORG_ID MG_PARENT_FOLDER REGION"
  [ShardProjectCreate]="QUOTA_PROJECT ORG_ID BILLING_ACCOUNT_ID MG_FOLDER_ID MG_PROJECT_ID REGION"
  [CloudRunAutoOwnerCreate]="QUOTA_PROJECT MG_PROJECT_ID MG_PROJECT_NUMBER REGION MAX_SERVICES_PER_STUDENT"
  [SharedCloudSqlCreate]="QUOTA_PROJECT MG_PROJECT_ID REGION MG_PRESET ENABLE_CLOUD_SQL"
)
declare -A OP_QUOTA_APIS=(
  [FolderGuardrailsCreate]="cloudresourcemanager.googleapis.com orgpolicy.googleapis.com iam.googleapis.com"
  [ShardProjectCreate]="cloudresourcemanager.googleapis.com serviceusage.googleapis.com cloudbilling.googleapis.com iam.googleapis.com storage.googleapis.com"
  [CloudRunAutoOwnerCreate]="run.googleapis.com eventarc.googleapis.com pubsub.googleapis.com iam.googleapis.com"
  [SharedCloudSqlCreate]="sqladmin.googleapis.com serviceusage.googleapis.com"
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
  sed -n '2,23p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
OP=""; AUTO_APPROVE=0; FORCE=0; DESCRIBE=0; VALIDATE_ONLY=0; NO_TMUX=0; FROM_OP=""; TO_OP=""
for arg in "$@"; do
  case "$arg" in
    --operation=*)   OP="${arg#*=}" ;;
    --auto-approve)  AUTO_APPROVE=1 ;;
    --force)         FORCE=1 ;;
    --describe)      DESCRIBE=1 ;;
    --validate-only) VALIDATE_ONLY=1 ;;
    --no-tmux)       NO_TMUX=1 ;;
    --from=*)        FROM_OP="${arg#*=}" ;;
    --to=*)          TO_OP="${arg#*=}" ;;
    -h|--help)       usage 0 ;;
    *)               err "Unknown argument: $arg"; usage 2 ;;
  esac
done
[[ -n "$OP" ]] || { err "Missing --operation=<OperationName>"; usage 2; }

# ---------------------------------------------------------------------------
# tmux wrapper for long-running interactive operations
# ---------------------------------------------------------------------------
TMUX_SESSION="${MG_TMUX_SESSION:-mg-layer1}"
maybe_relaunch_in_tmux() {
  case "$OP" in Status|Restore) return 0 ;; esac
  (( DESCRIBE || VALIDATE_ONLY || NO_TMUX )) && return 0
  [[ -n "${TMUX-}" ]] && return 0
  [[ -t 0 && -t 1 ]] || return 0
  command -v tmux >/dev/null 2>&1 || { warn "tmux not found: running directly in current shell"; return 0; }

  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    err "A tmux session '$TMUX_SESSION' already exists (a run may be in progress)."
    err "Reattach:  tmux attach -t $TMUX_SESSION     or close it:  tmux kill-session -t $TMUX_SESSION"
    exit 2
  fi

  local cmd q
  cmd="$(printf '%q ' "$TF_ROOT/run.sh" "$@")"
  q="echo; read -r -p '  Run finished. Press Enter to close this tmux session. ' _"
  info "Starting in tmux session ${C_BOLD}${TMUX_SESSION}${C_RESET}  (detach: Ctrl-b then d   reattach: tmux attach -t ${TMUX_SESSION})"
  sleep 1
  exec tmux new-session -s "$TMUX_SESSION" -c "$MG_ROOT" "$cmd; $q"
}
maybe_relaunch_in_tmux "$@"

# ---------------------------------------------------------------------------
# Config & Key-Value Helpers
# ---------------------------------------------------------------------------
load_config() {
  # shellcheck disable=SC1091
  MG_QUIET=1 source "${MG_ROOT}/initialize.sh" || die "Could not load initialize.env (see message above)."
}

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

env_write_back() {
  local key="$1" val="$2"
  if ! grep -qE "^${key}=" "$MG_ENV_FILE" && ! grep -q '^# ---- generated by terraform/run.sh' "$MG_ENV_FILE"; then
    printf '\n# ---- generated by terraform/run.sh (do not edit) ----\n' >> "$MG_ENV_FILE"
  fi
  kv_set "$MG_ENV_FILE" "$key" "$val"
  ok "initialize.env  ${key}=${val}"
}

# ---------------------------------------------------------------------------
# Status Helpers
# ---------------------------------------------------------------------------
status_get() {
  [[ -f "$STATUS_FILE" ]] || return 0
  # shellcheck disable=SC2016
  bash -c '. "$1"; n="$2"; printf "%s" "${!n-}"' _ "$STATUS_FILE" "${1}_${2}"
}
status_set()     { kv_set "$STATUS_FILE" "${1}_${2}" "$3"; }
now_utc()        { date -u +%Y-%m-%dT%H:%MZ; }
git_commit()     { git -C "$MG_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown; }
gcloud_account() { gcloud config get-value account 2>/dev/null || true; }

op_index() {
  local i
  for i in "${!BOOTSTRAP_OPS[@]}"; do [[ "${BOOTSTRAP_OPS[$i]}" == "$1" ]] && { echo "$i"; return 0; }; done
  return 1
}

# ---------------------------------------------------------------------------
# Optional GCS State Bucket Backup / Restore
# ---------------------------------------------------------------------------
bucket_exists() {
  [[ -n "${TF_STATE_BUCKET-}" ]] && gcloud storage buckets describe "gs://${TF_STATE_BUCKET}" --format="value(name)" >/dev/null 2>&1
}

backup_runner_files() {
  bucket_exists || return 0
  local remote="gs://${TF_STATE_BUCKET}/${RUNNER_PREFIX}"
  gcloud storage cp --quiet "$MG_ENV_FILE" "$remote/initialize.env" >/dev/null 2>&1 || warn "Backup of initialize.env to bucket failed"
  if [[ -f "$STATUS_FILE" ]]; then
    gcloud storage cp --quiet "$STATUS_FILE" "$remote/manualground.status" >/dev/null 2>&1 || warn "Backup of manualground.status to bucket failed"
  fi
  if [[ -d "$LOG_DIR" ]]; then
    gcloud storage rsync --recursive --quiet "$LOG_DIR" "$remote/logs" >/dev/null 2>&1 || warn "Backup of logs to bucket failed"
  fi
  return 0
}

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
version_ge() { [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" == "$2" ]]; }

terraform_version() {
  local v
  v="$(terraform version -json 2>/dev/null | jq -r '.terraform_version // empty' 2>/dev/null || true)"
  if [[ -z "$v" ]]; then
    v="$(terraform version 2>/dev/null | sed -nE 's/^Terraform v([0-9]+\.[0-9]+\.[0-9]+).*/\1/p' | head -n1 || true)"
  fi
  printf '%s' "$v"
}

validate_common() {
  local tool tfv
  for tool in terraform gcloud jq envsubst; do
    command -v "$tool" >/dev/null 2>&1 || problems+=("tool not found: $tool")
  done
  if command -v terraform >/dev/null 2>&1; then
    tfv="$(terraform_version)"
    if [[ -z "$tfv" ]]; then
      problems+=("could not determine terraform version from $(command -v terraform)")
    elif ! version_ge "$tfv" "$MIN_TERRAFORM"; then
      problems+=("terraform $tfv is older than $MIN_TERRAFORM")
    fi
  fi

  account="$(gcloud_account)"
  [[ -n "$account" ]] || problems+=("no active gcloud account (run: gcloud auth login)")

  if [[ -n "${QUOTA_PROJECT-}" ]]; then
    gcloud projects describe "$QUOTA_PROJECT" --format="value(projectId)" >/dev/null 2>&1 \
      || problems+=("quota project $QUOTA_PROJECT not reachable by $account")
  fi
}

validate_registry() {
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

validate_FolderGuardrailsCreate() {
  if [[ -z "${IT_ADMINS_GROUP-}" && -z "${PROVISIONER_SA_EMAIL-}" ]]; then
    warnings+=("neither IT_ADMINS_GROUP nor PROVISIONER_SA_EMAIL is set; set at least one so admin automation is exempted from Folder IAM Deny v2 rules")
  fi
}

validate_ShardProjectCreate() {
  if [[ -n "${BILLING_ACCOUNT_ID-}" ]]; then
    gcloud billing accounts describe "$BILLING_ACCOUNT_ID" --format="value(name)" >/dev/null 2>&1 \
      || problems+=("billing account $BILLING_ACCOUNT_ID not visible to $account")
  fi
}

validate_CloudRunAutoOwnerCreate() {
  [[ -z "${MG_PROJECT_ID-}" ]] && return 0
  local enabled
  enabled="$(gcloud services list --enabled --project="$MG_PROJECT_ID" --format="value(config.name)" 2>/dev/null || true)"
  for req_api in run.googleapis.com eventarc.googleapis.com pubsub.googleapis.com logging.googleapis.com; do
    grep -qx "$req_api" <<<"$enabled" || problems+=("$req_api is not enabled on $MG_PROJECT_ID (run ShardProjectCreate first)")
  done
}

validate_SharedCloudSqlCreate() {
  case "${MG_PRESET-dev}" in
    dev|prod) ;;
    *) problems+=("MG_PRESET must be 'dev' or 'prod' (got '${MG_PRESET-}')") ;;
  esac
  case "${ENABLE_CLOUD_SQL-true}" in
    true|false) ;;
    *) problems+=("ENABLE_CLOUD_SQL must be 'true' or 'false' (got '${ENABLE_CLOUD_SQL-}')") ;;
  esac
}

validate() {
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
describe() {
  local op="$1" file="${TF_ROOT}/${OP_DIR[$op]}/operation.md" idx
  idx="$(op_index "$op")"
  export MG_ACCOUNT
  MG_ACCOUNT="$(gcloud_account)"
  printf '\n %s%s%s%*s%s\n' "$C_BOLD$C_MAGENTA" "$op" "$C_RESET" 26 "" "${C_GRAY}order $((idx + 1)) of ${#BOOTSTRAP_OPS[@]}${C_RESET}"
  if [[ -f "$file" ]]; then
    envsubst < "$file" | while IFS= read -r line; do
      case "$line" in
        "# "*)  ;;
        "## "*) printf '\n %s\n' "${C_BOLD}${C_CYAN}${line#\#\# }${C_RESET}" ;;
        *)      printf '   %s\n' "$line" ;;
      esac
    done
  fi
  echo
}

# ---------------------------------------------------------------------------
# Terraform Execution & Post-Apply Hooks
# ---------------------------------------------------------------------------
write_backend() {
  cat > "$1/backend.tf" <<EOF
# Generated by terraform/run.sh when TF_STATE_BUCKET exists. Gitignored.
terraform {
  backend "gcs" {
    prefix = "$2"
  }
}
EOF
}

confirm() {
  (( AUTO_APPROVE )) && return 0
  local ans="" prompt="${1:-Proceed?}"
  if { exec 3</dev/tty; } 2>/dev/null; then
    read -r -p "  ${prompt} [y/N] " ans <&3 || true
    exec 3<&-
  else
    printf '  %s [y/N] ' "$prompt"
    read -r ans || true
  fi
  [[ "$ans" =~ ^[Yy]$ ]]
}

wait_for() {
  local desc="$1" timeout="$2"; shift 2
  local waited=0
  until "$@" >/dev/null 2>&1; do
    (( waited >= timeout )) && { err "Timed out after ${timeout}s waiting for: $desc"; return 1; }
    printf '%s\n' "  ${C_YELLOW}…${C_RESET} waiting for $desc (${waited}s)"
    sleep 10; waited=$((waited + 10))
  done
  ok "$desc"
}

post_apply_FolderGuardrailsCreate() {
  local dir="$1" out
  out="$(terraform -chdir="$dir" output -json)"
  env_write_back MG_FOLDER_ID      "$(jq -r '.folder_id.value' <<<"$out")"
  env_write_back MG_FOLDER_MANAGED "$(jq -r '.folder_managed.value' <<<"$out")"
}

post_apply_ShardProjectCreate() {
  local dir="$1" out proj_num
  out="$(terraform -chdir="$dir" output -json)"
  proj_num="$(jq -r '.project_number.value' <<<"$out")"
  env_write_back MG_PROJECT_NUMBER "$proj_num"

  wait_for "Eventarc Service Agent readiness on ${MG_PROJECT_ID}" 120 \
    bash -c 'gcloud projects get-iam-policy "$1" --format=json | jq -e --arg sa "serviceAccount:service-$2@gcp-sa-eventarc.iam.gserviceaccount.com" ".bindings[]? | select(.role==\"roles/eventarc.serviceAgent\") | .members | index(\$sa)" >/dev/null' _ "$MG_PROJECT_ID" "$proj_num"
}

post_apply_CloudRunAutoOwnerCreate() {
  local dir="$1" out sub
  out="$(terraform -chdir="$dir" output -json)"
  for sub in $(jq -r '.eventarc_subscriptions.value[]?' <<<"$out"); do
    [[ -n "$sub" ]] || continue
    wait_for "Pub/Sub ack_deadline_seconds=60 on ${sub}" 60 \
      bash -c '[[ "$(gcloud pubsub subscriptions describe "$1" --project="$2" --format="value(ackDeadlineSeconds)")" == "60" ]]' _ "$sub" "$MG_PROJECT_ID"
  done
}

post_apply_SharedCloudSqlCreate() {
  local dir="$1" out enabled inst
  out="$(terraform -chdir="$dir" output -json)"
  enabled="$(jq -r '.sql_instance_enabled.value' <<<"$out")"
  if [[ "$enabled" == "true" ]]; then
    inst="$(jq -r '.sql_instance_name.value' <<<"$out")"
    env_write_back MG_SQL_INSTANCE "$inst"
    wait_for "Cloud SQL instance ${inst} RUNNABLE" 120 \
      bash -c '[[ "$(gcloud sql instances describe "$1" --project="$2" --format="value(state)")" == "RUNNABLE" ]]' _ "$inst" "$MG_PROJECT_ID"
  else
    info "ENABLE_CLOUD_SQL=false: Shared Cloud SQL instance skipped cleanly."
  fi
}

# ---------------------------------------------------------------------------
# Run One Bootstrap Operation
# ---------------------------------------------------------------------------
CURRENT_OP=""; CURRENT_STEP=""; PREV_STATUS=""; SIGNAL=""

on_fail() {
  local rc=$? reason
  clear_fail_traps
  trap '' PIPE
  if [[ -n "$CURRENT_OP" ]]; then
    if [[ -n "$SIGNAL" ]]; then
      reason="interrupted (SIG${SIGNAL}) at: ${CURRENT_STEP:-unknown step}"
    else
      reason="failed at: ${CURRENT_STEP:-unknown step} (exit $rc)"
    fi
    status_set "$CURRENT_OP" STATUS FAILED
    status_set "$CURRENT_OP" AT "$(now_utc)"
    status_set "$CURRENT_OP" ERROR "${reason}, see ${LOG_FILE-logs}"
    backup_runner_files || true
    err "${CURRENT_OP} ${reason}" 2>/dev/null || true
  fi
  exit 1
}

set_fail_traps() {
  trap on_fail ERR
  trap 'SIGNAL=INT;  on_fail' INT
  trap 'SIGNAL=TERM; on_fail' TERM
  trap 'SIGNAL=HUP;  on_fail' HUP
}
clear_fail_traps() { trap - ERR INT TERM HUP; }

run_operation() {
  local op="$1" idx dir prefix prev rc state_args=() plan_file
  idx="$(op_index "$op")"
  dir="${TF_ROOT}/${OP_DIR[$op]}"
  prefix="manualground/${OP_DIR[$op]}"

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

  mkdir -p "$LOG_DIR" "${STATE_ROOT}/tf-data/${OP_DIR[$op]}" "${STATE_ROOT}/tf-state/${OP_DIR[$op]}"
  export TF_DATA_DIR="${STATE_ROOT}/tf-data/${OP_DIR[$op]}"
  plan_file="${STATE_ROOT}/tf-state/${OP_DIR[$op]}/tfplan"
  LOG_FILE="$LOG_DIR/${op}-$(date -u +%Y%m%dT%H%M%SZ).log"

  exec > >(trap '' HUP INT TERM PIPE; exec tee -a --output-error=warn "$LOG_FILE") 2>&1

  CURRENT_OP="$op"
  PREV_STATUS="$(status_get "$op" STATUS)"
  set_fail_traps
  status_set "$op" STATUS RUNNING
  status_set "$op" AT "$(now_utc)"
  status_set "$op" BY "$(gcloud_account)"
  status_set "$op" COMMIT "$(git_commit)"
  status_set "$op" ERROR ""

  title "Running ${C_MAGENTA}${op}${C_RESET}  ${C_GRAY}(log: ${LOG_FILE#"${MG_ROOT}"/})${C_RESET}"

  CURRENT_STEP="terraform init"
  if bucket_exists; then
    write_backend "$dir" "$prefix"
    terraform -chdir="$dir" init -input=false
  else
    rm -f "$dir/backend.tf"
    TF_CLI_ARGS_init="" terraform -chdir="$dir" init -input=false
    state_args=(-state="${STATE_ROOT}/tf-state/${OP_DIR[$op]}/terraform.tfstate")
  fi

  CURRENT_STEP="terraform plan"
  rc=0
  terraform -chdir="$dir" plan -input=false -detailed-exitcode "${state_args[@]}" -out="$plan_file" || rc=$?
  case "$rc" in
    0) ok "No changes needed." ;;
    2) printf '\n'
       if ! confirm; then
         warn "Cancelled. Nothing was changed."
         status_set "$op" STATUS "${PREV_STATUS:-NOT_STARTED}"
         CURRENT_OP=""; clear_fail_traps; rm -f "$plan_file"; exit 0
       fi
       CURRENT_STEP="terraform apply"
       terraform -chdir="$dir" apply -input=false "${state_args[@]}" "$plan_file" ;;
    *) false ;;
  esac
  rm -f "$plan_file"

  if declare -F "post_apply_${op}" >/dev/null; then
    if (( ${#state_args[@]} )); then
      # Temporarily export TF_CLI_ARGS_output so terraform output reads local state outside repo
      TF_CLI_ARGS_output="${state_args[*]}" "post_apply_${op}" "$dir" "$prefix"
    else
      "post_apply_${op}" "$dir" "$prefix"
    fi
  fi

  status_set "$op" STATUS DONE
  status_set "$op" AT "$(now_utc)"
  load_config
  backup_runner_files
  CURRENT_OP=""
  clear_fail_traps
  title "${C_GREEN}✔ ${op} DONE${C_RESET}"
}

# ---------------------------------------------------------------------------
# Utility Operations (Status, Restore, RunAll)
# ---------------------------------------------------------------------------
op_status() {
  title "ManualGround Layer 1    ${C_GRAY}project ${MG_PROJECT_ID-?} (preset: ${MG_PRESET-dev}, sql: ${ENABLE_CLOUD_SQL-true})${C_RESET}"
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
    printf '  %s%s %d  %-26s %-12s%s %-18s %-24s %s\n' "$color" "$sym" "$((i + 1))" "$op" "$st" "$C_RESET" "${at:-}" "${by%%@*}${by:+@}" "${commit:-}"
    if [[ "$st" == "FAILED" && -n "$errm" ]]; then printf '        %s\n' "${C_RED}${errm}${C_RESET}"; fi
  done
  echo
}

op_restore() {
  [[ -n "${TF_STATE_BUCKET-}" ]] || die "TF_STATE_BUCKET is empty in initialize.env"
  local remote="gs://${TF_STATE_BUCKET}/${RUNNER_PREFIX}" f tmp
  title "Restore from ${remote}"
  bucket_exists || die "Bucket gs://${TF_STATE_BUCKET} not found or not accessible."
  for f in initialize.env manualground.status; do
    tmp="$(mktemp)"
    if gcloud storage cp --quiet "$remote/$f" "$tmp" >/dev/null 2>&1; then
      mv "$tmp" "${MG_ROOT}/$f"
      ok "restored $f"
    else
      rm -f "$tmp"
      warn "$f not found in bucket"
    fi
  done
}

op_run_all() {
  local from_i=0 to_i=$(( ${#BOOTSTRAP_OPS[@]} - 1 )) i op rc args=() results=()
  if [[ -n "$FROM_OP" ]]; then
    from_i="$(op_index "$FROM_OP")" || die "Unknown --from operation: $FROM_OP (known: ${BOOTSTRAP_OPS[*]})"
  fi
  if [[ -n "$TO_OP" ]]; then
    to_i="$(op_index "$TO_OP")" || die "Unknown --to operation: $TO_OP (known: ${BOOTSTRAP_OPS[*]})"
  fi
  (( from_i <= to_i )) || die "--from ${BOOTSTRAP_OPS[$from_i]} comes after --to ${BOOTSTRAP_OPS[$to_i]}"

  (( AUTO_APPROVE )) && args+=(--auto-approve)
  (( FORCE )) && args+=(--force)
  (( DESCRIBE )) && args+=(--describe)
  (( VALIDATE_ONLY )) && args+=(--validate-only)
  args+=(--no-tmux)

  title "RunAll: ${C_MAGENTA}${BOOTSTRAP_OPS[$from_i]}${C_RESET} -> ${C_MAGENTA}${BOOTSTRAP_OPS[$to_i]}${C_RESET}  ${C_GRAY}($(( to_i - from_i + 1 )) operation(s))${C_RESET}"
  for (( i = from_i; i <= to_i; i++ )); do
    op="${BOOTSTRAP_OPS[$i]}"
    printf '%s\n' "${C_BOLD}=== $((i + 1))/${#BOOTSTRAP_OPS[@]}  ${op} ===${C_RESET}"
    rc=0
    "$TF_ROOT/run.sh" --operation="$op" "${args[@]}" || rc=$?
    if (( rc != 0 )); then
      results+=("${C_RED}✖ $((i + 1))  ${op}  (exit ${rc})${C_RESET}")
      for (( i = i + 1; i <= to_i; i++ )); do results+=("${C_GRAY}○ $((i + 1))  ${BOOTSTRAP_OPS[$i]}  (not run)${C_RESET}"); done
      title "RunAll stopped"
      printf '  %s\n' "${results[@]}"
      exit "$rc"
    fi
    results+=("${C_GREEN}✔ $((i + 1))  ${op}${C_RESET}")
  done
  title "RunAll finished"
  printf '  %s\n' "${results[@]}"
  echo
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
load_config

case "$OP" in
  RunAll)  op_run_all ;;
  Status)  op_status ;;
  Restore) op_restore ;;
  *)
    op_index "$OP" >/dev/null || die "Unknown operation: $OP (known: RunAll Status Restore ${BOOTSTRAP_OPS[*]})"
    run_operation "$OP" ;;
esac
