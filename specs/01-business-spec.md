# 01 — Business & Functional Specification (THE WHAT)

> **Document Role:** Primary Business Specification (*What we are solving, who the personas are, how the hierarchy is organized, who operates where, and how the Visual Canvas UX works*).  
> **Secondary Persona Documents (WHY & HOW):**
> * **Persona 1 — IT Admin:** [IT Admin CUJs (WHY)](business/it-admin-cuj.md) · [IT Admin Details (HOW)](business/it-admin-details.md)
> * **Persona 2 — BU Admin:** [BU Admin CUJs (WHY)](business/bu-admin-cuj.md) · [BU Admin Details (HOW)](business/bu-admin-details.md)
> * **Persona 3 — Student:** [Student CUJs (WHY)](business/student-cuj.md) · [Student Details (HOW)](business/student-details.md)

---

## 1. The Business Problem

Universities and large enterprises running AI, cloud, and software engineering programs face a recurring operational dilemma when giving hundreds or thousands of students hands-on access to Google Cloud:

1. **The "One Project per Student" Sprawl Problem:** Creating thousands of individual GCP projects hits billing account linking quotas, makes cost tracking and teardown painful, and requires heavy central IT intervention for every course or hackathon.
2. **The "Shared Project" Blast-Radius & IAM Problem:** Putting multiple students into a shared GCP project using standard roles (`Editor` or broad service roles) allows students to see, overwrite, or delete each other's resources, exhaust project-wide budgets with runaway compute, or get blocked by `Permission Denied` errors on services where `create` and `list` are evaluated at the project level (such as Cloud Run and Vertex AI Search).
3. **The Central IT Bottleneck:** Central IT owns the Organization Root Folder and Cloud Billing Account, while Schools, Departments, and Faculty (Business Units) own the academic cohorts and student rosters. When faculty have to file IT tickets every time a new course cohort needs projects, databases, or student onboarding, turnaround takes days instead of minutes.
4. **GCP Console Cognitive Overload for Students:** First-time learners logging into the full Google Cloud Console face hundreds of menus and cryptic IAM errors when all they need is a clean, guided playground with Gemini and a handful of pre-wired building blocks (Storage, Search/RAG, Database, and App Hosting).

### What the Learning Sandbox Solves
The **Learning Sandbox** provides a **Visual Canvas Self-Service Portal** backed by a **Central Control Tower** that cleanly decouples:
* **Organizational & Financial Governance (IT Admin)** from
* **Cohort Sizing, Project Initialization & Student Onboarding (BU Admin)** from
* **Self-Service Sandbox Building (Student)** — where up to **100 students safely share a single GCP project shard** with strict per-student isolation, pooled folder budgets with project-level overrides, and zero state drift because **all resource creation and deletion happen exclusively on the Visual Canvas**.

---

## 2. The Three Personas & Cumulative Inheritance Model

The platform is built around three personas arranged in a **strict cumulative inheritance hierarchy (`IT Admin ⊃ BU Admin ⊃ Student`)**: every higher layer automatically inherits 100% of the rights and views of all lower layers within its scope, plus its own layer's capabilities.

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
│    - Search for students across their folders/projects & Teardown Cohorts    │
│  • Inherited Capabilities: 100% of Student capabilities in their scope       │
├──────────────────────────────────────────────────────────────────────────────┤
│ LAYER 3: STUDENT (Sandbox Builder)                                           │
│  • Own Capabilities:                                                         │
│    - View personal sandbox topology scoped to their assigned Project Shard   │
│    - Create & Delete their personal slice of enabled services on the Canvas: │
│      [Gemini (Default)] + [Service Account] [GCS Bucket]                     │
│      [Vertex AI Search Agent] [Cloud SQL Database] [Cloud Run]               │
│    - Use provisioned services via Google Cloud Console ClickOps & IDE        │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Typical Organization of Folders & Projects in Context

To mirror how universities and enterprises are structured — where some schools are flat (e.g., *Business School*) while others are divided into departments (e.g., *College of Engineering $ightarrow$ Computer Science*) — the platform organizes GCP resources into a polymorphic hierarchy under a single **Root Sandbox Folder**:

```text
[Root Sandbox Folder]                               <── IT Admin Scope (Root Pooled Budget)
 │
 ├── 🗼 Control Tower Project                        <── Hosts Canvas UI, FastAPI BFF, Firebase DB,
 │                                                       TF State Bucket & Privileged sa-control-tower
 │
 ├── 🏛️ School Folder: Business School              <── IT Admin creates + maps Biz BU Admin Group
 │    │                                                 (Pooled School Folder Budget: $15,000)
 │    └── 🎓 Cohort Folder: MBA-GenAI-Fall          <── BU Admin creates Cohort (Size: 80 students)
 │         └── 📦 Project Shard: biz-mba-p01        <── 1 Shard initialized (80 / 100 seats)
 │
 └── 🏛️ School Folder: College of Engineering       <── IT Admin creates + maps Dean BU Admin Group
      │                                                 (Pooled School Folder Budget: $40,000)
      ├── 📂 Sub-folder: Computer Science           <── IT Admin creates + maps CS BU Admin Group
      │    │                                            (Pooled Sub-folder Budget: $25,000)
      │    └── 🎓 Cohort Folder: CS101-Fall         <── BU Admin creates Cohort (Size: 350 students)
      │         │                                       (Pooled Cohort Folder Budget: $8,000)
      │         ├── 📦 Project Shard: cs101-p01     <── 100 / 100 students · Limit: $3,000 (Default)
      │         ├── 📦 Project Shard: cs101-p02     <── 100 / 100 students · Limit: $5,000 (Override ⚡)
      │         ├── 📦 Project Shard: cs101-p03     <── 100 / 100 students · Limit: $3,000 (Default)
      │         └── 📦 Project Shard: cs101-p04     <──  50 / 100 students · Limit: $3,000 (Default)
      │
      └── 📂 Sub-folder: Electrical Engineering     <── IT Admin creates + maps EE BU Admin Group
           └── 🎓 Cohort Folder: Robotics-Lab       <── BU Admin creates Cohort (Size: 60 students)
                └── 📦 Project Shard: ee-robo-p01   <── 1 Shard initialized (60 / 100 seats)
```

### Key Structural Rules
1. **Flexible Cohort Placement:** A **Cohort Folder** can be created by a BU Admin either directly under a **School Folder** (when no department sub-folders are needed) or under a **School / Department Sub-folder**.
2. **Automatic Project Sharding ($\le 100$ Students per Project):** When a BU Admin specifies a Cohort size of $N$ students, the platform automatically calculates $\lceil N / 100 ceil$ Project Shards and initializes them via Terraform using the Control Tower's privileged service account — without requiring IT Admin intervention.
3. **Decoupled Cohort Init vs. Student Onboarding:** Project Shards and their shared infrastructure (such as the per-project Shared Cloud SQL instance) are initialized first based on Cohort size; mapping actual student identities or groups to the Cohort can happen days or weeks later.
4. **Pooled Folder Budgets + Over-Subscribable Project Limits with Overrides:**
   * **Folder Budgets** (`Root`, `School`, `Sub-folder`, `Cohort`) track actual pooled spend across all descendant projects.
   * **Project Shard Limits** default to an over-subscribable guardrail (e.g., 4 shards $	imes$ \$3,000 default limit = \$12,000 inside an \$8,000 Cohort pool) so uneven usage across student shards is absorbed naturally, with **Per-Project Overrides** available for heavy-use shards.

---

## 4. Operating Level & Responsibility Matrix by Persona

| Hierarchy Level | Functional Area | IT Admin | BU Admin | Student |
| :--- | :--- | :--- | :--- | :--- |
| **Root Sandbox Folder** | Control Tower, Billing Account Ref, Root Budget, `LIVE`/`SIMULATE` Config, School Folder Creation | **Owner (Full CRUD)** | — | — |
| **School Folder & Dept Sub-folder** | Sub-folder organization, BU Admin IAM Group mapping (cascading), Pooled Folder Budgets | **Owner (Full CRUD)** | **Scoped Operator** *(within mapped Folder/Sub-folder)* | — |
| **Cohort Folder** | Create Cohort Folder, size Cohort ($ightarrow \lceil N/100 ceil$ shards), map Cloud Identity Users/Groups, Cohort Budget, **Cohort Teardown** | *Inherited* | **Owner (Full CRUD)** | — |
| **Project Shard ($\le 100$ students)** | Initialize/toggle Project-Level Terraform Services (`Shared Cloud SQL`, `Vertex AI Search`, `Cloud Run`, `GCS`), set **Project Spend Limit Override**, Student Search | *Inherited* | **Owner (Full CRUD)** | — |
| **Student Sandbox Slice** | Create & Delete personal services on Visual Canvas (`SA`, `GCS Bucket`, `Vertex AI Search Agent`, `Cloud SQL DB`, `Cloud Run`) + ClickOps usage in GCP | *Inherited* | *Inherited (Can act on behalf of student)* | **Owner (Canvas Create/Delete + GCP Usage Rights)** |

---

## 5. Outline of the User Experience per Persona

All three personas interact with a unified **Visual Canvas (React Flow)** that adapts its starting zoom level and available actions based on the logged-in user's resolved persona (with a **Cohort / Role Switcher** in the top navigation bar if a user belongs to multiple cohorts or roles).

### 5.1 Cross-Persona UX Guarantees
* **Single-Action Workspace Locking ("Observer Mode"):** Only one mutation action can execute at a time within a locked scope (`root`, `folder`, `cohort`, `project`, or `student`). While an action is running, other admins viewing that scope see a live **Observer Lock Banner** showing who holds the lock, which action is executing, and a real-time **5-Stage Pipeline Progress Stepper**.
* **Firebase-Backed Truth & Simulation Parity:** The Visual Canvas always renders the persisted pipeline outputs from Firebase DB (`/environments/live/...` or `/environments/simulate/...`), ensuring browser refreshes (`F5`) always show accurate state.

### 5.2 Persona 1 UX: IT Admin Canvas (Zoom Level 1 — Organizational Tree)
* **Landing View:** Interactive node graph rooted at the **Root Sandbox Folder**, showing all **School Folders**, **Department Sub-folders**, mapped **BU Admin Groups**, and **Live Pooled Spend vs. Budget** bars.
* **Primary Interactions:**
  * Click **`+ School Folder`** or **`+ Sub-folder`** on any node to launch a single-action Terraform pipeline.
  * Click **`Map Admin Group`** on a School or Sub-folder node to search Cloud Identity Groups and bind a cascading BU Admin group.
  * Click **`Edit Folder Budget`** to set or adjust the pooled folder budget.
  * Double-click any School/Sub-folder node to **zoom into the BU Admin Cohort View** (inheriting all BU Admin controls).
* **Detailed Journeys & Implementation:**
  * **WHY (User Journeys):** [business/it-admin-cuj.md](business/it-admin-cuj.md)
  * **HOW (Implementation Details):** [business/it-admin-details.md](business/it-admin-details.md)

### 5.3 Persona 2 UX: BU Admin Canvas (Zoom Levels 1 & 2 — Cohorts & Project Shards)
* **Landing View:** Scoped to the BU Admin's mapped **School Folder(s)** and **Department Sub-folder(s)**, displaying active **Cohort Folders**, their **Project Shards (`1..N`)**, seat capacity (`e.g., 350 / 400 seats`), and **Spend vs. Limit** indicators.
* **Primary Interactions:**
  * **Create & Initialize Cohort:** Enter Cohort name, expected student count ($N$), Cohort budget, default project shard limit, and check which project-level services to initialize in Terraform ($ightarrow$ spins up $\lceil N/100 ceil$ project shards).
  * **Onboard Students / Groups (Anytime Later):** Open a Cohort and pick **Cloud Identity Users or User Groups** (or upload a CSV) to auto-shard students across the Cohort's projects.
  * **Project Shard Drilldown (Zoom Level 2):** Click into a specific Project Shard to toggle additional Terraform services on that project, set a **Project Spend Limit Override**, or inspect the 100-student shard roster.
  * **Global Student Search:** Search any student by name/email in the top bar to locate their Cohort and Project Shard and zoom directly into their **Student Sandbox Canvas**.
  * **Cohort Teardown:** Trigger end-of-semester teardown to cleanly wipe student slices and destroy the Cohort's project shards.
* **Detailed Journeys & Implementation:**
  * **WHY (User Journeys):** [business/bu-admin-cuj.md](business/bu-admin-cuj.md)
  * **HOW (Implementation Details):** [business/bu-admin-details.md](business/bu-admin-details.md)

### 5.4 Persona 3 UX: Student Sandbox Canvas (Zoom Level 3 — Personal 6-Node Topology)
* **Landing View:** Loaded via the student's login email from Firebase DB, scoped strictly to their assigned Project Shard and showing **only their own services**:
  * **Center Node (Always Active):** **Gemini (Vertex AI)**
  * **Up to 5 Optional Surrounding Slots (Gated by what the BU Admin enabled in the Project Shard):**
    1. **Service Account (`sa-<student>`)** — Workload identity badge/node.
    2. **GCS Bucket (`bkt-<project>-<student>`)** — Dedicated per-student bucket with `/rag-docs/` folder.
    3. **Vertex AI Search Agent (`ds-<student>` + `app-<student>`)** — Pre-wired GCS folder Data Connector + Search App shell.
    4. **Cloud SQL Database (`db_<student>`)** — Isolated logical Postgres database + IAM DB auth on the project shard's shared Cloud SQL instance.
    5. **Cloud Run (`run-<student>`)** — Container service running as `sa-<student>`.
* **Primary Interactions:**
  * **Empty State Prompt:** If no optional services are configured yet, the canvas prompts: *"No optional services currently set up — click an available slot to configure one."*
  * **Canvas Create & Delete:** Clicking **`Configure`** or **`Delete`** on any node runs the 5-stage **Atomic Pipeline** (`Validating` $ightarrow$ `Creating/Deleting` $ightarrow$ `Tagging & Labelling` $ightarrow$ `Binding Usage Rights` $ightarrow$ `Ready`) with live visual progress.
  * **ClickOps & IDE Handoff:** Clicking an active node reveals deep-links straight into the exact Google Cloud Console page (ClickOps) and connection strings for Antigravity IDE (guided by the packaged AGY User Guide Skill).
* **Detailed Journeys & Implementation:**
  * **WHY (User Journeys):** [business/student-cuj.md](business/student-cuj.md)
  * **HOW (Implementation Details):** [business/student-details.md](business/student-details.md)
