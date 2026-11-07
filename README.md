# Learning Sandbox (`learning-sandbox`)

Visual Canvas & Multi-Tier Control Tower for managing GCP Learning Sandboxes across **IT Admins**, **BU / School Admins**, and **Students** (`IT Admin ⊃ BU Admin ⊃ Student`).

## Repository Structure

```text
learning-sandbox/
├── specs/
│   ├── 01-business-spec.md                              # Functional & Domain Source of Truth
│   └── 02-technical-design/                             # Technical Design Master Collection
│       ├── 00-master-architecture.md                    # System Topology, Cross-Module Contracts & End-to-End Flows
│       ├── 01-bootstrap-spec.md                         # Day-0 Control Tower Setup (Root IAM, Tag Keys, State Bucket, Pub/Sub)
│       ├── 02-data-spec.md                              # Firebase DB Schema (/environments/{live|simulate}/...)
│       ├── 03-bff/                                      # BFF (FastAPI) Master + Functional Sub-Specs
│       │   ├── 00-bff-master-spec.md
│       │   ├── 01-auth-and-persona-spec.md
│       │   ├── 02-control-and-lock-engine-spec.md
│       │   ├── 03-it-admin-bff-spec.md
│       │   ├── 04-bu-admin-bff-spec.md
│       │   ├── 05-directory-and-roster-bff-spec.md
│       │   └── 06-student-sandbox-bff-spec.md
│       ├── 04-ui/                                       # UI (React + Tailwind + React Flow) Master + Functional Sub-Specs
│       │   ├── 00-ui-master-spec.md
│       │   ├── 01-lock-and-pipeline-drawer-ui-spec.md
│       │   ├── 02-it-admin-canvas-ui-spec.md
│       │   ├── 03-bu-admin-cohort-canvas-ui-spec.md
│       │   ├── 04-project-drilldown-canvas-ui-spec.md
│       │   └── 05-student-sandbox-canvas-ui-spec.md
│       ├── 05-it-admin-pipeline-spec.md                 # IT Admin Terraform Pipeline Spec
│       ├── 06-bu-admin-pipeline-spec.md                 # BU Admin Terraform Pipeline & Project Services Spec
│       ├── 07-atomic-pipeline-spec.md                   # Atomic Pipeline Spec (Student Create/Delete + Cohort Sharding)
│       └── 08-agy-portal-guide-skill-spec.md            # Packaged AGY Skill User Guide Spec
│
└── src/
    ├── terraform/
    │   ├── bootstrap/                                   # Day-0 Control Tower project & root setup
    │   ├── itadmin/                                     # School folders, dept sub-folders, BU admin groups & folder budgets
    │   └── buadmin/                                     # Cohort folders, project shards, project services & budget overrides
    ├── bff/
    │   ├── core/                                        # Config, auth/persona resolver, lock engine & Firebase client
    │   ├── routers/                                     # FastAPI routers (it_admin, bu_admin, directory_roster, student)
    │   └── pipelines/                                   # Pipeline runners (it_terraform, bu_terraform, atomic)
    ├── ui/
    │   └── src/
    │       ├── components/shell/                        # Navbar, LockBanner, PipelineDrawer & SimControlBar
    │       └── features/                                # React Flow canvas views (it-canvas, bu-cohort-canvas, project-drilldown, student-canvas)
    └── agy-skill/                                       # Packaged SKILL.md user guide for the Self-Service Portal
```
