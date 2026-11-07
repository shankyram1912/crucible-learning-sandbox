# Spec-Driven Design Conventions (`SPEC-CONVENTIONS.md`)

This document codifies the authoring, naming, and structural rules for all specifications in `learning-sandbox`.

---

## 1. Core Principles

1. **Spec-First Lifecycle (`specs/` $\rightarrow$ `src/`):**
   * Every feature, persona flow, infrastructure module, BFF endpoint, and UI view is specified and reviewed under `specs/` before implementation under `src/`.
2. **Iterative, File-by-File Review:**
   * Specifications are edited and reviewed **one by one** with bounded scope.
   * Only commit and push to Git when explicitly instructed by the user.

---

## 2. Folder & File Naming Convention (`01-brs` vs. `02-tdd`)

Every specification tier lives in a **numbered folder** under `specs/` containing **one Master Document (`<tier>-master.md`)** and **un-numbered Secondary Documents prefixed with `sub-` (`sub-<topic>.md`)**:

```text
specs/
├── SPEC-CONVENTIONS.md                  # This reference guide
├── 01-brs/                              # Tier 01: Business Requirements Specification (THE WHAT & THE WHY)
│   ├── brs-master.md                    # Primary Master Document (THE WHAT)
│   ├── sub-it-admin-cuj.md              # Secondary Document (THE WHY — Persona 1 CUJs)
│   ├── sub-bu-admin-cuj.md              # Secondary Document (THE WHY — Persona 2 CUJs)
│   └── sub-student-cuj.md               # Secondary Document (THE WHY — Persona 3 CUJs)
│
└── 02-tdd/                              # Tier 02: Technical Design & Low-Level Design (THE HOW / LLD)
    ├── tdd-master.md                    # Primary Master Document (Technical Architecture Index)
    ├── sub-it-admin-details.md          # Secondary LLD Document (THE HOW — Persona 1)
    ├── sub-bu-admin-details.md          # Secondary LLD Document (THE HOW — Persona 2)
    ├── sub-student-details.md           # Secondary LLD Document (THE HOW — Persona 3)
    └── ...                              # Component & UI Technical Specs
```

---

## 3. Document Responsibility Split: `01-brs` (`WHAT` & `WHY`) vs. `02-tdd` (`HOW` / `LLD`)

### A. `specs/01-brs/` — Business Requirements Specification (`WHAT` & `WHY` Only)
1. **Primary Master Document — `brs-master.md` (`THE WHAT`):**
   * Outlines the business problem being solved, the personas and cumulative inheritance hierarchy, the three-level configuration cascade (`Service Catalog Config` $\rightarrow$ `IT Admin Global Config` $\rightarrow$ `BU Admin Cohort Editable Elements`), the typical organization of folders/projects/students/apps, core business rules, and the responsibility matrix.
2. **Persona CUJ Documents — `sub-<persona>-cuj.md` (`THE WHY`):**
   * Lists the persona-specific **Critical User Journeys (CUJs)** in user-story format:
     > **As a** `<Persona>`,  
     > **I want to** `<perform action Y>`,  
     > **So that / to accomplish** `<business outcome Z>`.
   * States purely business inputs, pre-conditions, and business outcomes — keeping all low-level technical details out of `01-brs/`.

### B. `specs/02-tdd/` — Technical Design & Low-Level Design (`THE HOW` / `LLD`)
1. **Master Technical Design — `tdd-master.md`:**
   * Indexes the persona Low-Level Design (`sub-*-details.md`) and component technical specifications (`bootstrap`, `data`, `bff`, `ui`, `pipelines`).
2. **Persona Low-Level Design Documents — `sub-<persona>-details.md` (`THE HOW`):**
   * Captures the secondary non-business / technical implementation details per persona (JSON schemas, Terraform state paths and `.tfvars.json` contracts, IAM role bindings, billing budget filter rules, and single-action lock matrices).
3. **UI / Visual Canvas Specifications (`specs/02-tdd/ui/`):**
   * All Visual Canvas behaviors, React Flow node layouts, drawers, banners, and UI interactions belong strictly in `specs/02-tdd/ui/*`, never in `01-brs/`.
