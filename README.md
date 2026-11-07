# Learning Sandbox (`learning-sandbox`)

Visual Canvas & Multi-Tier Control Tower for managing GCP Learning Sandboxes across **IT Admins**, **BU / School Admins**, and **Students** (`IT Admin ⊃ BU Admin ⊃ Student`).

## Repository Structure

```text
learning-sandbox/
├── specs/
│   ├── SPEC-CONVENTIONS.md                        # Spec-Driven Design rules (01-brs WHAT/WHY vs. 02-tdd HOW/LLD)
│   ├── 01-brs/                                    # BUSINESS REQUIREMENTS SPECIFICATION (THE WHAT & THE WHY)
│   │   ├── brs-master.md                          # PRIMARY (WHAT): Business problem, 3 personas, folder/cohort/project
│   │   │                                          # organization, persona-to-level responsibility matrix & UX outline
│   │   ├── brs-it-admin-cuj.md                    # WHY: "As an IT Admin, I want to <Y> to accomplish <Z>"
│   │   ├── brs-bu-admin-cuj.md                    # WHY: "As a BU Admin (School/Cohort), I want to <Y> to accomplish <Z>"
│   │   └── brs-student-cuj.md                     # WHY: "As a Student, I want to <Y> to accomplish <Z>"
│   │
│   └── 02-tdd/                                    # TECHNICAL DESIGN & LOW-LEVEL DESIGN (THE HOW / LLD)
│       ├── tdd-master.md                          # PRIMARY: Master Technical Design & Cross-Component Architecture
│       ├── sub-it-admin-details.md                # HOW (LLD): Versioned Config JSON, School Folder Terraform, Budgets, Locks
│       ├── sub-bu-admin-details.md                # HOW (LLD): Sub-folder & Cohort Terraform, Active Provisioning Shard, Locks
│       ├── sub-student-details.md                 # HOW (LLD): JIT Student Workspace Init, App Containers, Atomic Pipeline, Locks
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
