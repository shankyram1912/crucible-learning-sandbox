#!/usr/bin/env bash
# Writes the Admin console upload file for the seed users: seed/users.csv with the Password column
# filled in. The repo copy never contains a password.
#
#   export LSB_SEED_PASSWORD='...'          # set in your shell (or leave unset to be prompted)
#   ./make-upload-csv.sh [output]           # default output: ~/lsb-users-upload.csv (outside the repo)
#
# Upload the output in Admin console > Directory > Users > Bulk update users, then delete it.
# See seed/seed.md.

set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$HOME/lsb-users-upload.csv}"

case "$(cd "$(dirname "$OUT")" 2>/dev/null && pwd)/" in
  "$(cd "$ROOT/.." && pwd)/"*) echo "Refusing to write the password file inside the repo: $OUT" >&2; exit 2 ;;
esac

if [[ -z "${LSB_SEED_PASSWORD-}" ]]; then
  read -r -s -p "Seed password (min 8 chars): " LSB_SEED_PASSWORD; echo
fi
(( ${#LSB_SEED_PASSWORD} >= 8 )) || { echo "Password must be at least 8 characters" >&2; exit 2; }
[[ "$LSB_SEED_PASSWORD" != *","* ]] || { echo "Password must not contain a comma (CSV)" >&2; exit 2; }

umask 077
awk -F, -v OFS=, -v pw="$LSB_SEED_PASSWORD" 'NR>1 && NF>1 {$4=pw} 1' "$ROOT/users.csv" > "$OUT"
echo "Wrote $(( $(wc -l < "$OUT") - 1 )) users to $OUT (mode 600). Upload it, then: rm $OUT"
