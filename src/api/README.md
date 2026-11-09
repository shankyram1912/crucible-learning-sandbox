# lsb-api: Learning Sandbox Self Service APIs

FastAPI service. Specs: [specs/02-tdd/tdd-apis/](../../specs/02-tdd/tdd-apis/tdd-apis-master.md). Settings: [tdd-apis-common-config.md](../../specs/02-tdd/tdd-apis/tdd-apis-common-config.md).

## Layout
| Path | What |
|---|---|
| `lsb_api/settings.py` | Every setting, validated at startup (the only place that reads the environment) |
| `lsb_api/context.py` | ID token verification, RequestContext, personas (Cloud Identity transitive membership) |
| `lsb_api/errors.py` | One error shape for every 4xx/5xx |
| `lsb_api/models/` | Pydantic models: `common.py`, one module per domain (`health.py`) |
| `lsb_api/<domain>.py` | One router per domain (`health.py`) |
| `lsb_api/main.py` | App factory, correlation middleware (request and session IDs) |
| `tests/` | Unit tests with fakes (no GCP needed) |
| `lsb-api-server.sh` | Starts, attaches to, checks and stops the local API (tmux session `lsb-api`) |

## Install
Needs [uv](https://docs.astral.sh/uv/) (it fetches a suitable Python itself).
```bash
cd src/api && uv sync
```
Googlers on corp machines: configure Corp Airlock once in `~/.config/uv/uv.toml` (see [src/cli/README.md](../cli/README.md)); nothing changes in the project.

## Test
```bash
uv run pytest -q
```

## Run locally
The API uses your ADC as its own identity (Firestore reads, group membership checks). It runs in a tmux session `lsb-api`, so it survives a closed terminal or a dropped SSH connection.
```bash
./lsb-api-server.sh                  # start (if needed) in tmux and attach; detach with Ctrl-b d
./lsb-api-server.sh --detach         # start (if needed) and return to the prompt
./lsb-api-server.sh --status         # running? port, last log lines
./lsb-api-server.sh --stop           # stop it
./lsb-api-server.sh --port 8090      # another port (options apply when it starts)
./lsb-api-server.sh --no-tmux --reload   # foreground, restart on code changes while developing
```
[lsb-api-server.sh](lsb-api-server.sh) sources `src/terraform/control-tower/initialize.sh` (platform settings and quota project, always this repo's `initialize.env`), sets `LSB_API_VERSION` to the current git commit, warns if ADC is missing, and runs uvicorn from `.venv`. Logs go to `logs/lsb-api.log` (gitignored). Any `LSB_*` setting can be exported before running it.

Then use the CLI ([user guide](../../guides/lsb-cli-user-guide.md), or `uv run lsb ...` from [src/cli](../cli/README.md)): `lsb health api`, `lsb health db`, `lsb health service`.
