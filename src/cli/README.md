# lsb-cli: `lsb` command line (developers)

Typer + Rich client for the Self Service APIs. **Users: see the [lsb CLI user guide](../../guides/lsb-cli-user-guide.md)** (install from the git URL, sign in, commands). Conventions: [tdd-apis-common-cli.md](../../specs/tdd-apis/tdd-apis-common-cli.md).

## Work on the CLI
```bash
cd src/cli
uv sync                     # project environment in .venv
uv run lsb health api       # run from the source tree
```

## Use your working copy as the installed `lsb`
An editable install runs the code in your clone, so edits apply immediately:
```bash
uv tool install --editable --reinstall ~/work/code/learning-sandbox/src/cli
```
Switch back to the released version with the install command from the user guide (`uv tool install --reinstall "git+https://github.com/..."`).

## Against a local API
Start the API with [src/api/lsb-api-server.sh](../api/README.md) (default `http://localhost:8080`, which is also `lsb`'s default URL).

## Notes
- Googlers on corp machines: uv must use Corp Airlock. Configure it once in `~/.config/uv/uv.toml` (default index = the airlock proxy URL from `/etc/pip.conf`, with `allow-insecure-host` for its host); no project file or command changes.
