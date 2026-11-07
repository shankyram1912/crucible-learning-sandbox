# Technical Design & Low-Level Design — Master (`THE HOW`)

> **Document Role:** Primary Technical Design & Low-Level Design (TDD / LLD) Document referencing un-numbered `sub-*.md` technical specifications.  
> **Companion Business Requirements Spec (`WHAT` & `WHY`):** [../01-brs/brs-master.md](../01-brs/brs-master.md)

---

## 1. Persona Low-Level Design Details (`THE HOW`)
* **Persona 1 — IT Admin LLD:** [sub-it-admin-details.md](sub-it-admin-details.md) *(Version-tracked Global Config schema, Top-Level School Folder Terraform, School Admin IAM bindings, Root/School Pooled Budgets & Locks)*
* **Persona 2 — BU Admin (School & Cohort Admin) LLD:** [sub-bu-admin-details.md](sub-bu-admin-details.md) *(Department Sub-folder & Cohort Terraform state isolation, Active Provisioning Project pointer, Cohort Student Email Group mapping, Non-destructive service toggles & Locks)*
* **Persona 3 — Student LLD:** [sub-student-details.md](sub-student-details.md) *(Just-in-time Student Workspace Initialization on Cohort entry, App-Level Containers `app-<app_slug>`, Atomic `CREATE`/`DELETE` matrix & Pooled Per-Student Allowance Gate)*

---

## 2. Platform & Component Technical Specifications
* **Bootstrap (Day-0 Control Tower Setup):** [bootstrap-spec.md](bootstrap-spec.md)
* **Data & Firebase Schema (`/environments/{live|simulate}/...`):** [data-spec.md](data-spec.md)
* **Backend-for-Frontend (FastAPI):** [bff/bff-master-spec.md](bff/bff-master-spec.md)
  * [bff/auth-and-persona-spec.md](bff/auth-and-persona-spec.md)
  * [bff/control-and-lock-engine-spec.md](bff/control-and-lock-engine-spec.md)
  * [bff/it-admin-bff-spec.md](bff/it-admin-bff-spec.md)
  * [bff/bu-admin-bff-spec.md](bff/bu-admin-bff-spec.md)
  * [bff/directory-and-roster-bff-spec.md](bff/directory-and-roster-bff-spec.md)
  * [bff/student-sandbox-bff-spec.md](bff/student-sandbox-bff-spec.md)
* **Visual Canvas UI (React Flow):** [ui/ui-master-spec.md](ui/ui-master-spec.md)
  * [ui/lock-and-pipeline-drawer-ui-spec.md](ui/lock-and-pipeline-drawer-ui-spec.md)
  * [ui/it-admin-canvas-ui-spec.md](ui/it-admin-canvas-ui-spec.md)
  * [ui/bu-admin-cohort-canvas-ui-spec.md](ui/bu-admin-cohort-canvas-ui-spec.md)
  * [ui/project-drilldown-canvas-ui-spec.md](ui/project-drilldown-canvas-ui-spec.md)
  * [ui/student-sandbox-canvas-ui-spec.md](ui/student-sandbox-canvas-ui-spec.md)
* **Execution Pipelines & Companion Skill:**
  * [it-admin-pipeline-spec.md](it-admin-pipeline-spec.md)
  * [bu-admin-pipeline-spec.md](bu-admin-pipeline-spec.md)
  * [atomic-pipeline-spec.md](atomic-pipeline-spec.md)
  * [agy-portal-guide-skill-spec.md](agy-portal-guide-skill-spec.md)
