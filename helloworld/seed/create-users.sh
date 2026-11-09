#!/usr/bin/env bash
# Creates the hello world seed users (seed/users.csv) and adds them to their service group.
#
#   ./create-users.sh [--dry-run] [--csv=users.csv]
#
# gcloud has no command to create Cloud Identity / Workspace users, so users are created with the
# Admin SDK Directory API (curl, token from gcloud). Group memberships use `gcloud identity`.
# Idempotent: existing users and memberships are skipped. Never deletes anything.
#
# One-time setup (as a Super Admin, in Cloud Shell):
#   gcloud auth application-default login --no-launch-browser \
#     --scopes=https://www.googleapis.com/auth/admin.directory.user,https://www.googleapis.com/auth/cloud-platform
#   gcloud services enable admin.googleapis.com --project="$QUOTA_PROJECT"
#
# Password: taken from LSB_SEED_PASSWORD, or prompted once (not echoed). It is never written to disk.
# See seed/seed.md.

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CSV="$ROOT/users.csv"
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --csv=*)   CSV="${arg#--csv=}" ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

QUOTA_PROJECT="${QUOTA_PROJECT:-${CLOUDSDK_BILLING_QUOTA_PROJECT:-}}"
[[ -n "$QUOTA_PROJECT" ]] || { echo "Set QUOTA_PROJECT (or source control-tower/initialize.sh first)" >&2; exit 2; }
[[ -f "$CSV" ]] || { echo "CSV not found: $CSV" >&2; exit 2; }
for bin in gcloud curl jq; do command -v "$bin" >/dev/null || { echo "$bin is required" >&2; exit 2; }; done

ok()   { printf '  \e[32m✔\e[0m %s\n' "$*"; }
skip() { printf '  \e[90m•\e[0m %s\n' "$*"; }
fail() { printf '  \e[31m✘\e[0m %s\n' "$*" >&2; }

API="https://admin.googleapis.com/admin/directory/v1/users"
TOKEN=""
if (( ! DRY_RUN )); then
  TOKEN="$(gcloud auth application-default print-access-token)"
  if [[ -z "${LSB_SEED_PASSWORD-}" ]]; then
    read -r -s -p "Password for the seed users (min 8 chars): " LSB_SEED_PASSWORD; echo
  fi
  (( ${#LSB_SEED_PASSWORD} >= 8 )) || { echo "password too short" >&2; exit 2; }
fi

directory() { # method url [json]
  local args=(-sS -o /tmp/lsb-seed-resp.$$ -w '%{http_code}' -X "$1"
              -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $QUOTA_PROJECT")
  [[ $# -ge 3 ]] && args+=(-H "Content-Type: application/json" -d "$3")
  curl "${args[@]}" "$2"
}
trap 'rm -f /tmp/lsb-seed-resp.$$' EXIT

created=0 existing=0 added=0 failed=0
printf '\nSeed users from %s%s\n\n' "$CSV" "$( (( DRY_RUN )) && echo ' (dry run)')"

while IFS=, read -r email given family persona group; do
  [[ "$email" == "email" || -z "$email" ]] && continue

  # 1. User
  if (( DRY_RUN )); then
    skip "would ensure user $email ($persona)"
  else
    code="$(directory GET "$API/$email")"
    if [[ "$code" == "200" ]]; then
      skip "user $email exists"; existing=$((existing + 1))
    elif [[ "$code" == "404" ]]; then
      body="$(jq -cn --arg e "$email" --arg g "$given" --arg f "$family" --arg p "$LSB_SEED_PASSWORD" \
        '{primaryEmail:$e, name:{givenName:$g, familyName:$f}, password:$p, changePasswordAtNextLogin:false, orgUnitPath:"/"}')"
      code="$(directory POST "$API" "$body")"
      if [[ "$code" == "200" ]]; then
        ok "created user $email ($persona)"; created=$((created + 1))
      else
        fail "create $email failed (HTTP $code): $(jq -r '.error.message? // .' /tmp/lsb-seed-resp.$$)"; failed=$((failed + 1)); continue
      fi
    else
      fail "lookup $email failed (HTTP $code): $(jq -r '.error.message? // .' /tmp/lsb-seed-resp.$$)"; failed=$((failed + 1)); continue
    fi
  fi

  # 2. Service group membership (only the first three users have one)
  [[ -z "$group" ]] && continue
  if (( DRY_RUN )); then
    skip "would add $email to $group"
  elif gcloud identity groups memberships check-transitive-membership --group-email="$group" --member-email="$email" \
         --billing-project="$QUOTA_PROJECT" --format="value(hasMembership)" 2>/dev/null | grep -qi true; then
    skip "$email already in $group"
  elif gcloud identity groups memberships add --group-email="$group" --member-email="$email" --roles=MEMBER \
         --billing-project="$QUOTA_PROJECT" >/dev/null 2>/tmp/lsb-seed-resp.$$; then
    ok "added $email to $group"; added=$((added + 1))
  else
    # A newly created user can take a short while to be visible to Cloud Identity: re-run the script.
    fail "add $email to $group failed: $(tail -1 /tmp/lsb-seed-resp.$$) (re-run in a minute)"; failed=$((failed + 1))
  fi
done < "$CSV"

printf '\n  users created %d, already existed %d, memberships added %d, failures %d\n\n' "$created" "$existing" "$added" "$failed"
(( failed == 0 ))
