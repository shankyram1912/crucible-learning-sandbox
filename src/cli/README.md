# lsb-cli: `lsb` command line

Typer + Rich client for the Self Service APIs. Conventions: [tdd-apis-common-cli.md](../../specs/tdd-apis/tdd-apis-common-cli.md).

## Install
On a Cloudtop, set the two `UV_*` variables from [src/api/README.md](../api/README.md) first.
```bash
cd src/cli && uv sync
alias lsb="$PWD/.venv/bin/lsb"
```

## Sign in
`lsb` uses your ADC; there is no separate login:
```bash
gcloud auth application-default login
```

## Use
```bash
lsb health api        # API up, shows the caller the API saw
lsb health db         # each Firestore database (Platform Admins only)
lsb health service    # OK / NOT OK only
lsb --json health service
lsb --api http://localhost:8080 health api    # or LSB_API_URL
```
Exit codes: `0` ok, `1` health check failing, `2` request rejected (401/403/...), `3` API unreachable or 500.
