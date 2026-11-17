#!/usr/bin/env bash
# ManualGround: load initialize.env into the current shell for Terraform & CLI runs.
#
#   source ./initialize.sh
#
# terraform/run.sh sources this automatically on every run, so manual sourcing is only
# needed for ad-hoc terraform, gcloud, or ./mg commands.

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "initialize.sh must be sourced, not executed. Run:  source ./initialize.sh" >&2
  exit 1
fi

_mg_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MG_ENV_FILE="${MG_ENV_FILE:-${_mg_dir}/initialize.env}"
LSB_ENV_FILE="$MG_ENV_FILE"
export MG_ENV_FILE LSB_ENV_FILE

if [[ ! -f "$MG_ENV_FILE" ]]; then
  echo "Missing ${MG_ENV_FILE}" >&2
  echo "Create it:  cp initialize.env.example initialize.env   then fill in the values." >&2
  unset _mg_dir
  return 1
fi

# 1. Derive ORG_SUFFIX (first 3 hex chars of sha256(ORG_ID)) so initialize.env can reference ${ORG_SUFFIX}.
ORG_SUFFIX="${ORG_SUFFIX-}"
export ORG_SUFFIX
_mg_org_id="$( { grep -E '^ORG_ID=' "$MG_ENV_FILE" || true; } | tail -n1 | cut -d= -f2- | tr -d "\"' ")"
if [[ -n "$_mg_org_id" ]]; then
  ORG_SUFFIX="$(printf '%s' "$_mg_org_id" | sha256sum | cut -c1-3)"
  export ORG_SUFFIX
fi

# 2. Load every KEY=value and export it.
set -a
# shellcheck disable=SC1090
. "$MG_ENV_FILE"
set +a

# 3. Export a lowercase TF_VAR_ copy of every key defined in initialize.env.
while IFS= read -r _mg_key; do
  export "TF_VAR_${_mg_key,,}=${!_mg_key-}"
done < <(grep -E '^[A-Z_][A-Z0-9_]*=' "$MG_ENV_FILE" | cut -d= -f1 | sort -u)

# 3b. Billing labels: LABEL_<NAME>=value -> TF_VAR_billing_labels = {"<name>": "value", ...}
_mg_labels=""
while IFS= read -r _mg_key; do
  _mg_name="${_mg_key#LABEL_}"; _mg_name="${_mg_name,,}"; _mg_name="${_mg_name//_/-}"
  _mg_val="${!_mg_key-}"
  _mg_labels+="${_mg_labels:+,}\"${_mg_name}\":\"${_mg_val//\"/}\""
done < <(grep -E '^LABEL_[A-Z0-9_]+=' "$MG_ENV_FILE" | cut -d= -f1 | sort -u || true)
export TF_VAR_billing_labels="{${_mg_labels}}"

# 4. Validate baseline required key.
_mg_missing=()
for _mg_key in QUOTA_PROJECT; do
  [[ -n "${!_mg_key-}" ]] || _mg_missing+=("$_mg_key")
done
if (( ${#_mg_missing[@]} )); then
  echo "initialize.env is missing required values: ${_mg_missing[*]}" >&2
  unset _mg_dir _mg_key _mg_missing _mg_org_id _mg_labels _mg_name _mg_val
  return 1
fi

# 5. Quota project for gcloud (session-scoped) and Google client libraries / Terraform.
export CLOUDSDK_CORE_PROJECT="$QUOTA_PROJECT"
export CLOUDSDK_BILLING_QUOTA_PROJECT="$QUOTA_PROJECT"
export GOOGLE_BILLING_PROJECT="$QUOTA_PROJECT"
export GOOGLE_CLOUD_QUOTA_PROJECT="$QUOTA_PROJECT"
export USER_PROJECT_OVERRIDE=true

# 6. Terraform binary discovery: prefer ~/.local/bin/terraform or workspace tools/terraform-1.17.1.
for _mg_tf_dir in "${HOME}/.local/bin" "/usr/local/google/home/shankyram/workspace/code-sandbox/tools/terraform-1.17.1"; do
  if [[ -x "${_mg_tf_dir}/terraform" ]]; then
    case ":${PATH}:" in
      *":${_mg_tf_dir}:"*) ;;
      *) export PATH="${_mg_tf_dir}:${PATH}" ;;
    esac
    hash -r 2>/dev/null || true
    break
  fi
done
export TF_INPUT=0
if [[ -n "${TF_STATE_BUCKET-}" ]]; then
  export TF_CLI_ARGS_init="-backend-config=bucket=${TF_STATE_BUCKET}"
fi

export MG_INITIALIZED=1

# 7. Summary and prompt prefix (skipped when sourced with MG_QUIET=1 or LSB_QUIET=1).
if [[ -z "${MG_QUIET-}${LSB_QUIET-}" ]]; then
  echo "ManualGround settings loaded from ${MG_ENV_FILE}"
  printf '  %-24s %s\n' \
    "QUOTA_PROJECT" "${QUOTA_PROJECT}" \
    "ORG_ID" "${ORG_ID-}" \
    "MG_FOLDER_ID" "${MG_FOLDER_ID-(create ${MG_FOLDER_NAME-NTU Playground})}" \
    "MG_PROJECT_ID" "${MG_PROJECT_ID-}" \
    "REGION" "${REGION-asia-southeast1}" \
    "MG_PRESET" "${MG_PRESET-dev}" \
    "ENABLE_CLOUD_SQL" "${ENABLE_CLOUD_SQL-true}" \
    "MAX_SERVICES_PER_STUDENT" "${MAX_SERVICES_PER_STUDENT-3}" \
    "TF_STATE_BUCKET" "${TF_STATE_BUCKET-(local state)}"
  if [[ $- == *i* ]]; then
    MG_ORIG_PS1="${MG_ORIG_PS1-$PS1}"
    PS1="[mg: ${MG_PROJECT_ID:-?}] ${MG_ORIG_PS1}"
  fi
fi

unset _mg_dir _mg_key _mg_missing _mg_org_id _mg_labels _mg_name _mg_val _mg_tf_dir
return 0
