#!/usr/bin/env bash
# Starts the Learning Sandbox Self Service APIs locally, inside a tmux session.
#
#   ./start.sh [--port 8080] [--host 127.0.0.1] [--reload]   start (if needed) in tmux session lsb-api and attach
#   ./start.sh --detach  [same options]                      start (if needed) in tmux and return to the prompt
#   ./start.sh --status                                      is it running, on which port, last log lines
#   ./start.sh --stop                                        stop the API (kills the tmux session)
#   ./start.sh --no-tmux [same options]                      run in the foreground of this terminal
#
# Detach from the attached session with Ctrl-b d (the API keeps running). Logs: src/api/logs/lsb-api.log.
# Loads the platform settings from src/terraform/control-tower/initialize.env (via initialize.sh),
# sets LSB_API_VERSION to the current git commit, and runs uvicorn from the project's .venv.
# The API uses your ADC as its own identity (Firestore reads, group membership checks).
# Settings: specs/tdd-apis/tdd-apis-common-config.md

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CT_DIR="$ROOT/../terraform/control-tower"
SESSION="lsb-api"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/lsb-api.log"
PORT_FILE="$LOG_DIR/lsb-api.port"
HOST="${LSB_API_HOST:-127.0.0.1}"
PORT=""
RELOAD=()
MODE="attach"
PASS=()   # options passed through to the foreground run inside tmux

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)    PORT="$2"; PASS+=(--port "$2"); shift 2 ;;
    --port=*)  PORT="${1#*=}"; PASS+=("$1"); shift ;;
    --host)    HOST="$2"; PASS+=(--host "$2"); shift 2 ;;
    --host=*)  HOST="${1#*=}"; PASS+=("$1"); shift ;;
    --reload)  RELOAD=(--reload --reload-dir "$ROOT/lsb_api"); PASS+=(--reload); shift ;;
    --detach)  MODE="detach"; shift ;;
    --status)  MODE="status"; shift ;;
    --stop)    MODE="stop"; shift ;;
    --no-tmux) MODE="foreground"; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

running() { command -v tmux >/dev/null && tmux has-session -t "$SESSION" 2>/dev/null; }

show_tail() {
  [[ -f "$LOG_FILE" ]] && { echo "--- last lines of $LOG_FILE"; tail -n "${1:-8}" "$LOG_FILE"; }
  return 0
}

# ---------------------------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------------------------
case "$MODE" in
  status)
    if running; then
      echo "lsb-api is running in tmux session '$SESSION' on port $(cat "$PORT_FILE" 2>/dev/null || echo '?')"
      echo "  attach: ./start.sh    stop: ./start.sh --stop"
    else
      echo "lsb-api is not running"
    fi
    show_tail 5
    exit 0 ;;
  stop)
    if running; then
      tmux kill-session -t "$SESSION"
      echo "lsb-api stopped"
    else
      echo "lsb-api is not running"
    fi
    exit 0 ;;
  attach|detach)
    if ! command -v tmux >/dev/null; then
      echo "tmux not found: running in the foreground instead (install tmux for a background session)" >&2
      MODE="foreground"
    else
      if running; then
        echo "lsb-api is already running in tmux session '$SESSION' on port $(cat "$PORT_FILE" 2>/dev/null || echo '?')"
        [[ ${#PASS[@]} -gt 0 ]] && echo "  (options ignored; stop it first to change them: ./start.sh --stop)"
      else
        mkdir -p "$LOG_DIR"
        printf -v inner '%q ' "$0" --no-tmux "${PASS[@]}"
        tmux new-session -d -s "$SESSION" -c "$ROOT" \
          "bash -c 'set -o pipefail; ${inner} 2>&1 | tee -a $(printf %q "$LOG_FILE")'"
        sleep 2
        if ! running; then
          echo "lsb-api failed to start" >&2
          show_tail 15 >&2
          exit 1
        fi
        echo "lsb-api started in tmux session '$SESSION' (port $(cat "$PORT_FILE" 2>/dev/null || echo "${PORT:-8080}"), log $LOG_FILE)"
      fi
      if [[ "$MODE" == "detach" ]]; then
        echo "  attach: ./start.sh    status: ./start.sh --status    stop: ./start.sh --stop"
        exit 0
      fi
      if [[ ! -t 0 || ! -t 1 ]]; then
        echo "  not a terminal, so not attaching (attach later with ./start.sh)"
        exit 0
      fi
      echo "  attaching; detach with Ctrl-b d (the API keeps running)"
      if [[ -n "${TMUX-}" ]]; then
        tmux switch-client -t "$SESSION"
      else
        tmux attach-session -t "$SESSION" || true
      fi
      running || { echo "lsb-api has stopped"; show_tail 8; }
      exit 0
    fi ;;
esac

# ---------------------------------------------------------------------------------------------
# Foreground run (also what the tmux session executes)
# ---------------------------------------------------------------------------------------------
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
# Always use this repo's initialize.env, even if the shell still has LSB_ENV_FILE from an older checkout.
export LSB_ENV_FILE="$CT_DIR/initialize.env"
# shellcheck disable=SC1091
source "$CT_DIR/initialize.sh" >/dev/null

# 3. API settings
export LSB_API_VERSION="${LSB_API_VERSION:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)}"
PORT="${PORT:-${LSB_API_PORT:-8080}}"
export LSB_API_PORT="$PORT"
mkdir -p "$LOG_DIR" && echo "$PORT" > "$PORT_FILE"

# 4. Credentials check (the API runs as your ADC)
if ! command -v gcloud >/dev/null || ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
  echo "Warning: no usable ADC. Run: gcloud auth application-default login" >&2
fi

echo "$(date -u +%FT%TZ) Starting lsb-api ${LSB_API_VERSION} on http://${HOST}:${PORT}  (project ${CT_PROJECT_ID}, Ctrl-C to stop)"
exec "$ROOT/.venv/bin/uvicorn" lsb_api.main:app_factory --factory --app-dir "$ROOT" \
  --host "$HOST" --port "$PORT" "${RELOAD[@]}"
