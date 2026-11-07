# Business Requirements Specification — Master (`THE WHAT`)

> **Document Role:** Primary Business Specification (*What business problem we solve, the three personas, how folders/cohorts/projects/apps are organized, the config-driven service inheritance model, who operates at each level, and the functional experience per persona*).  
> *(Note: Visual Canvas UI layout and interaction mechanics are specified separately in [ui-master-spec.md](../02-tdd/ui/ui-master-spec.md).)*
>
> **Secondary Persona Documents (`WHY` & `HOW`):**
> * **Persona 1 — IT Admin:** [brs-it-admin-cuj.md](brs-it-admin-cuj.md) · [../02-tdd/sub-it-admin-details.md](../02-tdd/sub-it-admin-details.md)
> * **Persona 2 — BU Admin (School Admin & Cohort Admin):** [brs-bu-admin-cuj.md](brs-bu-admin-cuj.md) · [../02-tdd/sub-bu-admin-details.md](../02-tdd/sub-bu-admin-details.md)
> * **Persona 3 — Student:** [brs-student-cuj.md](brs-student-cuj.md) · [../02-tdd/sub-student-details.md](../02-tdd/sub-student-details.md)

---

## 1. The Business Problem: Shared Cohort Projects & Pooled Budgets

Institutions running cloud and AI programs generally use two distinct sandbox models depending on learning goals:

1. **Dedicated Project per Student (Personal Flexible Learning):** Recommended when the goal is open-ended personal exploration with more relaxed self-admin controls and a hard per-student project budget.
2. **Shared Cohort Project & Pooled Budget (What This Platform Solves):** When universities and enterprises run structured courses, labs, and hackathons for hundreds or thousands of students under **shared GCP projects and pooled folder/cohort budgets**, they hit three operational barriers:
   * **Shared-Project Isolation & IAM Challenge:** Placing multiple students into a shared GCP project with standard roles (`Editor` or broad service roles) allows students to see, overwrite, or delete each other's resources, exhaust shared budgets, or get blocked by `Permission Denied` errors on services where `create` and `list` are evaluated at the project level (such as Cloud Run and Vertex AI Search).
   * **The Central IT Bottleneck:** Central IT owns the Organization Root Folder, Cloud Billing Account, and global platform guardrails, while Schools, Departments, and Faculty (Business Units) own the academic cohorts and student rosters. Requiring central IT intervention every time a cohort needs projects, shared databases, or student onboarding turns a 5-minute setup into a multi-day ticket queue.
   * **Multi Cohort & Multi App Level Services:** A student may belong to multiple Cohorts simultaneously and build multiple labs or applications over a term within each Cohort. Without a clear separation between **Student-Level Singletons** (`1` Service Account, `1` Bucket, `1` Logical DB, plus Gemini access — if enabled on the cohort) and **App-Level Containers (`app-<app_slug>`)** where students mix and match services within their per-student allowance and are allowed to delete app-specific services to free up and reuse capacity, students either overwrite earlier work or clutter the shared project.

### What the Learning Sandbox Solves
The **Learning Sandbox** provides a **Self-Service Portal** backed by a **Central Control Tower** for the **Shared Project & Pooled Budget** model, cleanly decoupling:
* **Organizational, Financial & Global Service Catalog Governance (IT Admin)** from
* **School Sub-folder Organization, Cohort Sizing, Active Provisioning Project Selection & Email Group Mapping (BU Admin — School & Cohort Admins)** from
* **Just-in-Time Student Initialization & App Container Building (Student)** — where **100 students by default safely share a single GCP project shard**, students auto-initialize their Student-Level Singletons upon first entering a Cohort workspace, and **all resource creation and deletion happen exclusively through the portal**.

---

## 2. The Three Personas & Cumulative Inheritance Model

The platform is built around three personas arranged in a **strict cumulative inheritance hierarchy (`IT Admin ⊃ BU Admin [School Admin ⊃ Cohort Admin] ⊃ Student`)**: every higher layer automatically inherits 100% of the rights of all lower layers within its scope, plus its own layer's capabilities. **All BU Admins are by default Cohort Admins** across their delegated scope.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: IT ADMIN (Root, Global Config & Top-Level School Onboarding)        │
│  • Own Capabilities:                                                         │
│    - Manage Version-Tracked Global Platform Config (from Service Catalog):   │
│      • Default Students per Project Shard (Default: 100 students/project)    │
│      • Default Enabled Services (SA [Mandatory], Gemini, GCS, Cloud SQL,     │
│        Cloud Run, Vertex AI Search, etc.) & Prerequisite Mappings            │
│      • Per-Service Sizes (e.g., Cloud SQL tier, Cloud Run CPU/memory) AND    │
│        Service Quota Defaults (Min) & Max                                    │
│    - Create Top-Level School Folders under Root Sandbox Folder               │
│    - Assign Top-Level School Admins (Users/Groups) to School Folders         │
│    - Configure Billing Account associations and Root / School Pooled Budgets │
│    - Control system execution mode (LIVE vs. SIMULATE)                       │
│  • Inherited Capabilities: 100% of BU Admin (School + Cohort) + Student      │
├──────────────────────────────────────────────────────────────────────────────┤
│ LAYER 2: BU ADMIN (All BU Admins Are by Default Cohort Admins)               │
│  • 2A. School Admin (Assigned by IT Admin at Top-Level School Folder):       │
│    - Create, update & decommission Department Sub-folders under their School │
│    - Allocate Pooled Sub-folder & Cohort Budgets within their School         │
│    - Assign additional Cohort Admins at the Sub-folder or Cohort level       │
│    - By default is a Cohort Admin across the entire School Folder            │
│  • 2B. Cohort Admin (Default for all BU Admins, or scoped to Sub-folder/     │
│        Cohort):                                                              │
│    - Create Cohort Folders & configure Cohort Editable Elements:             │
│      • Cohort Student Size (N) & Students per Project (Default: 100)         │
│        ──> Initializes ⌈N / 100⌉ Project Shards (<cohort_slug>-p01..pNN)     │
│      • Maintain & switch the Cohort's Current Active Provisioning Project    │
│        (based on remaining shard capacity, or manually switched by admin)    │
│      • Services Enabled on Cohort (SA is Mandatory; optional services        │
│        enforce prerequisites; non-destructive disable)                       │
│      • Per-Service Per-Student Quantity (takes Min from Service Catalog      │
│        Config by default + Cohort Override; non-destructive reduction)       │
│      • Pooled Cohort Budget, Default Project Limit & Per-Project Overrides   │
│    - Map Cohort Student Email Group(s) to the Cohort                         │
│    - Suspend a Student or Delete a Student Slice                             │
│    - Search for students across their scope & Teardown Cohorts               │
│  • Inherited Capabilities: 100% of Student capabilities in their scope       │
├──────────────────────────────────────────────────────────────────────────────┤
│ LAYER 3: STUDENT (JIT Workspace Initialization + App-Level Containers)       │
│  • Login & Cohort Selection (via Cohort Student Email Group Membership):     │
│    - Selects an assigned Cohort -> enters Cohort Workspace                   │
│    - Platform checks if Student Slice is initialized; if not, automatically  │
│      initializes Student-Level Singletons in the Cohort's Current Active     │
│      Provisioning Project Shard (<cohort_slug>-pNN)                          │
│    - Once initialized, App Container creation is enabled!                    │
│  • Student-Level Singletons (Max 1 per Student, if Service Enabled on Cohort)│
│    - 1 Service Account: sa-<student_slug> (Mandatory — always created)       │
│    - Gemini Access (if Gemini enabled)                                       │
│    - 1 Student GCS Bucket: bkt-<project_id>-<student_slug> (if GCS enabled)  │
│    - 1 Student Logical DB: db_<student_slug> on sql-<project_id> (if SQL on) │
│  • App-Level Containers (app-<app_slug> — Mix, Match & Delete App Services): │
│    - Example App-Scoped Building Blocks (1..N across Apps within Allowance): │
│      1. GCS Managed Folders under Student Bucket (Unlimited: ∞)              │
│         (gs://bkt-<project_id>-<student_slug>/apps/<app_slug>/<folder>/)     │
│      2. Postgres Schemas inside Student Logical DB (Min + Cohort Override)   │
│         (db_<student_slug>.<app_slug>_<schema>)                              │
│      3. Cloud Run Services (Min + Cohort Override)                           │
│         (run-<student_slug>-<app_slug>-<svc>)                                │
│      4. Vertex AI Search Data Stores & Apps (Min + Cohort Override)          │
│         (search-ds-<student_slug>-<app_slug>-<name> &                        │
│          search-app-<student_slug>-<app_slug>-<name>)                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

*(Note: The services above — Service Account, Gemini, GCS, Cloud SQL, Cloud Run, and Vertex AI Search — represent the initial example catalog loaded from the platform's Service Catalog Config.)*

---

## 3. Config-Driven Service Catalog, IT Admin Config & Cohort Editable Elements

Rather than hardcoding service lists or per-student quantities, the platform uses a **three-level configuration cascade**:

```text
[1. Platform Service Catalog Config]
 │  Defines the list of supported services and three core configuration dimensions:
 │    1. Requirement & Prerequisite Mapping:
 │       • requirement: MANDATORY vs. OPTIONAL (Service Account is MANDATORY and
 │         can never be disabled at IT Admin or Cohort level)
 │       • prerequisites: required parent services (e.g., Vertex AI Search requires
 │         GCS + Service Account)
 │    2. Service Sizes & Underlying Settings (e.g., Cloud SQL instance tier/size,
 │       Cloud Run CPU/memory sizing, API lists)
 │    3. Service Quota Defaults (Min / Default per student) and Max Ceilings
 ▼
[2. IT Admin Global Config Screen (Version-Tracked)]
 │  • Loads the Service Catalog Config and sets institution-wide defaults:
 │    - Default Students per Project Shard: S_shard = 100 (always defaults to 100)
 │    - Default Enabled Services for new Cohorts (SA is MANDATORY and locked ON;
 │      optional services enforce prerequisite mappings)
 │    - Service Sizes & Service Quota Defaults (Min) / Max (with override allowed)
 │  • Configurations are version-tracked (previous versions can be viewed;
 │    existing Cohorts are unaffected when a new config version is saved).
 ▼
[3. BU Admin Cohort Editable Elements (Inherited from IT Admin Config)]
    • Cohort Sizing & Active Provisioning Project:
      - Expected Students (N) & Students per Project (S_shard, default 100)
      - Project Shards Initialized: K = ⌈N / S_shard⌉ (<cohort_slug>-p01..pKK)
      - Current Active Provisioning Project (active_provisioning_project_id):
        Tracks which shard new students are initialized into based on remaining
        capacity (< 100 seats), and can be switched manually by the Cohort Admin.
    • Enabled Services Toggle: Toggle which optional services are enabled for this Cohort
      (Service Account is MANDATORY and cannot be disabled; enabling a service
      automatically enables its prerequisites from the Service Catalog Config).
      ──> Disabling a previously enabled optional service is non-destructive (blocks
          new provisioning without deleting existing student resources).
    • Per-Service Per-Student Quantity (for each enabled service):
      - Takes Min Quantity (m_service) from Service Catalog Config by default
      - Allows BU Admin Override at the Cohort level
      - Lowering the quantity is non-destructive (existing student resources
        deployed in excess of the new quantity remain unaffected).
```

### Cohort Editable Elements Reference

| Service (From Catalog Config) | Requirement & Prerequisites (From Catalog Config) | Cohort Enable Toggle | Student-Level Singleton *(Auto-Initialized on Student Cohort Entry, 1 per Student if Enabled)* | App-Level Building Block (`app-<app_slug>`, Atomic Pipeline) | Per-Student Quantity (`Min` from Catalog + Cohort Override) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Service Account** | **MANDATORY** *(Prerequisites: None)* | **Always Enabled (Cannot be disabled)** | `1` SA (`sa-<student_slug>`) | Bound as runtime identity across Student's Apps | Fixed Singleton (`1` per student) |
| **Gemini (Vertex AI)** | **OPTIONAL** *(Requires: `Service Account`)* | Enabled by default | Project + `sa-<student_slug>` Gemini access | Called by Student's Apps & IDE | Enabled / Disabled per Cohort |
| **GCS** | **OPTIONAL** *(Requires: `Service Account`)* | Enabled by default | `1` Bucket (`bkt-<project_id>-<student_slug>`) | **GCS Managed Folders** (`apps/<app_slug>/<folder>/`) | Bucket: `1` per student<br>Managed Folders: **Unlimited (`∞`)** |
| **Cloud SQL** | **OPTIONAL** *(Requires: `Service Account`)* | Configurable default | `1` Logical DB (`db_<student_slug>`) on shared `sql-<project_id>` | **Postgres Schemas** (`db_<student_slug>.<app_slug>_<schema>`) | Logical DB: `1` per student<br>Schemas: Takes **`min`** from Service Catalog Config; **override** allowed on Cohort |
| **Cloud Run** | **OPTIONAL** *(Requires: `Service Account`)* | Enabled by default | *(Uses `sa-<student_slug>`)* | **Cloud Run Services** (`run-<student_slug>-<app_slug>-<svc>`) | Takes **`min`** from Service Catalog Config; **override** allowed on Cohort |
| **Vertex AI Search** | **OPTIONAL** *(Requires: `Service Account`, `GCS`)* | Enabled by default | *(Uses `sa-<student_slug>` + `bkt-...`)* | **Search Data Stores & Apps** (`search-ds-...` & `search-app-...`) | Takes **`min`** from Service Catalog Config; **override** allowed on Cohort |

* **Flexible Mix & Match Across Apps:** A student's configured per-student quantity is a **pooled allowance across all App Containers (`app-<app_slug>`) created by that student** in that Cohort project.

---

## 4. Typical Organization of Folders, Projects, Students & Apps

```text
[Root Sandbox Folder]                               <── IT Admin Scope (Root Pooled Budget + Global Config)
 │
 ├── 🗼 Control Tower Project                        <── Hosts Portal UI, FastAPI BFF, Firebase DB,
 │                                                       Service Catalog Config, TF State & sa-control-tower
 │
 ├── 🏛️ School Folder: Business School              <── IT Admin creates + assigns Top-Level School Admin
 │    │                                                 (Pooled School Folder Budget: $15,000)
 │    └── 🎓 Cohort Folder: mba-genai-fall          <── School Admin (Cohort Admin by default) creates Cohort
 │         └── 📦 Project Shard: mba-genai-fall-p01 <── Active Provisioning Project (80 / 100 seats)
 │
 └── 🏛️ School Folder: College of Engineering       <── IT Admin creates + assigns Top-Level School Admin
      │                                                 (Pooled School Folder Budget: $40,000)
      └── 📂 Sub-folder: Computer Science           <── School Admin creates Sub-folder + assigns Cohort Admin
           │                                            (Pooled Sub-folder Budget: $25,000)
           └── 🎓 Cohort Folder: cs101-fall         <── Cohort Admin creates Cohort (Size: 350, Default 100/project)
                │                                       • Student Email Group: grp-cs101-students@school.edu
                │                                       • Current Active Provisioning Project: cs101-fall-p02 🎯
                │                                       • Pooled Cohort Folder Budget: $8,000
                ├── 📦 Project Shard: cs101-fall-p01 <── 100 / 100 students (Full) · Limit: $3,000 (Default)
                ├── 📦 Project Shard: cs101-fall-p02 <──  42 / 100 students (Active Target 🎯) · Limit: $5,000 (Override ⚡)
                │    │
                │    └── 👤 Student Slice: alice-tan (Auto-initialized when Alice entered cs101-fall workspace)
                │         ├── [Student-Level Singletons — Auto-initialized on Cohort entry]
                │         │    ├── 🔑 Service Account (1 - Mandatory): sa-alice-tan
                │         │    ├── ✨ Gemini (Enabled)
                │         │    ├── 🪣 Student Bucket (1): bkt-cs101-fall-p02-alice-tan
                │         │    └── 🗄️ Student Logical DB (1): db_alice_tan (on shared sql-cs101-fall-p02)
                │         │
                │         ├── 🚀 App Container: app-lab1 (Enabled once Student Slice is initialized)
                │         │    ├── 📁 Managed Folder (∞): gs://bkt-...-alice-tan/apps/lab1/rag-docs/
                │         │    ├── 🔎 Vertex Search: search-ds-alice-tan-lab1-docs & search-app-alice-tan-lab1-main
                │         │    ├── 🧩 DB Schema: db_alice_tan.lab1_core
                │         │    └── ☁️ Cloud Run: run-alice-tan-lab1-api
                │         │
                │         └── 🚀 App Container: app-capstone
                │              ├── 📁 Managed Folder (∞): gs://bkt-...-alice-tan/apps/capstone/assets/
                │              ├── 🧩 DB Schemas: db_alice_tan.capstone_users, db_alice_tan.capstone_logs
                │              └── ☁️ Cloud Run: run-alice-tan-capstone-web, run-alice-tan-capstone-worker
                │
                ├── 📦 Project Shard: cs101-fall-p03 <──   0 / 100 students (Standby) · Limit: $3,000 (Default)
                └── 📦 Project Shard: cs101-fall-p04 <──   0 / 100 students (Standby) · Limit: $3,000 (Default)
```

---

## 5. Core Business Rules & Naming Conventions

1. **Deterministic Naming Conventions (Single-Domain Institution):**
   * **Project Shard IDs:** Derived from the Cohort slug: `<cohort_slug>-p01`, `<cohort_slug>-p02`, ..., `<cohort_slug>-pNN`.
   * **Student Slug (Globally Unique in Single Domain):** Derived from the email prefix before `@` (normalized to lowercase alphanumeric/hyphens, e.g., `alice.tan@school.edu` $\rightarrow$ `alice-tan`; SQL identifier uses underscores `alice_tan`).
   * **Student-Level Singletons (Max 1 per Student in a Project Shard, if enabled on Cohort):**
     * **Service Account (Mandatory — always enabled):** `sa-<student_slug>`
     * **Student GCS Bucket:** `bkt-<project_id>-<student_slug>`
     * **Student Cloud SQL Logical Database:** `db_<student_slug>` (on shared instance `sql-<project_id>`)
   * **App-Level Resources (`app-<app_slug>`, Mix & Match within Per-Student Allowance):**
     * **GCS Managed Folder (Unlimited):** `gs://bkt-<project_id>-<student_slug>/apps/<app_slug>/<folder>/`
     * **Postgres Schema:** `db_<student_slug>.<app_slug>_<schema>`
     * **Cloud Run Service:** `run-<student_slug>-<app_slug>-<svc>`
     * **Vertex AI Search Data Store & App:** `search-ds-<student_slug>-<app_slug>-<name>` and `search-app-<student_slug>-<app_slug>-<name>`
2. **Default 100 Students per Project Shard & Active Provisioning Project Pointer:**
   * The IT Admin Config sets the default sharding density to **`100` students per project**, which all Cohorts inherit by default ($K = \lceil N / 100 \rceil$ Project Shards `<cohort_slug>-p01..pKK` initialized via Cohort Terraform).
   * Each Cohort maintains a **Current Active Provisioning Project (`active_provisioning_project_id`)** pointer based on remaining shard capacity (`< 100` initialized students). When the active shard reaches capacity, the pointer automatically advances to the next shard with available capacity — and **can also be manually switched at any time by the Cohort Admin**.
3. **Cohort Email Group Mapping & Just-in-Time Student Workspace Initialization:**
   * **Step 1 (Cohort Init & Email Group Mapping):** The Cohort Admin initializes the Cohort's `<cohort_slug>-p01..pKK` Project Shards and shared project-level infrastructure (e.g., Shared Cloud SQL instance) via Cohort Terraform (`src/terraform/buadmin`), and maps the **Cohort Student Email Group** (`grp-students-<cohort_slug>@domain.edu`) to the Cohort.
   * **Step 2 (Student Login & Auto-Initialize on Cohort Entry):** When a student logs in, they see the Cohort(s) corresponding to the Cohort Student Email Groups they belong to. When the student enters a Cohort workspace, the platform checks whether their Student Slice has been initialized (or if any newly enabled Cohort singleton is missing):
     * **If not initialized:** The platform assigns the student to the Cohort's `active_provisioning_project_id` and automatically initializes their enabled **Student-Level Singletons** (`1` mandatory `sa-<student_slug>`, `Gemini` access, `1` `bkt-<project_id>-<student_slug>`, `1` `db_<student_slug>`).
     * **Once initialized:** **App Container (`app-<app_slug>`) creation is enabled** for the student.
   * **Step 3 (Student Offboarding — Suspend Student vs. Delete Student Slice):**
     * **Suspend Student:** Revokes `user:<student_email>` access and locks/hides the Cohort workspace while preserving their Student-Level Singletons and App Containers.
     * **Delete Student Slice:** Tears down all of the student's App Containers and Student-Level Singletons in that Cohort and frees their seat in the project shard.
4. **Non-Destructive Service Disable & Quantity Reduction (Grandfathering Rule):**
   * **Disabling an Enabled Optional Service on a Cohort:** Underlying student services and project foundations already provisioned are **never deleted**; disabling only blocks new provisioning going forward.
   * **Changing / Lowering Per-Student Quantity on a Cohort:** Underlying student services already deployed in excess of the new quantity are **not affected or deleted**; lowering only gates new creation requests (`deployed_count < current_allowance`).
5. **Multi-Cohort & Unassigned User Rules:**
   * **Unassigned Users:** A logged-in user who is not in any admin group or Cohort Student Email Group sees a **"No Sandbox Assigned"** state.
   * **Multi-Cohort Students:** A student in multiple Cohort Student Email Groups can select and enter each Cohort workspace independently.
6. **Pooled Folder Budgets, Over-Subscribable Project Limits & Alert Behavior:**
   * **Folder Budgets** (`Root`, `School`, `Sub-folder`, `Cohort`) track actual pooled spend across all descendant projects.
   * **Project Shard Limits** default to an over-subscribable guardrail and support **Per-Project Overrides**.
   * **Budget Exceeded Behavior:** Crossing `100%` of a Folder Budget or Project Shard Limit surfaces a **Red Budget Alert Banner** for that scope (visual alert without freezing active student resources).
7. **Portal-Only Create & Delete (Usage-Only Rights in GCP):**
   * Students create and delete their App Containers and App-specific resources strictly through the Self-Service Portal.
   * In GCP, students receive **no IAM management privileges** (`setIamPolicy`) and **no top-level resource create/delete permissions** — only service-appropriate usage rights on their provisioned slice.
8. **Single-Action Workspace Locking & `LIVE`/`SIMULATE` Control Config:**
   * Every mutation acquires a scoped lock (`root`, `school`, `subfolder`, `cohort`, or `student`) so only one action executes at a time within that scope.
   * A central `control_config` toggles between `LIVE` and `SIMULATE` modes (isolating Firebase DB under `/environments/live/...` and `/environments/simulate/...`).

---

## 6. Operating Level & Responsibility Matrix by Persona

| Hierarchy Level | Functional Area | IT Admin | BU Admin *(All BU Admins Are Cohort Admins by Default)* | Student |
| :--- | :--- | :--- | :--- | :--- |
| **Root Sandbox Folder & Global Config** | Control Tower, Version-Tracked Service Catalog & Global Default Config (default `100` students/project, mandatory `SA`, prerequisite mappings, service sizes & quota `min`/`max`), Billing Account Ref, Root Budget, `LIVE`/`SIMULATE` Config | **Owner (Full CRUD)** | — | — |
| **Top-Level School Folder** | Create School Folder, assign **Top-Level School Admins**, set Pooled School Folder Budget | **Owner (Full CRUD)** | **School Admin (Scoped Owner)** | — |
| **Department Sub-folder** | Create/update/decommission Sub-folder under School Folder, assign additional **Cohort Admins** at Sub-folder level, set Pooled Sub-folder Budget | *Inherited* | **School Admin (Full CRUD)** · **Cohort Admin (Scoped Operator)** | — |
| **Cohort Folder** | Create/manage Cohort Folder, edit Cohort Settings (Student Size $N \rightarrow \lceil N/100 \rceil$ shards, **Current Active Provisioning Project** selection, Enabled Services, Per-Student Quantity taking `min` from Catalog with Cohort override; non-destructive disable/reduction), map **Cohort Student Email Group**, Suspend/Delete Student Slice, Cohort Budget, **Cohort Teardown** | *Inherited* | **School Admin & Cohort Admin (Owner)** | — |
| **Project Shard ($\le 100$ students)** | Initialize/toggle Project-Level Terraform Services (`Shared Cloud SQL`, `Vertex AI Search`, `Cloud Run`, `GCS`, `SA`, `Gemini`), switch **Active Provisioning Project**, set **Project Spend Limit Override**, Student Search | *Inherited* | **School Admin & Cohort Admin (Owner)** | — |
| **Student Level (Singletons per Student)** | Auto-initialized into the Cohort's `active_provisioning_project_id` when Student first enters Cohort workspace: `1` mandatory `sa-<student_slug>`, `Gemini`, `1` `bkt-...`, and `1` `db_<student_slug>` | *Inherited* | *Inherited (Can act on behalf of student)* | **Auto-Initialized on Entry + Usage Rights in GCP** |
| **App Container (`app-<app_slug>`)** | Enabled once Student Slice is initialized; Self-service Create & Delete of App Containers and App-specific services (`GCS Managed Folders` [$\infty$], `DB Schemas`, `Cloud Run Services`, `Vertex AI Search Data Stores & Apps`) within Cohort's Per-Student Quantity | *Inherited* | *Inherited (Can act on behalf of student)* | **Owner (Portal Create/Delete + GCP Usage Rights)** |

---

## 7. Outline of the Functional Experience per Persona

* **Persona 1 — IT Admin:** Operates at the Root, Global Config, and Top-Level School Folder level to configure version-tracked global service defaults (`100` students/project, mandatory `SA`, prerequisite mappings, service sizes, and quota `min`/`max`), create Top-Level School Folders, assign Top-Level School Admins, and manage Root/School Pooled Budgets.
  * **WHY (User Journeys):** [brs-it-admin-cuj.md](brs-it-admin-cuj.md)
  * **HOW (Implementation Details):** [../02-tdd/sub-it-admin-details.md](../02-tdd/sub-it-admin-details.md)
* **Persona 2 — BU Admin (School Admin & Cohort Admin — All BU Admins Are Cohort Admins by Default):** School Admins organize Department Sub-folders and can assign additional Cohort Admins at the Sub-folder or Cohort level. Cohort Admins (including all School Admins) create Cohort Folders, initialize $\lceil N/100 \rceil$ `<cohort_slug>-pNN` Project Shards via Terraform, manage and switch the Cohort's **Current Active Provisioning Project**, configure enabled services and per-student quantities, map the **Cohort Student Email Group**, suspend/delete individual student slices, set project budget overrides, and teardown completed cohorts.
  * **WHY (User Journeys):** [brs-bu-admin-cuj.md](brs-bu-admin-cuj.md)
  * **HOW (Implementation Details):** [../02-tdd/sub-bu-admin-details.md](../02-tdd/sub-bu-admin-details.md)
* **Persona 3 — Student:** Logs in, sees the Cohort(s) matching their **Cohort Student Email Group** memberships, and selects a Cohort. Upon entering the Cohort workspace, the platform checks if their Student Slice is initialized — automatically initializing their enabled **Student-Level Singletons** (`1` mandatory `sa-<student_slug>`, `Gemini`, `1` `bkt-<project_id>-<student_slug>`, `1` `db_<student_slug>`) in the Cohort's **Current Active Provisioning Project** if needed — and then unlocks **App Container (`app-<app_slug>`)** creation so they can freely mix, match, and delete App-specific services within their per-student allowance.
  * **WHY (User Journeys):** [brs-student-cuj.md](brs-student-cuj.md)
  * **HOW (Implementation Details):** [../02-tdd/sub-student-details.md](../02-tdd/sub-student-details.md)
