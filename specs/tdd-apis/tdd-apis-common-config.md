# LSB Control Tower TDD: APIs, Common Config

> Parent: [tdd-apis-master.md](tdd-apis-master.md)

The one place where every setting of the Self Service APIs and the `lsb` CLI is defined. Domain specs refer to settings by name and never introduce a setting without adding it here first.

---

## 1. Rules

1. **One settings object in code:** `src/api/lsb_api/settings.py` (a `pydantic-settings` `Settings` class) reads every setting below once at startup and validates it. The API **refuses to start** if a required setting is missing or invalid. No other code reads environment variables directly.
2. **Two kinds of keys:**
   - **Platform keys** describe the Control Tower and use the **same names as `initialize.env`** (for example `CT_PROJECT_ID`), so one value has one name everywhere. Their values come from Day-0.
   - **API keys** exist only for the API or CLI and are prefixed **`LSB_`**.
3. **Where values come from:**
   - **Local runs:** `source src/terraform/control-tower/initialize.sh` exports the platform keys; API keys use their defaults or are exported in the shell.
   - **Cloud Run (later):** environment variables set by Day-0 step 8 (`ControlTowerApiServiceCreate`) from `initialize.env`.
4. **Lists** are comma-separated, without spaces.
5. **No secrets** are settings. The API runs with its own identity (ADC locally, `sa-lsb-api` on Cloud Run); there are no keys or passwords to configure.
6. **Changing a setting means restarting or redeploying the API.** Settings are not read from Firestore at runtime. If a setting ever needs to change without a deploy (for example the Platform Admin groups), it moves to the config database and this table says so.

---

## 2. Platform keys (from `initialize.env`)

| Key | Required | Example (this environment) | Used for |
|---|---|---|---|
| `CT_PROJECT_ID` | yes | `lsb-control-tower-e26` | Firestore client project |
| `REGION` | yes | `asia-southeast1` | Default region for GCP calls |
| `DOMAIN` | yes | `shankyram.altostrat.com` | Token check: the caller must belong to this domain |
| `ORG_ID` | yes | `69296271958` | Organization-level calls (tags, folders) |
| `FIRESTORE_CONFIG_DATABASE` | yes | `lsb-control-tower-config-db` | Config (desired state) |
| `FIRESTORE_DATABASE` | yes | `lsb-control-tower-db` | Runtime state and jobs |
| `IT_ADMINS_GROUP` | yes | `grp-lsb-it-admins@shankyram.altostrat.com` | `IT_ADMIN` persona |
| `BU_ADMINS_GROUP` | yes | `grp-lsb-bu-admins@shankyram.altostrat.com` | `BU_ADMIN` persona |
| `TAG_KEY_COST_CENTER_BU_ID`, `TAG_KEY_COST_CENTER_CODE_ID`, `TAG_KEY_COST_CATEGORY_ID`, `TAG_KEY_BU_TRACKING_CODE_ID`, `TAG_KEY_BU_SUBCATEGORY_ID` | from the Playground Folder domain on | `tagKeys/281484385172110`, ... | Binding playground tags |

---

## 3. API keys

| Key | Required | Default | Meaning |
|---|---|---|---|
| `LSB_PLATFORM_ADMIN_GROUPS` | no | value of `BU_ADMINS_GROUP` | Groups whose members (transitively) are `PLATFORM_ADMIN` ([tdd-apis-common-models.md](tdd-apis-common-models.md) section 3). Today only `grp-lsb-bu-admins@` |
| `LSB_ALLOWED_AUDIENCES` | no | `32555940559.apps.googleusercontent.com` | OAuth client IDs (or Firebase project IDs) accepted as the `aud` of ID tokens ([tdd-apis-common-auth.md](tdd-apis-common-auth.md) section 1). The default is the public client ID that gcloud and ADC sign in with; **this is the decided setup for the CLI** (no separate `lsb` OAuth client). The UI step adds the Firebase project ID. Not a secret; a setting rather than a code constant because it belongs to Google |
| `LSB_API_VERSION` | no | `unknown` | Git commit the API was built from; returned by `health api` |
| `LSB_API_PORT` | no | `8080` | Port the API listens on |
| `LSB_LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LSB_HEALTH_DB_READ_TIMEOUT_SECONDS` | no | `2` | Per-database read timeout in `health db` and `health service` |
| `LSB_HEALTH_DB_TOTAL_TIMEOUT_SECONDS` | no | `5` | Overall limit for the parallel database reads |
| `LSB_HEALTH_SERVICE_CACHE_SECONDS` | no | `10` | How long `health service` reuses its last result |

---

## 4. CLI keys (read by `lsb`, not by the API)

| Key | Required | Default | Meaning |
|---|---|---|---|
| `LSB_API_URL` | no | `http://localhost:8080` | API base URL ([tdd-apis-common-stack.md](tdd-apis-common-stack.md) section 2); `--api` overrides it |
| `LSB_SESSION_ID` | no | generated and cached for a few hours | Session ID sent as `X-LSB-Session-Id` ([tdd-apis-common-models.md](tdd-apis-common-models.md) section 2) |
| `NO_COLOR` | no | unset | Any value disables colors |
