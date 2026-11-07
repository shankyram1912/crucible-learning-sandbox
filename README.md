# Learning Sandbox (`learning-sandbox`)

Visual Canvas & Multi-Tier Control Tower for managing GCP Learning Sandboxes across **IT Admins**, **BU / School & Cohort Admins**, and **Students** (`IT Admin ⊃ BU Admin [School Admin ⊃ Cohort Admin] ⊃ Student`).

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
│       ├── tdd-master.md                          # PRIMARY: Master Technical Design & Cross-Domain Architecture
│       ├── tdd-data/                              # Data & Firestore Schema Domain
│       │   ├── tdd-data-master.md
│       │   ├── tdd-data-catalog-and-config.md
│       │   ├── tdd-data-hierarchy-and-cohorts.md
│       │   └── tdd-data-students-and-apps.md
│       ├── tdd-apis/                              # FastAPI BFF & Operational API Domains (/api/v1/*)
│       │   ├── tdd-apis-master.md
│       │   ├── tdd-apis-routing-and-middleware.md
│       │   ├── tdd-apis-session.md
│       │   ├── tdd-apis-it-admin.md
│       │   ├── tdd-apis-bu-admin.md
│       │   └── tdd-apis-student.md
│       ├── tdd-iac/                               # Terraform Modules & GCS .tflock State Locking
│       │   ├── tdd-iac-master.md
│       │   ├── tdd-iac-bootstrap.md
│       │   ├── tdd-iac-itadmin-school.md
│       │   └── tdd-iac-buadmin-subfolder-and-cohort.md
│       ├── tdd-pipelines/                         # Async Execution Pipelines (Cloud Build TF & Atomic SDK)
│       │   ├── tdd-pipelines-master.md
│       │   ├── tdd-pipelines-cloud-build-terraform.md
│       │   └── tdd-pipelines-atomic-runner.md
│       ├── tdd-skills/                            # Companion Agent Skills
│       │   ├── tdd-skills-master.md
│       │   └── tdd-skills-agy-portal-guide.md
│       └── tdd-uiux/                              # Visual Canvas & Portal UI/UX (Empty — To Discuss Next)
│
└── src/
    ├── terraform/
    │   ├── bootstrap/                             # Day-0 Control Tower project & root setup
    │   ├── itadmin/                               # School folders, School admin IAM & pooled school budgets
    │   └── buadmin/                               # Sub-folders, Cohort folders, project shards & shared SQL
    ├── bff/
    │   ├── core/                                  # Config, auth/persona resolver & Firestore client
    │   ├── routers/                               # FastAPI routers (session, it_admin, bu_admin, student)
    │   └── pipelines/                             # Pipeline runners (cloud_build_terraform, atomic_runner)
    ├── ui/
    │   └── src/
    │       ├── components/shell/                  # Navbar & workspace shell
    │       └── features/                          # React Flow canvas views
    └── agy-skill/                                 # Packaged SKILL.md user guide for the Self-Service Portal
```
