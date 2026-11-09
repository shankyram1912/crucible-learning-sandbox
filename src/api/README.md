# lsb-api: Learning Sandbox Self Service APIs

FastAPI service. Specs: [specs/tdd-apis/](../../specs/tdd-apis/tdd-apis-master.md). Settings: [tdd-apis-common-config.md](../../specs/tdd-apis/tdd-apis-common-config.md).

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
| `start.sh` | Starts the API locally |

## Install
Needs [uv](https://docs.astral.sh/uv/). On a Cloudtop, point uv at Corp Airlock for this shell:
```bash
export UV_DEFAULT_INDEX=http://airlock-proxy.uplink.goog:999/python/artifact-foundry-prod/python-3p-limited-internal-use/simple/
export UV_INSECURE_HOST=airlock-proxy.uplink.goog
cd src/api && uv sync
```

## Test
```bash
uv run pytest -q
```

## Run locally
The API uses your ADC as its own identity (Firestore reads, group membership checks).
```bash
./start.sh                  # http://127.0.0.1:8080
./start.sh --port 8090      # another port
./start.sh --reload         # restart on code changes while developing
```
[start.sh](start.sh) sources `src/terraform/control-tower/initialize.sh` (platform settings and quota project), sets `LSB_API_VERSION` to the current git commit, warns if ADC is missing, and runs uvicorn from `.venv`. Any `LSB_*` setting can be exported before running it.

Then use the CLI ([src/cli](../cli/README.md)): `lsb health api`, `lsb health db`, `lsb health service`.
