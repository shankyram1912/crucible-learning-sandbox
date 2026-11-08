#!/usr/bin/env bash
# Learning Sandbox Day-0: load initialize.env into the current shell.
#
#   source ./initialize.sh
#
# run.sh sources this itself on every run, so manual sourcing is only needed
# for ad-hoc terraform / gcloud commands.

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "initialize.sh must be sourced, not executed. Run:  source ./initialize.sh" >&2
  exit 1
fi

_lsb_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LSB_ENV_FILE="${LSB_ENV_FILE:-${_lsb_dir}/initialize.env}"
export LSB_ENV_FILE

if [[ ! -f "$LSB_ENV_FILE" ]]; then
  echo "Missing ${LSB_ENV_FILE}" >&2
  echo "Create it:  cp initialize.env.example initialize.env   then fill in the values." >&2
  unset _lsb_dir
  return 1
fi

# 1. Derive ORG_SUFFIX (first 3 hex chars of sha256(ORG_ID)) so initialize.env can use it,
#    e.g. CT_PROJECT_ID=lsb-control-tower-${ORG_SUFFIX}. A value set in the file overrides it.
ORG_SUFFIX="${ORG_SUFFIX-}"
export ORG_SUFFIX
_lsb_org_id="$( { grep -E '^ORG_ID=' "$LSB_ENV_FILE" || true; } | tail -n1 | cut -d= -f2- | tr -d "\"' ")"
if [[ -n "$_lsb_org_id" ]]; then
  ORG_SUFFIX="$(printf '%s' "$_lsb_org_id" | sha256sum | cut -c1-3)"
  export ORG_SUFFIX
fi

# 2. Load every KEY=value and export it.
set -a
# shellcheck disable=SC1090
. "$LSB_ENV_FILE"
set +a

# 3. Export a lowercase TF_VAR_ copy of every key in the file.
while IFS= read -r _lsb_key; do
  export "TF_VAR_${_lsb_key,,}=${!_lsb_key-}"
done < <(grep -E '^[A-Z_][A-Z0-9_]*=' "$LSB_ENV_FILE" | cut -d= -f1 | sort -u)

# 4. Keys required by every operation (per-operation keys are checked by run.sh Validate).
_lsb_missing=()
for _lsb_key in QUOTA_PROJECT; do
  [[ -n "${!_lsb_key-}" ]] || _lsb_missing+=("$_lsb_key")
done
if (( ${#_lsb_missing[@]} )); then
  echo "initialize.env is missing required values: ${_lsb_missing[*]}" >&2
  unset _lsb_dir _lsb_key _lsb_missing
  return 1
fi

# 5. Quota project for gcloud (session only, does not change global gcloud config) and Terraform.
export CLOUDSDK_CORE_PROJECT="$QUOTA_PROJECT"
export CLOUDSDK_BILLING_QUOTA_PROJECT="$QUOTA_PROJECT"
export GOOGLE_BILLING_PROJECT="$QUOTA_PROJECT"
export USER_PROJECT_OVERRIDE=true

# 6. Terraform: fail instead of prompting; every init uses the state bucket.
export TF_INPUT=0
if [[ -n "${TF_STATE_BUCKET-}" ]]; then
  export TF_CLI_ARGS_init="-backend-config=bucket=${TF_STATE_BUCKET}"
fi

export LSB_INITIALIZED=1

# 7. Summary and prompt prefix (skipped when run.sh sources this with LSB_QUIET=1).
if [[ -z "${LSB_QUIET-}" ]]; then
  echo "Learning Sandbox Day-0 settings loaded from ${LSB_ENV_FILE}"
  printf '  %-16s %s\n' \
    "QUOTA_PROJECT" "${QUOTA_PROJECT}" \
    "ORG_ID" "${ORG_ID-}" \
    "ORG_SUFFIX" "${ORG_SUFFIX-}" \
    "CT_PROJECT_ID" "${CT_PROJECT_ID-}" \
    "REGION" "${REGION-}" \
    "TF_STATE_BUCKET" "${TF_STATE_BUCKET-}"
  if [[ $- == *i* ]]; then
    LSB_ORIG_PS1="${LSB_ORIG_PS1-$PS1}"
    PS1="[ct: ${CT_PROJECT_ID:-?}] ${LSB_ORIG_PS1}"
  fi
fi

unset _lsb_dir _lsb_key _lsb_missing _lsb_org_id
return 0
