# `lsb` CLI User Guide

`lsb` is the command line for the **LSB Control Tower Self Service APIs**. Every command calls the API; `lsb` never talks to GCP or Firestore directly. This guide covers installing it, signing in, pointing it at your API, and every command available today.

Developing `lsb` or running the API yourself: see [src/cli/README.md](../src/cli/README.md) and [src/api/README.md](../src/api/README.md).

---

## 1. Before you start

You need:
1. A Google account in your organization's domain (for this environment `shankyram.altostrat.com`).
2. The [gcloud CLI](https://cloud.google.com/sdk/docs/install), used here only to sign in (section 3).
3. [uv](https://docs.astral.sh/uv/getting-started/installation/), the Python tool installer. uv downloads a suitable Python by itself; you do not need to install Python first.
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS and Linux
   ```
4. The URL of your LSB Control Tower API, from your IT team (section 4).

---

## 2. Install

```bash
uv tool install "git+https://github.com/shankyram1912/learning-sandbox#subdirectory=src/cli"
lsb --help
```
uv puts `lsb` in its own environment and links the command into `~/.local/bin`. If `lsb` is not found afterwards, run `uv tool update-shell` and open a new terminal.

| Task | Command |
|---|---|
| Update to the latest version | `uv tool install --reinstall "git+https://github.com/shankyram1912/learning-sandbox#subdirectory=src/cli"` |
| Uninstall | `uv tool uninstall lsb-cli` |

---

## 3. Sign in

`lsb` uses your Google **Application Default Credentials (ADC)**; there is no separate `lsb login`.
```bash
gcloud auth application-default login                    # on a remote machine add --no-launch-browser
```
Sign in with your organization account. `lsb` gets everything it needs from that sign-in, and refreshes it automatically.

Check which account the API sees:
```bash
lsb health api        # shows "caller <your email>"
```
ADC can be signed in as a different account from your `gcloud` CLI login. If the caller is wrong, run the sign-in again.

---

## 4. Point `lsb` at your API

```bash
export LSB_API_URL=https://<your LSB Control Tower API>      # from your IT team
```
Add it to your shell profile (`~/.bashrc`, `~/.zshrc`) to keep it. For a single call use `lsb --api <url> ...`. Without a setting, `lsb` calls `http://localhost:8080`.

---

## 5. Commands

### 5.1 Health

| Command | Who can run it | Shows |
|---|---|---|
| `lsb health api` | Any signed-in user of the organization | API is up: version, the caller the API saw, latency |
| `lsb health db` | **Platform Admins** (IT Admins and BU Admins) | Each data store with its role and latency, or an error code |
| `lsb health service` | Any signed-in user of the organization | Service, CONFIG and RUNTIME JOBS as OK or NOT OK only |

```
$ lsb health api
  ✔ API ok    lsb-api 93711ed    caller admin@shankyram.altostrat.com    99ms

$ lsb health db
  ✔ lsb-control-tower-config-db      config         41ms
  ✔ lsb-control-tower-db             runtime-jobs   38ms
  Databases ok (2/2)

$ lsb health service
  ✔ Service OK    CONFIG OK    RUNTIME JOBS OK
```

When a data store fails, `lsb health db` names the error:

| Error | Meaning |
|---|---|
| `PERMISSION_DENIED` | The API cannot read this data store |
| `DATABASE_NOT_FOUND` | The data store is misconfigured or missing |
| `DEADLINE_EXCEEDED` | No answer in time |
| `UNAVAILABLE` | Temporarily unavailable; try again |
| `UNKNOWN` | Anything else; report it with the request ID |

### 5.2 Coming next
`lsb jobs`, `lsb templates`, `lsb playground-folder`, `lsb playground`, `lsb group members`, `lsb service`. This guide gains a section for each as it is released.

---

## 6. Options and settings

**Global options** go before the command:

| Option | Effect | Example |
|---|---|---|
| `--json` | Print the raw API response, no colors (for scripts) | `lsb --json health service` |
| `--api <url>` | Use another API URL for this call | `lsb --api https://... health api` |
| `--help` | Help for `lsb` or any command | `lsb health --help` |

**Environment variables:**

| Variable | Default | Effect |
|---|---|---|
| `LSB_API_URL` | `http://localhost:8080` | API base URL |
| `LSB_SESSION_ID` | generated, reused for 8 hours | Session ID sent with every call (section 7) |
| `NO_COLOR` | unset | Any value disables colors |

---

## 7. Exit codes, sessions and request IDs

| Exit code | Meaning |
|---|---|
| `0` | Success |
| `1` | A health check is failing |
| `2` | Request rejected: not signed in, sign-in rejected (`401`), not allowed (`403`), bad request |
| `3` | API unreachable, or an unexpected API error (`500`) |

Every call carries a **session ID** (one per terminal session, reused for 8 hours) and gets a **request ID** back. Errors print the request ID, for example `request r-a81ee4360ace457c`. Quote it when reporting a problem: it lets the platform team find the exact call and everything else in your session.

---

## 8. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `lsb: command not found` | Run `uv tool update-shell`, open a new terminal; or reinstall (section 2) |
| `No usable Google login (...)` or `ADC did not return an ID token` | Not signed in: `gcloud auth application-default login` |
| `API unreachable at ...` | Wrong or missing `LSB_API_URL`, or no network path to the API |
| `UNAUTHENTICATED: Caller is not in <domain>` | Signed in with a personal or other account: sign in again with your organization account |
| `UNAUTHENTICATED: Invalid ID token: ...` | Sign-in expired or not accepted (`audience not accepted` means the API does not trust the app you signed in with): sign in again with `gcloud auth application-default login`; if it persists, contact the platform team with the request ID |
| `PERMISSION_DENIED: This operation needs the PLATFORM_ADMIN persona` | `lsb health db` is for Platform Admins; use `lsb health service` |
