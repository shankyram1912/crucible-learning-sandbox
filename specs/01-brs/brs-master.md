# 01 — Business & Functional Specification (THE WHAT)

> **Document Role:** Primary Business Specification (*What business problem we solve, the three personas, how folders/cohorts/projects are organized, who operates at each level, and the functional experience per persona*).  
> *(Note: Visual Canvas UI layout and interaction mechanics are specified separately in [ui-master-spec.md](../technical-design/ui/ui-master-spec.md).)*
>
> **Secondary Persona Documents (WHY & HOW):**
> * **Persona 1 — IT Admin:** [IT Admin CUJs (WHY)](sub-it-admin-cuj.md) · [IT Admin Details (HOW)](sub-it-admin-details.md)
> * **Persona 2 — BU Admin:** [BU Admin CUJs (WHY)](sub-bu-admin-cuj.md) · [BU Admin Details (HOW)](sub-bu-admin-details.md)
> * **Persona 3 — Student:** [Student CUJs (WHY)](sub-student-cuj.md) · [Student Details (HOW)](sub-student-details.md)

---

## 1. The Business Problem

Universities and large enterprises running AI, cloud, and software engineering programs face a recurring operational dilemma when giving hundreds or thousands of students hands-on access to Google Cloud:

1. **The "One Project per Student" Sprawl Problem:** Creating thousands of individual GCP projects hits billing account linking quotas, makes cost tracking and teardown painful, and requires heavy central IT intervention for every course or hackathon.
2. **The "Shared Project" Blast-Radius & IAM Problem:** Putting multiple students into a shared GCP project using standard roles (`Editor` or broad service roles) allows students to see, overwrite, or delete each other's resources, exhaust project-wide budgets with runaway compute, or get blocked by `Permission Denied` errors on services where `create` and `list` are evaluated at the project level (such as Cloud Run and Vertex AI Search).
3. **The Central IT Bottleneck:** Central IT owns the Organization Root Folder and Cloud Billing Account, while Schools, Departments, and Faculty (Business Units) own the academic cohorts and student rosters. When faculty have to file IT tickets every time a new course cohort needs projects, databases, or student onboarding, turnaround takes days instead of minutes.
4. **GCP Console Cognitive Overload for Students:** First-time learners logging into the full Google Cloud Console face hundreds of menus and cryptic IAM errors when all they need is a clean, guided playground with Gemini, their own Workload Identity Service Account, and four optional building blocks (Storage, Search/RAG, Database, and App Hosting).

### What the Learning Sandbox Solves
The **Learning Sandbox** provides a **Self-Service Portal** backed by a **Central Control Tower** that cleanly decouples:
* **Organizational & Financial Governance (IT Admin)** from
* **Cohort Sizing, Project Initialization & Student Onboarding (BU Admin)** from
* **Self-Service Sandbox Building (Student)** — where up to **100 students safely share a single GCP project shard** with strict per-student isolation, pooled folder budgets with project-level overrides, and zero state drift because **all resource creation and deletion happen exclusively through the portal**.

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
│    - Toggle which Project-Level Services are initialized per Cohort/Project  │
│    - Set Default Project Spend Limits & Per-Project Spend Limit Overrides    │
│    - Map Cloud Identity Users / User Groups (or CSV rosters) to Cohorts      │
│      (automatically creating each mapped student's Service Account)          │
│    - Search for students across their folders/projects & Teardown Cohorts    │
│  • Inherited Capabilities: 100% of Student capabilities in their scope       │
├──────────────────────────────────────────────────────────────────────────────┤
│ LAYER 3: STUDENT (Sandbox Builder)                                           │
│  • Default Provisioned Baseline (Created when student is mapped to project): │
│    - Gemini (Vertex AI access)                                               │
│    - Dedicated Service Account (sa-<student_slug>)                           │
│  • 4 Optional Self-Service Resources (Create & Delete via Portal):           │
│    1. GCS Bucket (bkt-<project_id>-<student_slug>)                           │
│    2. Vertex AI Search Agent (ds-<student_slug> + app-<student_slug>)        │
│    3. Cloud SQL Database (db_<student_slug> on project's shared SQL instance)│
│    4. Cloud Run Service (run-<student_slug> running as sa-<student_slug>)    │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Typical Organization of Folders & Projects in Context

To mirror how universities and enterprises are structured — where some schools are flat (e.g., *Business School*) while others are divided into departments (e.g., *College of Engineering $\rightarrow$ Computer Science*) — the platform organizes GCP resources into a polymorphic hierarchy under a single **Root Sandbox Folder**:

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
      ├── 📂 Sub-folder: Computer Science           <── IT Admin creates + maps CS BU Admin Group
      │    │                                            (Pooled Sub-folder Budget: $25,000)
      │    └── 🎓 Cohort Folder: cs101-fall         <── BU Admin creates Cohort (Size: 350 students)
      │         │                                       (Pooled Cohort Folder Budget: $8,000)
      │         ├── 📦 Project Shard: cs101-fall-p01 <── 100 / 100 students · Limit: $3,000 (Default)
      │         ├── 📦 Project Shard: cs101-fall-p02 <── 100 / 100 students · Limit: $5,000 (Override ⚡)
      │         ├── 📦 Project Shard: cs101-fall-p03 <── 100 / 100 students · Limit: $3,000 (Default)
      │         └── 📦 Project Shard: cs101-fall-p04 <──  50 / 100 students · Limit: $3,000 (Default)
      │
      └── 📂 Sub-folder: Electrical Engineering     <── IT Admin creates + maps EE BU Admin Group
           └── 🎓 Cohort Folder: robotics-lab       <── BU Admin creates Cohort (Size: 60 students)
                └── 📦 Project Shard: robotics-lab-p01 <── 1 Shard initialized (60 / 100 seats)
```

---

## 4. Core Business Rules & Naming Conventions

1. **Naming Conventions:**
   * **Project Shard IDs:** Derived directly from the Cohort slug: `<cohort_slug>-p01`, `<cohort_slug>-p02`, ..., `<cohort_slug>-pNN`.
   * **Student Slug:** Derived from the email prefix before `@` (normalized to lowercase alphanumeric/hyphens, e.g., `alice.tan@school.edu` $\rightarrow$ `alice-tan`).
   * **Student Resources:**
     * Service Account (auto-created on project mapping): `sa-<student_slug>`
     * GCS Bucket: `bkt-<project_id>-<student_slug>`
     * Vertex AI Search Data Store & App: `ds-<student_slug>` and `app-<student_slug>`
     * Cloud SQL Logical Database: `db_<student_slug>` (on shared instance `sql-<project_id>`)
     * Cloud Run Service: `run-<student_slug>`
2. **Automatic Project Sharding ($\le 100$ Students per Project):** When a BU Admin specifies a Cohort size of $N$ students, the platform calculates $\lceil N / 100 \rceil$ Project Shards (`<cohort_slug>-p01..pNN`) and initializes them via Terraform using the Control Tower's privileged service account.
3. **Decoupled Cohort Initialization vs. Student Mapping:**
   * **Step 1 (Cohort Init):** Project Shards and their shared project-level infrastructure (such as the Shared Cloud SQL instance) are initialized first via Terraform based on expected Cohort size.
   * **Step 2 (Student Mapping Later):** When the BU Admin later maps Cloud Identity Users, User Groups, or a CSV roster to the Cohort, each student is assigned to a Project Shard ($\le 100$ students/shard) and their personal **Service Account (`sa-<student_slug>`)** and baseline **Gemini** access are provisioned automatically.
4. **Multi-Cohort & Unassigned User Rules:**
   * **Unassigned Users:** A logged-in user who is not mapped to any admin group or student cohort sees a **"No Sandbox Assigned"** state.
   * **Multi-Cohort Students:** A student enrolled in multiple Cohorts is mapped to a distinct Project Shard per Cohort (and can initialize/manage their sandbox independently in each assigned Cohort project).
5. **Pooled Folder Budgets, Over-Subscribable Project Limits & Alert Behavior:**
   * **Folder Budgets** (`Root`, `School`, `Sub-folder`, `Cohort`) track actual pooled spend across all descendant projects.
   * **Project Shard Limits** default to an over-subscribable guardrail (so uneven student usage across shards is absorbed naturally) and support **Per-Project Overrides**.
   * **Budget Exceeded Behavior:** Crossing `100%` of a Folder Budget or Project Shard Limit surfaces a **Red Budget Exceeded Status** for that scope (visual alert without freezing active student resources).
6. **Portal-Only Create & Delete (Usage-Only Rights in GCP):**
   * Students create and delete their 4 optional services strictly through the Self-Service Portal.
   * In GCP, students have **no IAM management privileges** (`setIamPolicy`) and **no top-level resource create/delete permissions** — only service-appropriate usage rights on their provisioned slice.
7. **Single-Action Workspace Locking & `LIVE`/`SIMULATE` Control Config:**
   * Every mutation acquires a scoped lock (`root`, `folder`, `cohort`, `project`, or `student`) so only one action executes at a time within that scope.
   * A central `control_config` toggles between `LIVE` and `SIMULATE` modes (isolating Firebase DB under `/environments/live/...` and `/environments/simulate/...`).

---

## 5. Operating Level & Responsibility Matrix by Persona

| Hierarchy Level | Functional Area | IT Admin | BU Admin | Student |
| :--- | :--- | :--- | :--- | :--- |
| **Root Sandbox Folder** | Control Tower, Billing Account Ref, Root Budget, `LIVE`/`SIMULATE` Config, School Folder Creation | **Owner (Full CRUD)** | — | — |
| **School Folder & Dept Sub-folder** | Sub-folder organization, BU Admin IAM Group mapping (cascading), Pooled Folder Budgets | **Owner (Full CRUD)** | **Scoped Operator** *(within mapped Folder/Sub-folder)* | — |
| **Cohort Folder** | Create Cohort Folder, size Cohort ($\rightarrow \lceil N/100 \rceil$ `<cohort_slug>-pNN` shards), map Cloud Identity Users/Groups, Cohort Budget, **Cohort Teardown** | *Inherited* | **Owner (Full CRUD)** | — |
| **Project Shard ($\le 100$ students)** | Initialize/toggle Project-Level Terraform Services (`Shared Cloud SQL`, `Vertex AI Search`, `Cloud Run`, `GCS`), set **Project Spend Limit Override**, Student Search | *Inherited* | **Owner (Full CRUD)** | — |
| **Student Sandbox Slice** | Default `Gemini` + `sa-<student_slug>` (created on project mapping); Self-service Create & Delete of `GCS Bucket`, `Vertex AI Search Agent`, `Cloud SQL DB`, `Cloud Run` + ClickOps usage in GCP | *Inherited* | *Inherited (Can act on behalf of student)* | **Owner (Portal Create/Delete + GCP Usage Rights)** |

---

## 6. Outline of the Functional Experience per Persona

* **Persona 1 — IT Admin:** Operates at the Root, School Folder, and Department Sub-folder level to establish the organizational tree, map cascading BU Admin IAM Groups, and manage Pooled Folder Budgets, with full inherited drilldown into BU Admin and Student scopes.
  * **WHY (User Journeys):** [sub-it-admin-cuj.md](sub-it-admin-cuj.md)
  * **HOW (Implementation Details):** [sub-it-admin-details.md](sub-it-admin-details.md)
* **Persona 2 — BU Admin:** Operates within their mapped School Folder or Department Sub-folder to create Cohort Folders, initialize $\lceil N/100 \rceil$ `<cohort_slug>-pNN` Project Shards via Terraform, configure project-level services and budget overrides, map Cloud Identity users/groups (which initializes student Service Accounts), search students, and teardown completed cohorts.
  * **WHY (User Journeys):** [sub-bu-admin-cuj.md](sub-bu-admin-cuj.md)
  * **HOW (Implementation Details):** [sub-bu-admin-details.md](sub-bu-admin-details.md)
* **Persona 3 — Student:** Operates within their assigned Cohort Project Shard(s) with **Gemini** and **`sa-<student_slug>`** active out of the box, and self-serves creation and deletion of their 4 optional services (**GCS Bucket**, **Vertex AI Search Agent**, **Cloud SQL DB**, **Cloud Run**), using Google Cloud Console ClickOps and Antigravity IDE for day-to-day building.
  * **WHY (User Journeys):** [sub-student-cuj.md](sub-student-cuj.md)
  * **HOW (Implementation Details):** [sub-student-details.md](sub-student-details.md)
