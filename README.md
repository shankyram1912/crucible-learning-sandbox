# Learning Sandbox (`learning-sandbox`)

Visual Canvas & Multi-Tier Control Tower for managing GCP Learning Sandboxes across **IT Admins**, **BU / School Admins**, and **Students** (`IT Admin ⊃ BU Admin ⊃ Student`).

## Repository Structure

```text
learning-sandbox/
├── specs/
│   ├── SPEC-CONVENTIONS.md                        # Spec-Driven Design rules (WHAT/WHY/HOW, master + sub-*.md)
│   ├── 01-brs/                                    # BUSINESS REQUIREMENTS SPECIFICATION (BRS)
│   │   ├── brs-master.md                          # PRIMARY (WHAT): Business problem, 3 personas, folder/cohort/project
│   │   │                                          # organization, persona-to-level responsibility matrix & UX outline
│   │   ├── sub-it-admin-cuj.md                    # WHY: "As an IT Admin, I want to <Y> to accomplish <Z>"
│   │   ├── sub-it-admin-details.md                # HOW: Folder Terraform, Admin Group cascading, Pooled Folder Budgets, Locks
│   │   ├── sub-bu-admin-cuj.md                    # WHY: "As a BU Admin, I want to <Y> to accomplish <Z>"
│   │   ├── sub-bu-admin-details.md                # HOW: Cohort ⌈N/100⌉ sharding, Project Terraform services, Overrides, Teardown
│   │   ├── sub-student-cuj.md                     # WHY: "As a Student, I want to <Y> to accomplish <Z>"
│   │   └── sub-student-details.md                 # HOW: Atomic Create/Delete pipeline, 6-service usage rights, ClickOps handoff
│   │
│   ├── 02-technical-design.md                     # PRIMARY: Master Technical Design & Cross-Component Architecture
│   └── technical-design/                          # SECONDARY DOCS referenced by 02-technical-design.md (no number prefixes)
│       ├── bootstrap-spec.md                      # Central Control Tower Day-0 Setup
│       ├── data-spec.md                           # Firebase Schema (/environments/{live|simulate}/...)
│       ├── bff/
│       │   ├── bff-master-spec.md                 # Primary BFF Spec (references functional BFF sub-specs below)
│       │   ├── auth-and-persona-spec.md
│       │   ├── control-and-lock-engine-spec.md
│       │   ├── it-admin-bff-spec.md
│       │   ├── bu-admin-bff-spec.md
│       │   ├── directory-and-roster-bff-spec.md
│       │   └── student-sandbox-bff-spec.md
│       ├── ui/
│       │   ├── ui-master-spec.md                  # Primary UI Spec (references functional UI sub-specs below)
│       │   ├── lock-and-pipeline-drawer-ui-spec.md
│       │   ├── it-admin-canvas-ui-spec.md
│       │   ├── bu-admin-cohort-canvas-ui-spec.md
│       │   ├── project-drilldown-canvas-ui-spec.md
│       │   └── student-sandbox-canvas-ui-spec.md
│       ├── it-admin-pipeline-spec.md
│       ├── bu-admin-pipeline-spec.md
│       ├── atomic-pipeline-spec.md
│       └── agy-portal-guide-skill-spec.md
│
└── src/
    ├── terraform/
    │   ├── bootstrap/                             # Day-0 Control Tower project & root setup
    │   ├── itadmin/                               # School folders, dept sub-folders, BU admin groups & folder budgets
    │   └── buadmin/                               # Cohort folders, project shards, project services & budget overrides
    ├── bff/
    │   ├── core/                                  # Config, auth/persona resolver, lock engine & Firebase client
    │   ├── routers/                               # FastAPI routers (it_admin, bu_admin, directory_roster, student)
    │   └── pipelines/                             # Pipeline runners (it_terraform, bu_terraform, atomic)
    ├── ui/
    │   └── src/
    │       ├── components/shell/                  # Navbar, LockBanner, PipelineDrawer & SimControlBar
    │       └── features/                          # React Flow canvas views (it-canvas, bu-cohort-canvas, project-drilldown, student-canvas)
    └── agy-skill/                                 # Packaged SKILL.md user guide for the Self-Service Portal
```
