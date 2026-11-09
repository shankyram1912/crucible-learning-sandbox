#!/usr/bin/env bash
# Starts the Learning Sandbox Self Service APIs locally.
#
#   ./start.sh [--port 8080] [--host 127.0.0.1] [--reload]
#
# Loads the platform settings from src/terraform/control-tower/initialize.env (via initialize.sh),
# sets LSB_API_VERSION to the current git commit, and runs uvicorn from the project's .venv.
# The API uses your ADC as its own identity (Firestore reads, group membership checks).
# Settings: specs/tdd-apis/tdd-apis-common-config.md

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CT_DIR="$ROOT/../terraform/control-tower"
HOST="${LSB_API_HOST:-127.0.0.1}"
PORT=""
RELOAD=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)   PORT="$2"; shift 2 ;;
    --port=*) PORT="${1#*=}"; shift ;;
    --host)   HOST="$2"; shift 2 ;;
    --host=*) HOST="${1#*=}"; shift ;;
    --reload) RELOAD=(--reload --reload-dir "$ROOT/lsb_api"); shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# 1. Python environment
if [[ ! -x "$ROOT/.venv/bin/uvicorn" ]]; then
  echo "No .venv in $ROOT. Install first (see README.md):" >&2
  echo "  cd $ROOT && uv sync" >&2
  exit 2
fi

# 2. Platform settings (CT_PROJECT_ID, DOMAIN, FIRESTORE_*, groups) and the quota project
if [[ ! -f "$CT_DIR/initialize.env" ]]; then
  echo "Missing $CT_DIR/initialize.env (Day-0 settings). Copy initialize.env.example and fill it in." >&2
  exit 2
fi
# shellcheck disable=SC1091
source "$CT_DIR/initialize.sh" >/dev/null

# 3. API settings
export LSB_API_VERSION="${LSB_API_VERSION:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)}"
PORT="${PORT:-${LSB_API_PORT:-8080}}"
export LSB_API_PORT="$PORT"

# 4. Credentials check (the API runs as your ADC)
if ! command -v gcloud >/dev/null || ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
  echo "Warning: no usable ADC. Run: gcloud auth application-default login" >&2
fi

echo "Starting lsb-api ${LSB_API_VERSION} on http://${HOST}:${PORT}  (project ${CT_PROJECT_ID}, Ctrl-C to stop)"
exec "$ROOT/.venv/bin/uvicorn" lsb_api.main:app_factory --factory --app-dir "$ROOT" \
  --host "$HOST" --port "$PORT" "${RELOAD[@]}"
