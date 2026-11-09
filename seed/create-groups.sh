#!/usr/bin/env bash
# Creates the seed groups (seed/groups.csv) and their memberships (seed/memberships.csv).
#
#   ./create-groups.sh
#
# Run by an IT Admin who has directory rights (Super Admin or Groups Admin), signed in to gcloud
# as themselves. This is a person acting in the directory, never the platform: the platform only
# reads groups (specs/tdd-master.md section 2.2).
#
# Uses DIRECTORY_CUSTOMER_ID and QUOTA_PROJECT from src/terraform/control-tower/initialize.env.
# Idempotent: existing groups and memberships are skipped. Never deletes anything.
# See seed/seed.md.

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CT_DIR="$ROOT/../src/terraform/control-tower"
LABELS="cloudidentity.googleapis.com/groups.discussion_forum,cloudidentity.googleapis.com/groups.security"

export LSB_ENV_FILE="$CT_DIR/initialize.env"
# shellcheck disable=SC1091
source "$CT_DIR/initialize.sh" >/dev/null
: "${DIRECTORY_CUSTOMER_ID:?missing in initialize.env}" "${QUOTA_PROJECT:?missing in initialize.env}"

echo "Signed in to gcloud as: $(gcloud config get-value account 2>/dev/null)"
echo

created=0 existing=0 added=0 present=0 failed=0

# 1. Groups
while IFS=, read -r email display description kind; do
  [[ "$email" == "email" || -z "$email" ]] && continue
  if gcloud identity groups describe "$email" --billing-project="$QUOTA_PROJECT" --format="value(name)" >/dev/null 2>&1; then
    echo "  • group $email exists ($kind)"; existing=$((existing + 1))
  elif gcloud identity groups create "$email" --customer="$DIRECTORY_CUSTOMER_ID" \
         --display-name="$display" --description="$description" --labels="$LABELS" \
         --with-initial-owner=empty --billing-project="$QUOTA_PROJECT" >/dev/null; then
    echo "  ✔ created group $email ($kind)"; created=$((created + 1))
  else
    echo "  ✘ could not create group $email" >&2; failed=$((failed + 1))
  fi
done < "$ROOT/groups.csv"

echo

# 2. Memberships (a member reached through nesting counts as present)
while IFS=, read -r group member note; do
  [[ "$group" == "group_email" || -z "$group" ]] && continue
  if gcloud identity groups memberships check-transitive-membership --group-email="$group" \
       --member-email="$member" --billing-project="$QUOTA_PROJECT" --format="value(hasMembership)" 2>/dev/null | grep -qi true; then
    echo "  • $member already in $group"; present=$((present + 1))
  elif gcloud identity groups memberships add --group-email="$group" --member-email="$member" \
         --roles=MEMBER --billing-project="$QUOTA_PROJECT" >/dev/null; then
    echo "  ✔ added $member to $group  ($note)"; added=$((added + 1))
  else
    echo "  ✘ could not add $member to $group (does the user exist? a new group can take a minute: re-run)" >&2
    failed=$((failed + 1))
  fi
done < "$ROOT/memberships.csv"

printf '\n  groups created %d, existing %d; memberships added %d, already present %d; failures %d\n' \
  "$created" "$existing" "$added" "$present" "$failed"
(( failed == 0 ))
