"""lsb: command line for the Learning Sandbox Self Service APIs.

Conventions: specs/tdd-apis/tdd-apis-common-cli.md; settings: tdd-apis-common-config.md section 4;
health commands: tdd-apis-health.md.
"""

import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import google.auth
import httpx
import typer
from google.auth.transport.requests import Request as GoogleRequest
from rich.console import Console

VERSION = "0.1.0"
SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email",
          "https://www.googleapis.com/auth/cloud-platform"]
SESSION_FILE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "lsb" / "session.json"
SESSION_TTL_SECONDS = 8 * 3600

app = typer.Typer(help="LSB Control Tower command line.", no_args_is_help=True, add_completion=False)
health_app = typer.Typer(help="Health of the Self Service APIs.", no_args_is_help=True)
app.add_typer(health_app, name="health")
platform_users_app = typer.Typer(help="Platform users: who has which platform role.", no_args_is_help=True)
app.add_typer(platform_users_app, name="platform-users")

console = Console()
err_console = Console(stderr=True)


class Opts:
    json: bool = False
    api: str = "http://localhost:8080"


opts = Opts()


@app.callback()
def main(json_out: bool = typer.Option(False, "--json", help="Print the raw API response, no colors."),
         api: str = typer.Option(None, "--api", help="API base URL (overrides LSB_API_URL).")):
    opts.json = json_out
    opts.api = (api or os.environ.get("LSB_API_URL") or "http://localhost:8080").rstrip("/")


# ---------------------------------------------------------------------------------------------
# Auth and session
# ---------------------------------------------------------------------------------------------
def _id_token() -> str:
    """ID token from the user's ADC (one refresh also yields the access token)."""
    try:
        creds, _ = google.auth.default(scopes=SCOPES)
        creds.refresh(GoogleRequest())
    except Exception as exc:  # noqa: BLE001
        _fail(2, f"No usable Google login ({type(exc).__name__}). Run: gcloud auth application-default login")
    token = getattr(creds, "id_token", None)
    if not token:
        _fail(2, "ADC did not return an ID token. Run: gcloud auth application-default login")
    return token


def _session_id() -> str:
    if os.environ.get("LSB_SESSION_ID"):
        return os.environ["LSB_SESSION_ID"]
    try:
        data = json.loads(SESSION_FILE.read_text())
        if time.time() - data["created"] < SESSION_TTL_SECONDS:
            return data["id"]
    except (OSError, ValueError, KeyError):
        pass
    sid = f"s-{uuid.uuid4().hex[:16]}"
    try:
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(json.dumps({"id": sid, "created": time.time()}))
    except OSError:
        pass
    return sid


def _get(path: str, params: dict | None = None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {_id_token()}", "X-LSB-Session-Id": _session_id(),
               "User-Agent": f"lsb-cli/{VERSION}"}
    t0 = time.monotonic()
    try:
        r = httpx.get(f"{opts.api}{path}", headers=headers, params=params, timeout=15)
    except httpx.HTTPError as exc:
        _fail(3, f"API unreachable at {opts.api} ({type(exc).__name__})")
    r.elapsed_ms = int((time.monotonic() - t0) * 1000)  # type: ignore[attr-defined]
    return r


def _fail(code: int, message: str) -> None:
    err_console.print(f"  [red]✖[/red] {message}")
    raise typer.Exit(code)


def _handle_errors(r: httpx.Response, ok_codes: tuple[int, ...]) -> dict:
    """Common exit codes: 2 for 400/401/403/404/409/422, 3 for 500 or anything unexpected."""
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code in ok_codes:
        return body
    if opts.json:
        console.print_json(data=body or {"status_code": r.status_code})
    err = body.get("error", {}) if isinstance(body, dict) else {}
    msg = f"{err.get('code', r.status_code)}: {err.get('message', r.reason_phrase)}"
    rid = err.get("request_id") or r.headers.get("x-request-id")
    if not opts.json:
        err_console.print(f"\n  [red]✖[/red] {msg}" + (f"   [dim]request {rid}[/dim]" if rid else "") + "\n")
    raise typer.Exit(2 if 400 <= r.status_code < 500 else 3)


# ---------------------------------------------------------------------------------------------
# lsb health api | db | service
# ---------------------------------------------------------------------------------------------
@health_app.command("api")
def health_api():
    """The API process is up (no dependencies)."""
    r = _get("/v1/health/api")
    body = _handle_errors(r, (200,))
    if opts.json:
        console.print_json(data=body)
        return
    console.print(f"\n  [green]✔[/green] API ok    [bold magenta]{body['service']}[/bold magenta] {body['version']}"
                  f"    caller [bold magenta]{body['caller']}[/bold magenta]    {r.elapsed_ms}ms\n")


ERROR_HINTS = {
    "PERMISSION_DENIED": "the API identity cannot read this database",
    "DATABASE_NOT_FOUND": "database ID is wrong or the database does not exist",
    "DEADLINE_EXCEEDED": "no answer within the read timeout",
    "UNAVAILABLE": "Firestore or the network is temporarily unavailable",
    "UNKNOWN": "see the API log",
}


@health_app.command("db")
def health_db():
    """Each Firestore database, with details (IT Admins)."""
    r = _get("/v1/health/db")
    body = _handle_errors(r, (200, 503))
    if opts.json:
        console.print_json(data=body)
    else:
        console.print()
        for d in body["databases"]:
            role = d["role"].lower().replace("_", "-")
            if d["status"] == "OK":
                console.print(f"  [green]✔[/green] {d['database']:<32} {role:<14} {d['latency_ms']}ms")
            else:
                e = d.get("error", "UNKNOWN")
                console.print(f"  [red]✖[/red] {d['database']:<32} {role:<14} [red]{e}[/red]    {ERROR_HINTS.get(e, '')}")
        ok = sum(1 for d in body["databases"] if d["status"] == "OK")
        n = len(body["databases"])
        console.print(f"\n  {'Databases ok' if ok == n else '[red]Databases failing[/red]'} ({ok}/{n})\n")
    raise typer.Exit(0 if r.status_code == 200 else 1)


@health_app.command("service")
def health_service():
    """Service and data areas, OK / NOT OK only."""
    r = _get("/v1/health/service")
    body = _handle_errors(r, (200, 503))
    if opts.json:
        console.print_json(data=body)
    else:
        def fmt(label: str, status: str) -> str:
            return f"{label} OK" if status == "OK" else f"[red]{label} NOT OK[/red]"
        mark = "[green]✔[/green]" if body["status"] == "OK" else "[red]✖[/red]"
        console.print(f"\n  {mark} {fmt('Service', body['status'])}    {fmt('CONFIG', body['config'])}"
                      f"    {fmt('RUNTIME JOBS', body['runtime_jobs'])}\n")
    raise typer.Exit(0 if r.status_code == 200 else 1)


# ---------------------------------------------------------------------------------------------
# lsb platform-users roles [EMAIL]
# ---------------------------------------------------------------------------------------------
@platform_users_app.command("roles")
def platform_roles(email: str = typer.Argument(None, help="Another user's email; default: you")):
    """All platform roles (USER, BU_ADMIN, IT_ADMIN, PLATFORM_ADMIN) and the admin groups that give them."""
    r = _get(f"/v1/platform-users/{quote(email, safe='@')}/roles" if email else "/v1/platform-users/me/roles")
    body = _handle_errors(r, (200,))
    if opts.json:
        console.print_json(data=body)
        return
    roles = "  ".join(f"[bold]{x}[/bold]" for x in body["roles"])
    console.print(f"\n  [green]✔[/green] [bold magenta]{body['email']}[/bold magenta]    {roles}")
    for g in body.get("groups", []):
        how = "direct" if g["relation"] == "DIRECT" else "nested"
        console.print(f"      member of [bold magenta]{g['group']}[/bold magenta] ({how})")
    console.print()


if __name__ == "__main__":
    app()
