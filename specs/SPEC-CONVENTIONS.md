# Spec-Driven Design Conventions (`SPEC-CONVENTIONS.md`)

This document codifies the authoring, naming, and structural rules for all specifications in `learning-sandbox`.

---

## 1. Core Principles

1. **Spec-First Lifecycle (`specs/` $\rightarrow$ `src/`):**
   * Every feature, persona flow, infrastructure module, BFF endpoint, and UI view is specified and reviewed under `specs/` before implementation under `src/`.
2. **Iterative, File-by-File Review:**
   * Specifications are edited and reviewed **one by one** with bounded scope.
   * Before performing major structural reorganizations on an existing spec, keep a local backup in scratch storage.

---

## 2. Folder & File Naming Convention

Every specification tier lives in a **numbered folder** under `specs/` containing **one Master Document (`<tier>-master.md`)** and **un-numbered Secondary Documents prefixed with `sub-` (`sub-<topic>.md`)**:

```text
specs/
├── SPEC-CONVENTIONS.md                  # This reference guide
├── 01-brs/                              # Tier 01: Business Requirements Specification (BRS)
│   ├── brs-master.md                    # Primary Master Document (THE WHAT)
│   ├── sub-it-admin-cuj.md              # Secondary Document (THE WHY — Persona 1)
│   ├── sub-it-admin-details.md          # Secondary Document (THE HOW — Persona 1)
│   ├── sub-bu-admin-cuj.md              # Secondary Document (THE WHY — Persona 2)
│   ├── sub-bu-admin-details.md          # Secondary Document (THE HOW — Persona 2)
│   ├── sub-student-cuj.md               # Secondary Document (THE WHY — Persona 3)
│   └── sub-student-details.md           # Secondary Document (THE HOW — Persona 3)
└── ...
```

### Naming Rules
* **Folder Name:** `<NN>-<short-slug>/` (e.g., `01-brs/`).
* **Primary Document:** `<short-slug>-master.md` (e.g., `brs-master.md`). Never prefix files inside a numbered folder with numbers (`01-`, `02-`).
* **Secondary Documents:** `sub-<name>.md` (e.g., `sub-it-admin-cuj.md`, `sub-it-admin-details.md`). Every `sub-*.md` file must link back to its parent `*-master.md` at the top of the file.

---

## 3. Document Responsibility Split: `WHAT` vs. `WHY` vs. `HOW`

Within the Business Requirements Specification (`specs/01-brs/`), responsibilities are strictly partitioned across three document types:

### A. Primary Master Document — `brs-master.md` (`THE WHAT`)
Outlines **what** we are solving at the system and organizational level:
1. **The Business Problem:** Why existing approaches fail and what the platform solves.
2. **The Personas & Inheritance Hierarchy:** The three personas (`IT Admin ⊃ BU Admin ⊃ Student`) and how higher layers inherit lower layers' capabilities.
3. **Typical Organization of Folders & Projects in Context:** How Root, School Folders, Department Sub-folders, Cohort Folders, and `<cohort_slug>-pNN` Project Shards are organized in a real institution.
4. **Core Business Rules & Naming Conventions:** Deterministic slug rules, sharding caps, lifecycle timing (e.g., when Service Accounts are created), budget alert behavior, and unassigned/multi-cohort rules.
5. **Operating Level & Responsibility Matrix:** Which persona operates at which level of the hierarchy on what functional areas.
6. **Outline of the Functional Experience per Persona:** Crisp summary per persona with direct links to `sub-<persona>-cuj.md` (`WHY`) and `sub-<persona>-details.md` (`HOW`).

### B. Persona CUJ Documents — `sub-<persona>-cuj.md` (`THE WHY`)
Lists the persona-specific **Critical User Journeys (CUJs)** in user-story format:
> **As a** `<Persona>`,  
> **I want to** `<perform action Y>`,  
> **So that / to accomplish** `<business outcome Z>`.

Each CUJ states the **Business Inputs**, **Business Pre-conditions** (if any), and **Business Outcome** without burying the reader in Terraform or API syntax.

### C. Persona Details Documents — `sub-<persona>-details.md` (`THE HOW`)
Captures the secondary **non-business / technical implementation details** for that persona:
* Terraform directory boundaries (`src/terraform/itadmin`, `src/terraform/buadmin`) and state file isolation (`gs://...`).
* Compiled `.tfvars.json` input contracts and expected `terraform output -json` schemas.
* Specific GCP APIs enabled, IAM role bindings, usage-only permission boundaries, and `google_billing_budget` filter rules (`resource_ancestors` vs. `projects`).
* Single-action lock keys (`locks/...`) and pipeline execution sequences.

---

## 4. Strict Boundary Between Business Specs and UI / Canvas Specs

* **No Visual Canvas Mechanics in `01-brs/`:** All visual canvas behaviors (React Flow node rendering, drag-and-drop/click interactions, drawers, banners, color states, and layout mechanics) belong **exclusively in the UI specifications** (`ui-master-spec.md` and its `sub-*.md` documents), never in the Business Requirements Specification.
