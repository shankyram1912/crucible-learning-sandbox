# Business Requirements Specification — Master (`THE WHAT`)

> **Document Role:** Primary Business Specification (*What business problem we solve, the three personas, how folders/cohorts/projects/apps are organized, the config-driven service & quota inheritance model, who operates at each level, and the functional experience per persona*).  
> *(Note: Visual Canvas UI layout and interaction mechanics are specified separately in [ui-master-spec.md](../technical-design/ui/ui-master-spec.md).)*
>
> **Secondary Persona Documents (`WHY` & `HOW`):**
> * **Persona 1 — IT Admin:** [sub-it-admin-cuj.md](sub-it-admin-cuj.md) · [sub-it-admin-details.md](sub-it-admin-details.md)
> * **Persona 2 — BU Admin:** [sub-bu-admin-cuj.md](sub-bu-admin-cuj.md) · [sub-bu-admin-details.md](sub-bu-admin-details.md)
> * **Persona 3 — Student:** [sub-student-cuj.md](sub-student-cuj.md) · [sub-student-details.md](sub-student-details.md)

---

## 1. The Business Problem: Shared Cohort Projects & Pooled Budgets

Institutions running cloud and AI programs generally use two distinct sandbox models depending on learning goals:

1. **Dedicated Project per Student (Personal Flexible Learning):** Recommended when the goal is open-ended personal exploration with more relaxed self-admin controls and a hard per-student project budget.
2. **Shared Cohort Project & Pooled Budget (What This Platform Solves):** When universities and enterprises run structured courses, labs, and hackathons for hundreds or thousands of students under **shared GCP projects and pooled folder/cohort budgets**, they hit three operational barriers:
   * **Shared-Project Isolation & IAM Challenge:** Placing multiple students into a shared GCP project with standard roles (`Editor` or broad service roles) allows students to see, overwrite, or delete each other's resources, exhaust shared budgets, or get blocked by `Permission Denied` errors on services where `create` and `list` are evaluated at the project level (such as Cloud Run and Vertex AI Search).
   * **The Central IT Bottleneck:** Central IT owns the Organization Root Folder, Cloud Billing Account, and global platform guardrails, while Schools, Departments, and Faculty (Business Units) own the academic cohorts and student rosters. Requiring central IT intervention every time a cohort needs projects, shared databases, or student onboarding turns a 5-minute setup into a multi-day ticket queue.
   * **Multi-Assignment Organization & Quota Governance for Students:** Within a shared project, a student often builds multiple labs or apps over a term. Without a clear boundary between **Student-Level Singletons** (`1` Service Account, `1` Bucket, `1` Logical DB, plus Gemini access — if enabled on the cohort) and **App-Level Boundaries (`app-<app_slug>`)** governed by dynamic per-student service limits derived from project quotas and cohort shard density, students either overwrite earlier work or exhaust shared project quotas.

### What the Learning Sandbox Solves
The **Learning Sandbox** provides a **Self-Service Portal** backed by a **Central Control Tower** for the **Shared Project & Pooled Budget** model, cleanly decoupling:
* **Organizational, Financial & Global Service Catalog Governance (IT Admin)** from
* **Cohort Sizing, Service Selection, Per-Student Max Caps & Student Mapping (BU Admin)** from
* **Two-Tier Student & App Sandbox Building (Student)** — where **100 students by default safely share a single GCP project shard** with pooled budgets, over-subscribable project limits, quota-derived per-student resource caps, and zero state drift because **all resource creation and deletion happen exclusively through the portal**.

---

## 2. The Three Personas & Cumulative Inheritance Model

The platform is built around three personas arranged in a **strict cumulative inheritance hierarchy (`IT Admin ⊃ BU Admin ⊃ Student`)**: every higher layer automatically inherits 100% of the rights of all lower layers within its scope, plus its own layer's capabilities.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: IT ADMIN (Root, Global Config & Organization Governance)            │
│  • Own Capabilities:                                                         │
│    - Manage Global Platform Config (loaded from Service Catalog Config):     │
│      • Default Students per Project Shard (Default: 100 students/project)    │
│      • Default Enabled Services (SA, Gemini, GCS, Cloud SQL, Cloud Run,      │
│        Vertex AI Search, etc.) & underlying per-project service settings     │
│      • Per-Project Quota Ceilings (Q_project) & Per-Student Min / Default    │
│        settings per service                                                  │
│    - Organize School Folders and Department Sub-folders under Root           │
│    - Map BU Admin IAM Groups to School Folders or Department Sub-folders     │
│    - Configure Billing Account associations and Pooled Folder Budgets        │
│    - Control system execution mode (LIVE vs. SIMULATE)                       │
│  • Inherited Capabilities: 100% of BU Admin + 100% of Student capabilities   │
├──────────────────────────────────────────────────────────────────────────────┤
│ LAYER 2: BU ADMIN (School / Department / Cohort Operator)                    │
│  • Own Capabilities:                                                         │
│    - Create Cohort Folders under their School Folder or Dept Sub-folder      │
│    - Configure Cohort Editable Elements (inheriting defaults from IT Admin): │
│      • Cohort Student Size (N) & Students per Project (Default: 100)         │
│        ──> Initializes ⌈N / 100⌉ Project Shards (<cohort_slug>-p01..pNN)     │
│      • Services Enabled on Cohort (SA, Gemini, GCS, Cloud SQL, Cloud Run,    │
│        Vertex AI Search, etc. — enabling services triggers Terraform across  │
│        all project shards and all mapped students in the Cohort)             │
│      • Per-Service Per-Student Allowance (bounded between Min from Admin     │
│        Service Catalog Config, Default, and dynamic Max derived from         │
│        Q_project and students per project shard)                             │
│      • Pooled Cohort Budget, Default Project Limit & Per-Project Overrides   │
│    - Map Cloud Identity Users / User Groups (or CSV rosters) to Cohorts      │
│      (triggers Terraform to provision enabled Student-Level Singletons for   │
│      all mapped students)                                                    │
│    - Search for students across their folders/projects & Teardown Cohorts    │
│  • Inherited Capabilities: 100% of Student capabilities in their scope       │
├──────────────────────────────────────────────────────────────────────────────┤
│ LAYER 3: STUDENT (Sandbox Builder — Student Singletons + App Boundary)       │
│  • Student-Level Singletons (Max 1 per Student, if Service Enabled on Cohort)│
│    - Gemini Access (if Gemini enabled)                                       │
│    - 1 Service Account: sa-<student_slug> (if SA enabled)                    │
│    - 1 Student GCS Bucket: bkt-<project_id>-<student_slug> (if GCS enabled)  │
│    - 1 Student Logical DB: db_<student_slug> on sql-<project_id> (if SQL on) │
│  • App-Level Boundary (app-<app_slug> — Mix & Match up to Student Max Caps): │
│    - Example App-Scoped Building Blocks (1..N across Apps within Student Cap)│
│      1. GCS Managed Folders under Student Bucket (Unlimited: ∞)              │
│         (gs://bkt-<project_id>-<student_slug>/apps/<app_slug>/<folder>/)     │
│      2. Postgres Schemas inside Student Logical DB (Configurable Default/Max)│
│         (db_<student_slug>.<app_slug>_<schema>)                              │
│      3. Cloud Run Services (Configurable Default/Max)                        │
│         (run-<student_slug>-<app_slug>-<svc>)                                │
│      4. Vertex AI Search Data Stores & Apps (Configurable Default/Max)       │
│         (search-ds-<student_slug>-<app_slug>-<name> &                        │
│          search-app-<student_slug>-<app_slug>-<name>)                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

*(Note: The services above — Service Account, Gemini, GCS, Cloud SQL, Cloud Run, and Vertex AI Search — represent the initial example catalog loaded from the platform's Service Catalog Config.)*

---

## 3. Config-Driven Service Catalog, IT Admin Config & Cohort Editable Elements

Rather than hardcoding service lists or arbitrary per-student limits, the platform uses a **three-level configuration cascade**:

```text
[1. Platform Service Catalog Config]
 │  Defines the list of supported services, their underlying default per-project
 │  Terraform/API settings (e.g., Cloud SQL tier, API lists), baseline GCP Project
 │  Quota ceilings (Q_project), and baseline per-student Min (m_service) & Default (d_service).
 ▼
[2. IT Admin Global Config Screen]
 │  • Loads the Service Catalog Config and sets institution-wide defaults & bounds:
 │    - Default Students per Project Shard: S_shard = 100 (always defaults to 100)
 │    - Default Enabled Services for new Cohorts (including SA & Gemini)
 │    - Effective Max Quota per Project per Service (Q_project)
 │    - Per-Student Min (m_service) and Default (d_service) per Service
 ▼
[3. BU Admin Cohort Editable Elements (Inherited from IT Admin Config)]
    • Cohort Sizing: Expected Students (N) & Students per Project (S_shard, default 100)
      - Project Shards Initialized: K = ⌈N / S_shard⌉
      - Students per Project Shard: n_shard = min(N, S_shard)
    • Enabled Services Toggle: Toggle which services are enabled for this Cohort
      (SA, Gemini, GCS, Cloud SQL, Cloud Run, Vertex AI Search, etc.)
      ──> Enabling/updating services or mapping students triggers Cohort Terraform
          across all Project Shards and all Students in the Cohort!
    • Per-Service Per-Student Max (for each enabled service):
      - Pre-populated with IT Admin's Default Per-Student setting (d_service)
      - Bounded on the low end by Min Per-Student (m_service, from Admin Service Catalog Config)
      - Bounded on the high end by the Dynamic Max Ceiling:
        m_service  <=  Selected_Max_Per_Student  <=  ⌊ Q_project(service) / n_shard ⌋
```

### Cohort Editable Elements & Quota Math Reference

| Service (From Catalog Config) | Cohort Enable Toggle (Triggers Cohort Terraform for All Students) | Student-Level Singleton *(Terraform-Provisioned, 1 per Student if Enabled)* | App-Level Building Block (`app-<app_slug>`, Atomic Pipeline) | Per-Student Allowance Bounds (`Min` / `Default` / `Max`) |
| :--- | :--- | :--- | :--- | :--- |
| **Service Account** | Enabled by default | `1` SA (`sa-<student_slug>`) | Bound as runtime identity across Student's Apps | Fixed Singleton (`1` per student when enabled) |
| **Gemini (Vertex AI)** | Enabled by default | Project + `sa-<student_slug>` Gemini access | Called by Student's Apps & IDE | Enabled / Disabled per Cohort |
| **GCS** | Enabled by default | `1` Bucket (`bkt-<project_id>-<student_slug>`) | **GCS Managed Folders** (`apps/<app_slug>/<folder>/`) | Bucket: `1` per student<br>Managed Folders: **Unlimited (`∞`)** *(default)* |
| **Cloud SQL** | Configurable default | `1` Logical DB (`db_<student_slug>`) on shared `sql-<project_id>` | **Postgres Schemas** (`db_<student_slug>.<app_slug>_<schema>`) | Logical DB: `1` per student<br>Schemas: **Configurable** (`min` from config, `default` from config, `max` = $\lfloor Q_{\text{sql\_schemas}} / n_{\text{shard}} \rfloor$) |
| **Cloud Run** | Enabled by default | *(Uses `sa-<student_slug>`)* | **Cloud Run Services** (`run-<student_slug>-<app_slug>-<svc>`) | **Configurable** (`min` from config, `default` from config, `max` = $\lfloor Q_{\text{cloud\_run}} / n_{\text{shard}} \rfloor$) |
| **Vertex AI Search** | Enabled by default | *(Uses `sa-<student_slug>` + `bkt-...`)* | **Search Data Stores & Apps** (`search-ds-...` & `search-app-...`) | **Configurable** (`min` from config, `default` from config, `max` = $\lfloor Q_{\text{vertex\_search}} / n_{\text{shard}} \rfloor$) |

* **Flexible Mix & Match Across Apps:** A student's configured `max_per_student` is a **pooled allowance across all Apps (`app-<app_slug>`) created by that student** in that Cohort project. For example, if a Cohort allows `max = 3` Cloud Run services per student, a student may deploy all `3` inside `app-capstone`, or `1` each across `app-lab1`, `app-lab2`, and `app-lab3`.

---

## 4. Typical Organization of Folders, Projects, Students & Apps

```text
[Root Sandbox Folder]                               <── IT Admin Scope (Root Pooled Budget + Global Config)
 │
 ├── 🗼 Control Tower Project                        <── Hosts Portal UI, FastAPI BFF, Firebase DB,
 │                                                       Service Catalog Config, TF State & sa-control-tower
 │
 ├── 🏛️ School Folder: Business School              <── IT Admin creates + maps Biz BU Admin Group
 │    │                                                 (Pooled School Folder Budget: $15,000)
 │    └── 🎓 Cohort Folder: mba-genai-fall          <── BU Admin creates Cohort (Size: 80, Default 100/project)
 │         └── 📦 Project Shard: mba-genai-fall-p01 <── 1 Shard initialized (80 / 100 seats)
 │
 └── 🏛️ School Folder: College of Engineering       <── IT Admin creates + maps Dean BU Admin Group
      │                                                 (Pooled School Folder Budget: $40,000)
      └── 📂 Sub-folder: Computer Science           <── IT Admin creates + maps CS BU Admin Group
           │                                            (Pooled Sub-folder Budget: $25,000)
           └── 🎓 Cohort Folder: cs101-fall         <── BU Admin creates Cohort (Size: 350, Default 100/project)
                │                                       (Pooled Cohort Folder Budget: $8,000)
                ├── 📦 Project Shard: cs101-fall-p01 <── 100 / 100 students · Limit: $3,000 (Default)
                ├── 📦 Project Shard: cs101-fall-p02 <── 100 / 100 students · Limit: $5,000 (Override ⚡)
                │    │
                │    └── 👤 Student Slice: alice-tan (alice.tan@school.edu)
                │         ├── [Student-Level Singletons — 1 each when service is enabled on Cohort]
                │         │    ├── ✨ Gemini (Enabled)
                │         │    ├── 🔑 Service Account (1): sa-alice-tan
                │         │    ├── 🪣 Student Bucket (1): bkt-cs101-fall-p02-alice-tan
                │         │    └── 🗄️ Student Logical DB (1): db_alice_tan (on shared sql-cs101-fall-p02)
                │         │
                │         ├── 🚀 App: app-lab1 (Mix & match within Alice's Cohort per-student max caps)
                │         │    ├── 📁 Managed Folder (∞): gs://bkt-...-alice-tan/apps/lab1/rag-docs/
                │         │    ├── 🔎 Vertex Search: search-ds-alice-tan-lab1-docs & search-app-alice-tan-lab1-main
                │         │    ├── 🧩 DB Schema: db_alice_tan.lab1_core
                │         │    └── ☁️ Cloud Run: run-alice-tan-lab1-api
                │         │
                │         └── 🚀 App: app-capstone
                │              ├── 📁 Managed Folder (∞): gs://bkt-...-alice-tan/apps/capstone/assets/
                │              ├── 🧩 DB Schemas: db_alice_tan.capstone_users, db_alice_tan.capstone_logs
                │              └── ☁️ Cloud Run: run-alice-tan-capstone-web, run-alice-tan-capstone-worker
                │
                ├── 📦 Project Shard: cs101-fall-p03 <── 100 / 100 students · Limit: $3,000 (Default)
                └── 📦 Project Shard: cs101-fall-p04 <──  50 / 100 students · Limit: $3,000 (Default)
```

---

## 5. Core Business Rules & Naming Conventions

1. **Deterministic Naming Conventions:**
   * **Project Shard IDs:** Derived from the Cohort slug: `<cohort_slug>-p01`, `<cohort_slug>-p02`, ..., `<cohort_slug>-pNN`.
   * **Student Slug:** Derived from the email prefix before `@` (normalized to lowercase alphanumeric/hyphens, e.g., `alice.tan@school.edu` $\rightarrow$ `alice-tan`; SQL identifier uses underscores `alice_tan`).
   * **Student-Level Singletons (Max 1 per Student in a Project Shard, if enabled on Cohort):**
     * **Service Account:** `sa-<student_slug>`
     * **Student GCS Bucket:** `bkt-<project_id>-<student_slug>`
     * **Student Cloud SQL Logical Database:** `db_<student_slug>` (on shared instance `sql-<project_id>`)
   * **App-Level Resources (`app-<app_slug>`, Mix & Match within Per-Student Max Caps):**
     * **GCS Managed Folder (Unlimited):** `gs://bkt-<project_id>-<student_slug>/apps/<app_slug>/<folder>/`
     * **Postgres Schema:** `db_<student_slug>.<app_slug>_<schema>`
     * **Cloud Run Service:** `run-<student_slug>-<app_slug>-<svc>`
     * **Vertex AI Search Data Store & App:** `search-ds-<student_slug>-<app_slug>-<name>` and `search-app-<student_slug>-<app_slug>-<name>`
2. **Default 100 Students per Project Shard:**
   * The IT Admin Config sets the default sharding density to **`100` students per project**, which all Cohorts inherit by default.
   * For a Cohort of $N$ students, the platform initializes $K = \lceil N / 100 \rceil$ Project Shards (`<cohort_slug>-p01..pKK`) via Terraform using the Control Tower's privileged service account.
3. **Cohort Terraform for Project Shards & All Student-Level Singletons:**
   * **Step 1 (Cohort Init & Service Enablement):** Project Shards and shared project-level infrastructure (based on the Cohort's enabled service list and underlying default project settings from config) are initialized via Cohort Terraform (`src/terraform/buadmin`).
   * **Step 2 (Student Mapping & Service Toggling Triggers Terraform for All Students):** Mapping Cloud Identity Users/Groups (or CSV rosters) to a Cohort — or enabling additional services on an existing Cohort — **triggers the Cohort Terraform pipeline across all mapped students**, provisioning `1` Service Account (`sa-<student_slug>`), `Gemini` bindings, `1` Student Bucket (`bkt-<project_id>-<student_slug>`), and `1` Student Logical DB (`db_<student_slug>`) for every student in the Cohort according to the enabled services.
   * **Step 3 (Student Self-Service at the App Level):** Students then self-serve creation and deletion of **Apps (`app-<app_slug>`)** and App-scoped building blocks (`GCS Managed Folders`, `Postgres Schemas`, `Cloud Run Services`, `Vertex AI Search Data Stores & Apps`) via the fast Atomic Pipeline within their Cohort's configured per-student max caps.
4. **Multi-Cohort & Unassigned User Rules:**
   * **Unassigned Users:** A logged-in user not mapped to any admin group or student cohort sees a **"No Sandbox Assigned"** state.
   * **Multi-Cohort Students:** A student enrolled in multiple Cohorts is mapped to a distinct Project Shard per Cohort and manages their Student Slice and Apps independently in each assigned Cohort project.
5. **Pooled Folder Budgets, Over-Subscribable Project Limits & Alert Behavior:**
   * **Folder Budgets** (`Root`, `School`, `Sub-folder`, `Cohort`) track actual pooled spend across all descendant projects.
   * **Project Shard Limits** default to an over-subscribable guardrail (absorbing uneven student usage across shards) and support **Per-Project Overrides**.
   * **Budget Exceeded Behavior:** Crossing `100%` of a Folder Budget or Project Shard Limit surfaces a **Red Budget Alert Banner** for that scope (visual alert without freezing active student resources).
6. **Portal-Only Create & Delete (Usage-Only Rights in GCP):**
   * Students create and delete their Apps and App-level resources strictly through the Self-Service Portal.
   * In GCP, students receive **no IAM management privileges** (`setIamPolicy`) and **no top-level resource create/delete permissions** — only service-appropriate usage rights on their provisioned slice.
7. **Single-Action Workspace Locking & `LIVE`/`SIMULATE` Control Config:**
   * Every mutation acquires a scoped lock (`root`, `folder`, `cohort`, `project`, or `student`) so only one action executes at a time within that scope.
   * A central `control_config` toggles between `LIVE` and `SIMULATE` modes (isolating Firebase DB under `/environments/live/...` and `/environments/simulate/...`).

---

## 6. Operating Level & Responsibility Matrix by Persona

| Hierarchy Level | Functional Area | IT Admin | BU Admin | Student |
| :--- | :--- | :--- | :--- | :--- |
| **Root Sandbox Folder & Global Config** | Control Tower, Service Catalog & Global Quota/Default Config (default `100` students/project, default enabled services including `SA` & `Gemini`, project quota ceilings), Billing Account Ref, Root Budget, `LIVE`/`SIMULATE` Config, School Folder Creation | **Owner (Full CRUD)** | — | — |
| **School Folder & Dept Sub-folder** | Sub-folder organization, BU Admin IAM Group mapping (cascading), Pooled Folder Budgets | **Owner (Full CRUD)** | **Scoped Operator** *(within mapped Folder/Sub-folder)* | — |
| **Cohort Folder** | Create Cohort Folder, edit Cohort Settings (inherited from IT Admin: Student Size $N$, `100` students/project $\rightarrow \lceil N/100 \rceil$ shards, Enabled Services including `SA` & `Gemini`, Per-Service Per-Student Max with dynamic quota ceiling), map Cloud Identity Users/Groups, Cohort Budget, **Cohort Teardown** | *Inherited* | **Owner (Full CRUD)** | — |
| **Project Shard ($\le 100$ students)** | Initialize/toggle Project-Level Terraform Services (`Shared Cloud SQL`, `Vertex AI Search`, `Cloud Run`, `GCS`, `SA`, `Gemini`), set **Project Spend Limit Override**, Student Search | *Inherited* | **Owner (Full CRUD)** | — |
| **Student Level (Singletons per Student)** | `1` Service Account (`sa-<student_slug>`), `Gemini`, `1` Student Bucket (`bkt-...`), and `1` Student Logical DB (`db_<student_slug>`) — provisioned when enabled on Cohort | *Inherited* | *Inherited (Can act on behalf of student)* | **Usage Rights in GCP** |
| **App Boundary (`app-<app_slug>`)** | Self-service Create & Delete of Apps and mix-and-match App-scoped services (`GCS Managed Folders` [$\infty$], `DB Schemas`, `Cloud Run Services`, `Vertex AI Search Data Stores & Apps`) within Cohort's Per-Student Max Caps | *Inherited* | *Inherited (Can act on behalf of student)* | **Owner (Portal Create/Delete + GCP Usage Rights)** |

---

## 7. Outline of the Functional Experience per Persona

* **Persona 1 — IT Admin:** Operates at the Root, Global Config, School Folder, and Department Sub-folder level to configure global service/quota defaults (default `100` students/project, default enabled services including `SA` & `Gemini`, project quota ceilings), establish the organizational tree, map cascading BU Admin IAM Groups, and manage Pooled Folder Budgets, with full inherited drilldown into BU Admin and Student scopes.
  * **WHY (User Journeys):** [sub-it-admin-cuj.md](sub-it-admin-cuj.md)
  * **HOW (Implementation Details):** [sub-it-admin-details.md](sub-it-admin-details.md)
* **Persona 2 — BU Admin:** Operates within their mapped School Folder or Department Sub-folder to create Cohort Folders, customize Cohort settings inherited from IT Admin (enabled services including `SA` & `Gemini`, per-service per-student max caps bounded by project quota and cohort student count, default `100` students/project $\rightarrow \lceil N/100 \rceil$ `<cohort_slug>-pNN` shards), set project budget overrides, map Cloud Identity users/groups (which provisions enabled Student-Level Singletons), search students, and teardown completed cohorts.
  * **WHY (User Journeys):** [sub-bu-admin-cuj.md](sub-bu-admin-cuj.md)
  * **HOW (Implementation Details):** [sub-bu-admin-details.md](sub-bu-admin-details.md)
* **Persona 3 — Student:** Operates within their assigned Cohort Project Shard(s) where their enabled **Student-Level Singletons** (`1` `sa-<student_slug>`, `Gemini`, `1` `bkt-<project_id>-<student_slug>`, `1` `db_<student_slug>`) are ready, and creates **Apps (`app-<app_slug>`)** to freely mix and match **GCS Managed Folders** ($\infty$), **Postgres Schemas**, **Cloud Run services**, and **Vertex AI Search Data Stores & Apps** (`search-ds-...`, `search-app-...`) within their Cohort's per-student max service caps.
  * **WHY (User Journeys):** [sub-student-cuj.md](sub-student-cuj.md)
  * **HOW (Implementation Details):** [sub-student-details.md](sub-student-details.md)
