# Crucible — Learning Sandbox (`crucible-learning-sandbox`)

**Crucible** (the **LSB Control Tower**) manages governed, multi-tenant Google Cloud & AI learning sandboxes: IT Admins set up **Playground Folders**, version-tracked **Service Catalogs**, and **Playground Templates**; BU Admins and optional **Playground Admins** create **playgrounds** (folder plus project shards from a template) inside them; and students initialize isolated workspaces and build **app containers** within pooled allowances. Everything is driven through the **Self Service APIs** and the `lsb` CLI.

> **Documentation Site (Astro Starlight):** `https://shankyram1912.github.io/crucible-learning-sandbox/` (built directly in memory from `specs/`, `guides/`, and `todolist.md` via `site/` with zero duplicated `.md` files).

## Repository structure

```text
crucible-learning-sandbox/
├── specs/                          Current specifications (single source of truth)
│   ├── 01-brs/                     Business Requirements (brs-master, IT Admin, BU Admin & Student CUJs)
│   └── 02-tdd/                     Technical Design (tdd-master, control-tower, apis, playground, data, tags-labels)
├── src/
│   ├── terraform/control-tower/    Day-0 bootstrap: run.sh, initialize.sh, operations 01–05
│   ├── api/                        FastAPI Self Service APIs (lsb_api) + lsb-api-server.sh
│   └── cli/                        Typer CLI (lsb)
├── site/                           Astro + Starlight docs site (reads ../specs & ../guides directly)
├── seed/                           Test users, groups, and memberships
├── guides/                         End-user guides (lsb-cli-user-guide.md)
├── todolist.md                     Build sequence and status
└── specs-reference/                Earlier BRS and TDD, kept for reference
```

## Getting started

Day-0 bootstrap runs in Cloud Shell as an org admin. See [src/terraform/control-tower/README.md](src/terraform/control-tower/README.md) and [specs/02-tdd/tdd-control-tower/tdd-control-tower-master.md](specs/02-tdd/tdd-control-tower/tdd-control-tower-master.md).

The `lsb` command line: [guides/lsb-cli-user-guide.md](guides/lsb-cli-user-guide.md). Running the API locally: [src/api/README.md](src/api/README.md).

## Conventions

- **Specs first:** decisions go into `specs/` and `todolist.md` before code.
- **Commit messages:** [Conventional Commits](https://www.conventionalcommits.org/), `type(scope): summary`, for example `feat(control-tower): add PlaygroundTagsCreate`.
