# Spec-Driven Design Conventions (`SPEC-CONVENTIONS.md`)

This document codifies the authoring, naming, and structural rules for all specifications in `learning-sandbox`.

---

## 1. Core Principles

1. **Spec-First Lifecycle (`specs/` $\rightarrow$ `src/`):**
   * Every feature, persona flow, infrastructure module, API endpoint, and UI view is specified and reviewed under `specs/` before implementation under `src/`.
2. **Iterative, File-by-File Review:**
   * Specifications are edited and reviewed **one by one** with bounded scope.
   * Only commit and push to Git when explicitly instructed by the user.

---

## 2. Folder & File Naming Convention (`01-brs` vs. `02-tdd`)

Every specification tier lives in a **numbered folder** under `specs/` with a primary `<tier>-master.md` document:

* **Tier 01 (`specs/01-brs/`):** Flat tier with `brs-master.md` (`THE WHAT`) and persona CUJ documents `brs-<persona>-cuj.md` (`THE WHY`).
* **Tier 02 (`specs/02-tdd/`):** Domain-organized tier with `tdd-master.md` (`THE HOW`) and domain subfolders `tdd-<domain>/`, where each subfolder has its own `<folder>-master.md` and `<folder>-<topic>.md` specs:

```text
specs/
├── SPEC-CONVENTIONS.md                  # This reference guide
├── 01-brs/                              # Tier 01: Business Requirements Specification (THE WHAT & THE WHY)
│   ├── brs-master.md                    # Primary Master Document (THE WHAT)
│   ├── brs-it-admin-cuj.md              # Secondary Document (THE WHY — Persona 1 CUJs)
│   ├── brs-bu-admin-cuj.md              # Secondary Document (THE WHY — Persona 2 CUJs)
│   └── brs-student-cuj.md               # Secondary Document (THE WHY — Persona 3 CUJs)
│
└── 02-tdd/                              # Tier 02: Technical Design & Low-Level Design (THE HOW / LLD)
    ├── tdd-master.md                    # Primary Master Document (Technical Architecture & Domain Index)
    ├── tdd-data/                        # Data & Firestore Schema Domain (tdd-data-master.md + tdd-data-*.md)
    ├── tdd-apis/                        # FastAPI BFF & Operational API Domains (tdd-apis-master.md + tdd-apis-*.md)
    ├── tdd-iac/                         # Terraform Modules & State Domain (tdd-iac-master.md + tdd-iac-*.md)
    ├── tdd-pipelines/                   # Execution Pipelines & Simulation Engine (tdd-pipelines-master.md + tdd-pipelines-*.md)
    ├── tdd-skills/                      # Companion Agent Skills (tdd-skills-master.md + tdd-skills-*.md)
    └── tdd-uiux/                        # Visual Canvas & Portal UI/UX Domain
```

---

## 3. Document Responsibility Split: `01-brs` (`WHAT` & `WHY`) vs. `02-tdd` (`HOW` / `LLD`)

### A. `specs/01-brs/` — Business Requirements Specification (`WHAT` & `WHY` Only)
1. **Primary Master Document — `brs-master.md` (`THE WHAT`):**
   * Outlines the business problem being solved, the personas and cumulative inheritance hierarchy, the three-level configuration cascade (`Service Catalog Config` $\rightarrow$ `IT Admin Global Config` $\rightarrow$ `BU Admin Cohort Editable Elements`), the typical organization of folders/projects/students/apps, core business rules, and the responsibility matrix.
2. **Persona CUJ Documents — `brs-<persona>-cuj.md` (`THE WHY`):**
   * Lists the persona-specific **Critical User Journeys (CUJs)** in user-story format:
     > **As a** `<Persona>`,  
     > **I want to** `<perform action Y>`,  
     > **So that / to accomplish** `<business outcome Z>`.
   * States purely business inputs, pre-conditions, and business outcomes — keeping all low-level technical details out of `01-brs/`.

### B. `specs/02-tdd/` — Technical Design & Low-Level Design (`THE HOW` / `LLD`)
1. **Master Technical Design — `tdd-master.md`:**
   * Defines the end-to-end technical architecture, cross-domain data flow, API route-to-operational-domain matrix, and traceability back to `01-brs/`.
2. **Domain Subfolders (`tdd-data`, `tdd-apis`, `tdd-iac`, `tdd-pipelines`, `tdd-skills`, `tdd-uiux`):**
   * Each subfolder contains a `<folder>-master.md` overview and focused `<folder>-<topic>.md` low-level design specifications.
   * All Visual Canvas behaviors, React Flow node layouts, drawers, banners, and UI interactions belong strictly in `specs/02-tdd/tdd-uiux/*`, never in `01-brs/`.
