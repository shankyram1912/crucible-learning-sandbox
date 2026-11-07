# Business Requirements Specification — Master (`THE WHAT`)

> **Document Role:** Primary Business Specification (*What business problem we solve, the three personas, how folders/cohorts/projects/apps are organized, who operates at each level, and the functional experience per persona*).  
> *(Note: Visual Canvas UI layout and interaction mechanics are specified separately in [ui-master-spec.md](../technical-design/ui/ui-master-spec.md).)*
>
> **Secondary Persona Documents (`WHY` & `HOW`):**
> * **Persona 1 — IT Admin:** [sub-it-admin-cuj.md](sub-it-admin-cuj.md) · [sub-it-admin-details.md](sub-it-admin-details.md)
> * **Persona 2 — BU Admin:** [sub-bu-admin-cuj.md](sub-bu-admin-cuj.md) · [sub-bu-admin-details.md](sub-bu-admin-details.md)
> * **Persona 3 — Student:** [sub-student-cuj.md](sub-student-cuj.md) · [sub-student-details.md](sub-student-details.md)

---

## 1. The Business Problem: Shared Cohort Projects & Pooled Budgets

Institutions running cloud and AI programs generally use two distinct sandbox models depending on learning goals:

1. **Dedicated Project per Student (Personal Flexible Learning):** Recommended when the goal is open-ended personal exploration with relaxed self-admin controls and a hard per-student project budget.
2. **Shared Cohort Project & Pooled Budget (What This Platform Solves):** When universities and enterprises run structured courses, labs, and hackathons for hundreds or thousands of students under **shared GCP projects and pooled folder/cohort budgets**, they hit three operational barriers:
   * **Shared-Project Isolation & IAM Challenge:** Placing up to 100 students into a shared GCP project with standard roles (`Editor` or broad service roles) allows students to see, overwrite, or delete each other's resources, exhaust shared budgets, or get blocked by `Permission Denied` errors on services where `create` and `list` are evaluated at the project level (such as Cloud Run and Vertex AI Search).
   * **The Central IT Bottleneck:** Central IT owns the Organization Root Folder and Cloud Billing Account, while Schools, Departments, and Faculty (Business Units) own the academic cohorts and student rosters. Requiring central IT intervention every time a cohort needs projects, shared databases, or student onboarding turns a 5-minute setup into a multi-day ticket queue.
   * **Multi-Assignment Organization for Students:** Within a shared project, a student often works on multiple labs or assignments over a term. Without a clean separation between **Student-Level Foundation Resources** (Identity, Bucket, Logical DB) and **App-Level Boundaries** (where students mix and match services like Cloud Run, Vertex AI Search, GCS Managed Folders, and DB Schemas within a per-student service quota), students either overwrite earlier labs or clutter the shared project.

### What the Learning Sandbox Solves
The **Learning Sandbox** provides a **Self-Service Portal** backed by a **Central Control Tower** for the **Shared Project & Pooled Budget** model, cleanly decoupling:
* **Organizational & Financial Governance (IT Admin)** from
* **Cohort Sizing, Project Shard Initialization & Student Mapping (BU Admin)** from
* **Two-Tier Student & App Sandbox Building (Student)** — where up to **100 students safely share a single GCP project shard** with pooled budgets, over-subscribable project limits, per-student resource caps, and zero state drift because **all resource creation and deletion happen exclusively through the portal**.

---

## 2. The Three Personas & Cumulative Inheritance Model

The platform is built around three personas arranged in a **strict cumulative inheritance hierarchy (`IT Admin ⊃ BU Admin ⊃ Student`)**: every higher layer automatically inherits 100% of the rights of all lower layers within its scope, plus its own layer's capabilities.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: IT ADMIN (Root & Organization Governance)                           │
│  • Own Capabilities:                                                         │
│    - Organize School Folders and Department Sub-folders under Root           │
│    - Map BU Admin IAM Groups to School Folders or Department Sub-folders     │
│    - Configure Billing Account associations and Pooled Folder Budgets        │
│    - Control system execution mode (LIVE vs. SIMULATE)                       │
│  • Inherited Capabilities: 100% of BU Admin + 100% of Student capabilities   │
├──────────────────────────────────────────────────────────────────────────────┤
│ LAYER 2: BU ADMIN (School / Department / Cohort Operator)                    │
│  • Own Capabilities:                                                         │
│    - Create Cohort Folders under their School Folder or Dept Sub-folder      │
│    - Initialize Cohort Project Shards (⌈N / 100⌉ projects) via Terraform     │
│    - Toggle which Project-Level Services & Per-Student Max Service Caps      │
│      are configured per Cohort/Project                                       │
│    - Set Default Project Spend Limits & Per-Project Spend Limit Overrides    │
│    - Map Cloud Identity Users / User Groups (or CSV rosters) to Cohorts      │
│      (automatically creating each mapped student's Service Account)          │
│    - Search for students across their folders/projects & Teardown Cohorts    │
│  • Inherited Capabilities: 100% of Student capabilities in their scope       │
├──────────────────────────────────────────────────────────────────────────────┤
│ LAYER 3: STUDENT (Sandbox Builder — Student Level + App Boundary)            │
│  • Student-Level Resources (1 per Student in a Project Shard):               │
│    - Auto-Created on Project Mapping:                                        │
│      • Gemini (Vertex AI access)                                             │
│      • Dedicated Service Account (sa-<student_slug>)                         │
│    - Self-Service at Student Level (Example Baseline Resources):             │
│      • Student GCS Bucket (bkt-<project_id>-<student_slug>)                  │
│      • Student Cloud SQL Logical DB (db_<student_slug> on shared SQL)        │
│  • App-Level Boundary (app-<app_slug> — Mix & Match up to Student Max Caps): │
│    - Example App-Scoped Resources (1..N per App within Student Max Quota):   │
│      1. Cloud Run Services (run-<student_slug>-<app_slug>-<svc>)             │
│      2. Vertex AI Search Data Stores & Apps                                  │
│         (search-ds-<student_slug>-<app_slug>-<name> &                        │
│          search-app-<student_slug>-<app_slug>-<name>)                        │
│      3. GCS Managed Folders under Student Bucket                             │
│         (gs://bkt-<project_id>-<student_slug>/apps/<app_slug>/<folder>/)     │
│      4. Postgres Schemas inside Student Logical DB                           │
│         (db_<student_slug>.<app_slug>_<schema>)                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

*(Note: The four service families — GCS, Vertex AI Search, Cloud SQL, and Cloud Run — represent the initial example catalog of self-service building blocks supported by the portal.)*

---

## 3. Typical Organization of Folders, Projects, Students & Apps

To mirror how universities and enterprises are structured — from Root down to School Folders, Department Sub-folders, Cohort Folders, Project Shards ($\le 100$ students/shard), Student Slices, and per-student Apps — the platform organizes resources as follows:

```text
[Root Sandbox Folder]                               <── IT Admin Scope (Root Pooled Budget)
 │
 ├── 🗼 Control Tower Project                        <── Hosts Portal UI, FastAPI BFF, Firebase DB,
 │                                                       TF State Bucket & Privileged sa-control-tower
 │
 ├── 🏛️ School Folder: Business School              <── IT Admin creates + maps Biz BU Admin Group
 │    │                                                 (Pooled School Folder Budget: $15,000)
 │    └── 🎓 Cohort Folder: mba-genai-fall          <── BU Admin creates Cohort (Size: 80 students)
 │         └── 📦 Project Shard: mba-genai-fall-p01 <── 1 Shard initialized (80 / 100 seats)
 │
 └── 🏛️ School Folder: College of Engineering       <── IT Admin creates + maps Dean BU Admin Group
      │                                                 (Pooled School Folder Budget: $40,000)
      └── 📂 Sub-folder: Computer Science           <── IT Admin creates + maps CS BU Admin Group
           │                                            (Pooled Sub-folder Budget: $25,000)
           └── 🎓 Cohort Folder: cs101-fall         <── BU Admin creates Cohort (Size: 350 students)
                │                                       (Pooled Cohort Folder Budget: $8,000)
                ├── 📦 Project Shard: cs101-fall-p01 <── 100 / 100 students · Limit: $3,000 (Default)
                ├── 📦 Project Shard: cs101-fall-p02 <── 100 / 100 students · Limit: $5,000 (Override ⚡)
                │    │
                │    └── 👤 Student Slice: alice-tan (alice.tan@school.edu)
                │         ├── [Student Level — 1 per Student]
                │         │    ├── ✨ Gemini (Active on mapping)
                │         │    ├── 🔑 Service Account: sa-alice-tan (Active on mapping)
                │         │    ├── 🪣 GCS Bucket: bkt-cs101-fall-p02-alice-tan
                │         │    └── 🗄️ Logical Postgres DB: db_alice_tan (on shared sql-cs101-fall-p02)
                │         │
                │         ├── 🚀 App: app-lab1 (Mix & match within Alice's per-student max service caps)
                │         │    ├── 📁 Managed Folder: gs://bkt-...-alice-tan/apps/lab1/rag-docs/
                │         │    ├── 🔎 Vertex Search: search-ds-alice-tan-lab1-docs & search-app-alice-tan-lab1-main
                │         │    ├── 🧩 DB Schema: db_alice_tan.lab1_core
                │         │    └── ☁️ Cloud Run: run-alice-tan-lab1-api
                │         │
                │         └── 🚀 App: app-capstone
                │              ├── 📁 Managed Folder: gs://bkt-...-alice-tan/apps/capstone/assets/
                │              ├── 🧩 DB Schemas: db_alice_tan.capstone_users, db_alice_tan.capstone_logs
                │              └── ☁️ Cloud Run: run-alice-tan-capstone-web, run-alice-tan-capstone-worker
                │
                ├── 📦 Project Shard: cs101-fall-p03 <── 100 / 100 students · Limit: $3,000 (Default)
                └── 📦 Project Shard: cs101-fall-p04 <──  50 / 100 students · Limit: $3,000 (Default)
```

---

## 4. Core Business Rules & Naming Conventions

1. **Naming Conventions:**
   * **Project Shard IDs:** Derived from the Cohort slug: `<cohort_slug>-p01`, `<cohort_slug>-p02`, ..., `<cohort_slug>-pNN`.
   * **Student Slug:** Derived from the email prefix before `@` (normalized to lowercase alphanumeric/hyphens, e.g., `alice.tan@school.edu` $\rightarrow$ `alice-tan`; SQL identifier uses underscores `alice_tan`).
   * **Student-Level Resources (1 per Student in a Project Shard):**
     * **Service Account** (auto-created when student is mapped to project): `sa-<student_slug>`
     * **Student GCS Bucket:** `bkt-<project_id>-<student_slug>`
     * **Student Cloud SQL Logical Database:** `db_<student_slug>` (on shared instance `sql-<project_id>`)
   * **App-Level Resources (`app-<app_slug>`, Mix & Match within Per-Student Max Service Caps):**
     * **Cloud Run Service:** `run-<student_slug>-<app_slug>-<svc>`
     * **Vertex AI Search Data Store & App:** `search-ds-<student_slug>-<app_slug>-<name>` and `search-app-<student_slug>-<app_slug>-<name>`
     * **GCS Managed Folder (under Student Bucket):** `gs://bkt-<project_id>-<student_slug>/apps/<app_slug>/<folder>/`
     * **Postgres Schema (inside Student Logical DB):** `db_<student_slug>.<app_slug>_<schema>`
2. **Per-Student Max Service Caps (Flexible Mix & Match Across Apps):**
   * Each Cohort defines **Max Services per Student** across the student's entire sandbox slice (for example: max `1` Student Bucket, max `1` Student Logical DB, max `N` Cloud Run services, max `D` Vertex AI Search Data Stores/Apps, max `F` GCS Managed Folders, max `S` DB Schemas per student).
   * Students can organize their resources into **1 or more Apps (`app-<app_slug>`)** and freely **mix and match** their per-student service allowance across those Apps as needed (e.g., placing 3 Cloud Run services into a single App, or 1 Cloud Run service across 3 separate Apps).
3. **Automatic Project Sharding ($\le 100$ Students per Project):** When a BU Admin specifies a Cohort size of $N$ students, the platform calculates $\lceil N / 100 \rceil$ Project Shards (`<cohort_slug>-p01..pNN`) and initializes them via Terraform using the Control Tower's privileged service account.
4. **Decoupled Cohort Initialization vs. Student Mapping:**
   * **Step 1 (Cohort Init):** Project Shards and shared project-level infrastructure (such as the Shared Cloud SQL instance) are initialized first via Terraform based on expected Cohort size.
   * **Step 2 (Student Mapping Later):** When the BU Admin maps Cloud Identity Users, User Groups, or a CSV roster to the Cohort, each student is assigned to a Project Shard ($\le 100$ students/shard) and their personal **Service Account (`sa-<student_slug>`)** and baseline **Gemini** access are provisioned automatically.
5. **Multi-Cohort & Unassigned User Rules:**
   * **Unassigned Users:** A logged-in user not mapped to any admin group or student cohort sees a **"No Sandbox Assigned"** state.
   * **Multi-Cohort Students:** A student enrolled in multiple Cohorts is mapped to a distinct Project Shard per Cohort and manages their Student Slice and Apps independently in each assigned Cohort project.
6. **Pooled Folder Budgets, Over-Subscribable Project Limits & Alert Behavior:**
   * **Folder Budgets** (`Root`, `School`, `Sub-folder`, `Cohort`) track actual pooled spend across all descendant projects.
   * **Project Shard Limits** default to an over-subscribable guardrail (absorbing uneven student usage across shards) and support **Per-Project Overrides**.
   * **Budget Exceeded Behavior:** Crossing `100%` of a Folder Budget or Project Shard Limit surfaces a **Red Budget Alert Banner** for that scope (visual alert without freezing active student resources).
7. **Portal-Only Create & Delete (Usage-Only Rights in GCP):**
   * Students create and delete their Student-level and App-level resources strictly through the Self-Service Portal.
   * In GCP, students receive **no IAM management privileges** (`setIamPolicy`) and **no top-level resource create/delete permissions** — only service-appropriate usage rights on their provisioned slice.
8. **Single-Action Workspace Locking & `LIVE`/`SIMULATE` Control Config:**
   * Every mutation acquires a scoped lock (`root`, `folder`, `cohort`, `project`, or `student`) so only one action executes at a time within that scope.
   * A central `control_config` toggles between `LIVE` and `SIMULATE` modes (isolating Firebase DB under `/environments/live/...` and `/environments/simulate/...`).

---

## 5. Operating Level & Responsibility Matrix by Persona

| Hierarchy Level | Functional Area | IT Admin | BU Admin | Student |
| :--- | :--- | :--- | :--- | :--- |
| **Root Sandbox Folder** | Control Tower, Billing Account Ref, Root Budget, `LIVE`/`SIMULATE` Config, School Folder Creation | **Owner (Full CRUD)** | — | — |
| **School Folder & Dept Sub-folder** | Sub-folder organization, BU Admin IAM Group mapping (cascading), Pooled Folder Budgets | **Owner (Full CRUD)** | **Scoped Operator** *(within mapped Folder/Sub-folder)* | — |
| **Cohort Folder** | Create Cohort Folder, size Cohort ($\rightarrow \lceil N/100 \rceil$ `<cohort_slug>-pNN` shards), set Per-Student Max Service Caps, map Cloud Identity Users/Groups, Cohort Budget, **Cohort Teardown** | *Inherited* | **Owner (Full CRUD)** | — |
| **Project Shard ($\le 100$ students)** | Initialize/toggle Project-Level Terraform Services (`Shared Cloud SQL`, `Vertex AI Search`, `Cloud Run`, `GCS`), set **Project Spend Limit Override**, Student Search | *Inherited* | **Owner (Full CRUD)** | — |
| **Student Level (1 per Student in Shard)** | Auto-provisioned `Gemini` + `sa-<student_slug>` (on project mapping); Self-service Create & Delete of `Student GCS Bucket` (`bkt-...`) and `Student Logical DB` (`db_<student_slug>`) | *Inherited* | *Inherited (Can act on behalf of student)* | **Owner (Portal Create/Delete + GCP Usage Rights)** |
| **App Boundary (`app-<app_slug>`)** | Create/delete Apps and mix & match App-scoped services (`Cloud Run`, `Vertex AI Search Data Stores/Apps`, `GCS Managed Folders`, `DB Schemas`) within Per-Student Max Service Caps | *Inherited* | *Inherited (Can act on behalf of student)* | **Owner (Portal Create/Delete + GCP Usage Rights)** |

---

## 6. Outline of the Functional Experience per Persona

* **Persona 1 — IT Admin:** Operates at the Root, School Folder, and Department Sub-folder level to establish the organizational tree, map cascading BU Admin IAM Groups, and manage Pooled Folder Budgets, with full inherited drilldown into BU Admin and Student scopes.
  * **WHY (User Journeys):** [sub-it-admin-cuj.md](sub-it-admin-cuj.md)
  * **HOW (Implementation Details):** [sub-it-admin-details.md](sub-it-admin-details.md)
* **Persona 2 — BU Admin:** Operates within their mapped School Folder or Department Sub-folder to create Cohort Folders, initialize $\lceil N/100 \rceil$ `<cohort_slug>-pNN` Project Shards via Terraform, configure project-level services, per-student max service caps, and budget overrides, map Cloud Identity users/groups (which initializes student Service Accounts), search students, and teardown completed cohorts.
  * **WHY (User Journeys):** [sub-bu-admin-cuj.md](sub-bu-admin-cuj.md)
  * **HOW (Implementation Details):** [sub-bu-admin-details.md](sub-bu-admin-details.md)
* **Persona 3 — Student:** Operates within their assigned Cohort Project Shard(s) with **Gemini** and **`sa-<student_slug>`** active out of the box, manages their Student-level **GCS Bucket** and **Cloud SQL Logical DB**, and creates **Apps (`app-<app_slug>`)** where they freely mix and match **Cloud Run services**, **Vertex AI Search Data Stores & Apps** (`search-ds-...`, `search-app-...`), **GCS Managed Folders**, and **Postgres Schemas** within their per-student max service caps.
  * **WHY (User Journeys):** [sub-student-cuj.md](sub-student-cuj.md)
  * **HOW (Implementation Details):** [sub-student-details.md](sub-student-details.md)
