# LSB Control Tower TDD: APIs, Health Domain

> Parent: [tdd-apis-master.md](tdd-apis-master.md)

Health tells an operator whether the Self Service APIs are up and whether they can reach their data. It has two operations: **`health api`** (the API process itself, no dependencies) and **`health db`** (one small read on each Firestore database). They replace the single `GET /v1/health` / `lsb health` row (1) in [apis-v0-interface.md](../../specs-reference/apis-v0-interface.md) A.2 and B.

| # (build order) | Operation | REST | CLI | Status |
|---|---|---|---|---|
| 01 | Health api | `GET /v1/health/api` | `lsb health api` | To do |
| 02 | Health db | `GET /v1/health/db` | `lsb health db` | To do |

---

## 1. Common rules

1. **Authentication is required** for both, like every other call ([tdd-apis-master.md](tdd-apis-master.md) principle 9, [tdd-apis-common-auth.md](tdd-apis-common-auth.md)). Both also get the common request and response headers and the RequestContext ([tdd-apis-common-models.md](tdd-apis-common-models.md)). There is no unauthenticated health endpoint. On Cloud Run later, the service uses the default TCP startup probe, so no HTTP probe needs to call these endpoints.
2. **Authorization:** any authenticated user of the org domain may call both. Responses contain no secrets and no internal error text, only status, timings and error codes.
3. **Read-only.** Neither operation writes anything, anywhere.
4. **Synchronous.** Both return the result directly (`200` or `503`), never a job.
5. **Platform identity for data checks.** `health db` reads Firestore with the API's own runtime identity (locally the developer's ADC, on Cloud Run `sa-lsb-api`), not the caller's access token, because it checks the platform's access, not the caller's.
6. **Configuration** comes from the same keys as `initialize.env`: `CT_PROJECT_ID`, `FIRESTORE_CONFIG_DATABASE`, `FIRESTORE_DATABASE`.

---

## 2. Operation 01: health api

**Purpose:** liveness. The API process is running, can verify a token, and knows which build it is.

**Request:** `GET /v1/health/api`, no body, no parameters.

**Response `200`:**
```json
{
  "status": "OK",
  "service": "lsb-api",
  "version": "f6c8d60",
  "time": "2026-11-09T01:30:00Z",
  "caller": "lsb-it-admin1@shankyram.altostrat.com"
}
```
| Field | Type | Required | Description |
|---|---|---|---|
| `status` | enum | yes | Always `OK` when the API answers |
| `service` | string | yes | `lsb-api` |
| `version` | string | yes | Git commit the API was built from (`LSB_API_VERSION`, set at build or start time; `unknown` if not set) |
| `time` | timestamp | yes | API server time (UTC) |
| `caller` | string (email) | yes | Email from the verified token, so the same call confirms authentication end to end |

Pydantic model: `HealthApiResponse` in `src/api/models/health.py`.

**No dependency calls:** no Firestore, Cloud Identity or GCP call, so it stays fast and never fails because something else is slow.

**Errors** (shape: [tdd-apis-common-models.md](tdd-apis-common-models.md) section 5): `401 UNAUTHENTICATED` (missing or invalid token). Anything else means the API is not healthy (`500 INTERNAL`, or unreachable).

**CLI:** `lsb health api`
```
$ lsb health api

  ✔ API ok    lsb-api f6c8d60    caller lsb-it-admin1@shankyram.altostrat.com    12ms
```

---

## 3. Operation 02: health db

**Purpose:** readiness of the data layer. The API can reach both Firestore databases with its own identity.

**Request:** `GET /v1/health/db`, no body, no parameters.

**Check per database** (both run in parallel, overall limit 5 seconds):
1. Read the document `_health/ping` with a 2-second timeout. The document does not need to exist: a "not found" document still proves network path, credentials, IAM and that the database exists. Cost: one document read per database.
2. Record status, latency, and on failure the error code only.

| Database | Role |
|---|---|
| `FIRESTORE_CONFIG_DATABASE` (`lsb-control-tower-config-db`) | `CONFIG` |
| `FIRESTORE_DATABASE` (`lsb-control-tower-db`) | `RUNTIME_JOBS` |

**Response `200`** (all databases ok) or **`503`** (at least one failed), same body shape:
```json
{
  "status": "OK",
  "databases": [
    { "database": "lsb-control-tower-config-db", "role": "CONFIG",       "status": "OK", "latency_ms": 41 },
    { "database": "lsb-control-tower-db",        "role": "RUNTIME_JOBS", "status": "OK", "latency_ms": 38 }
  ]
}
```
| Field | Type | Required | Description |
|---|---|---|---|
| `status` | enum | yes | `OK` if every database is `OK`, otherwise `FAIL` |
| `databases` | list of DatabaseCheck | yes | One entry per database, config first |
| `databases[].database` | string | yes | Database ID |
| `databases[].role` | enum | yes | `CONFIG` or `RUNTIME_JOBS` |
| `databases[].status` | enum | yes | `OK` or `FAIL` |
| `databases[].latency_ms` | integer | yes | Time for the read, or until it failed or timed out |
| `databases[].error` | enum | only if `FAIL` | One of the codes below |

Pydantic models: `HealthDbResponse`, `DatabaseCheck` in `src/api/models/health.py`.

On failure a database entry carries `"status": "FAIL"` and `"error"`, one of:

| `error` | Meaning | Usual fix |
|---|---|---|
| `PERMISSION_DENIED` | The API identity has no read access to this database | Firestore IAM for the API identity (Day-0 step 6) |
| `DATABASE_NOT_FOUND` | The database ID is wrong or the database does not exist | Check `FIRESTORE_CONFIG_DATABASE` / `FIRESTORE_DATABASE`, Day-0 step 3 |
| `DEADLINE_EXCEEDED` | No answer within 2 seconds | Network, or Firestore degraded |
| `UNAVAILABLE` | Firestore or the network is temporarily unavailable | Retry |
| `UNKNOWN` | Anything else (details only in the API log) | API log |


**Not in scope:** write checks (health never writes), database settings such as location or point-in-time recovery (checked by Day-0 readiness, `gcloud firestore databases describe`).

**CLI:** `lsb health db`
```
$ lsb health db

  ✔ lsb-control-tower-config-db    config          41ms
  ✔ lsb-control-tower-db           runtime-jobs    38ms

  Databases ok (2/2)
```
```
$ lsb health db

  ✖ lsb-control-tower-config-db    config          PERMISSION_DENIED    the API identity cannot read this database
  ✔ lsb-control-tower-db           runtime-jobs    38ms

  Databases failing (1/2)
```

---

## 4. CLI exit codes

| Code | `health api` | `health db` |
|---|---|---|
| `0` | API ok | All databases ok |
| `1` | n/a | At least one database failed (`503`) |
| `2` | `401` (not signed in or token rejected) | `401` |
| `3` | API unreachable or `500` | API unreachable or `500` |

`--json` prints the raw response for both commands ([tdd-apis-common-cli.md](tdd-apis-common-cli.md) section 2). Exit code `1` for a failing `health db` is the one addition to the common exit codes (section 3 there).

---

## 5. Test in the live environment

1. `lsb health api` as any seed user: `0`, with the caller's email shown.
2. `lsb health api` with no login: `2` (`401`).
3. `lsb health db` with the API's identity able to read both databases: `0`.
4. Temporarily point `FIRESTORE_CONFIG_DATABASE` at a wrong ID: `1`, `DATABASE_NOT_FOUND` on the config row only.
