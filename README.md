# Learning Sandbox (`learning-sandbox`)

The **LSB Control Tower** manages Google Cloud learning sandboxes for a university: IT Admins create **Playground Folders** under school folders, BU Admins create **playgrounds** (folder plus projects from a template) inside them, and students get access to the services enabled in their playground. Everything is driven through the **Learning Sandbox Self Service APIs** and the `lsb` command line tool; Terraform is used only for Day-0 bootstrap, playground project creation and enabling services.

## Repository structure

```text
learning-sandbox/
├── specs/                          Current specs (source of truth)
│   ├── control-tower-spec.md       Principles: Terraform, billing labels, playground tags, data split, IAM and access model
│   ├── day0-bootstrap-spec.md      Day-0 Control Tower bootstrap (run.sh and its operations)
│   ├── apiservices-spec.md         Self Service APIs and the lsb CLI
│   ├── terraform-pipeline-spec.md  Playground Terraform pipeline (Cloud Build)
│   └── gcpservices-spec.md         GCP services offered in playgrounds
├── src/
│   └── terraform/control-tower/    Day-0 bootstrap: run.sh, initialize.sh, one folder per operation
├── seed/                           Test users and seed data proposal (seed.md, users.csv)
├── todolist.md                     Build sequence and status
└── specs-reference/                Earlier BRS and TDD (01-brs, 02-tdd), kept for reference only; superseded by specs/
```

## Getting started

Day-0 bootstrap runs in Cloud Shell as an org admin. See [src/terraform/control-tower/README.md](src/terraform/control-tower/README.md) and [specs/day0-bootstrap-spec.md](specs/day0-bootstrap-spec.md).

## Conventions

- **Specs first:** decisions go into `specs/` and `todolist.md` before code.
- **Commit messages:** [Conventional Commits](https://www.conventionalcommits.org/), `type(scope): summary`, for example `feat(control-tower): add PlaygroundTagsCreate`.
