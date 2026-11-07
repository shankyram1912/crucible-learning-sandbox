# 01 — Business & Functional Specification

> **Status:** In Review — Persona 1 (IT Admin) Drafted  
> **Repository:** `learning-sandbox`

---

## 1. Platform Overview & Core Invariants

The **Learning Sandbox** is a visual, self-service cloud playground management platform for universities and enterprises. It enables organizations to safely govern, budget, and provision isolated Google Cloud environments for thousands of students across multiple Schools, Business Units (BUs), and Course Cohorts.

### 1.1 Cumulative Persona Hierarchy (`IT Admin ⊃ BU Admin ⊃ Student`)
The platform enforces a **strict cumulative inheritance model** across three personas:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ PERSONA 1: IT ADMIN (Root / Organization Governance)                         │
│  • Own Rights: School Folders, Department Sub-folders, BU Admin IAM Group    │
│    mapping, Billing Account association, and Pooled Folder Budgets.          │
│  • Inherited Rights: 100% of BU Admin rights + 100% of Student rights.       │
├──────────────────────────────────────────────────────────────────────────────┤
│ PERSONA 2: BU ADMIN (School / Department / Cohort Operator)                  │
│  • Own Rights: Cohort Folder creation, Cohort Sizing (-> Project Shards),    │
│    Project-level Terraform Service initialization, Project Spend Limit       │
│    Overrides, Cloud Identity User/Group mapping, Student Search, Teardown.   │
│  • Inherited Rights: 100% of Student rights within their managed scope.      │
├──────────────────────────────────────────────────────────────────────────────┤
│ PERSONA 3: STUDENT (Sandbox Builder)                                         │
│  • Own Rights: Personal 6-Node Visual Canvas (Gemini default + 5 optional    │
│    services), Atomic Create & Delete via Canvas, ClickOps usage in GCP.      │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Seven Core Business Invariants
1. **Central Control Tower Architecture:** A dedicated **Control Tower Project** sits under the Root Sandbox Folder hosting the Visual Canvas UI, the FastAPI Backend-for-Frontend (BFF), the Firebase/Firestore database, and the privileged `sa-control-tower` Service Account that executes Terraform and atomic GCP operations across child folders and projects.
2. **Canvas-Only Create & Delete (Zero State Drift):** Top-level sandbox resources are created **and** deleted exclusively through the Visual Canvas portal. Students receive **no IAM management rights** (`setIamPolicy`) and **no top-level resource create/delete rights** in GCP — only service-appropriate data-plane/usage permissions on their provisioned slice. Consequently, Firebase DB is always the authoritative source of truth.
3. **Dual Execution Pipelines:**
   * **Terraform Pipeline (Admin & Cohort Foundation):** Used by IT Admins (`src/terraform/itadmin`) and BU Admins (`src/terraform/buadmin`) to manage stateful infrastructure (Folders, Sub-folders, Cohort Project Shards, Shared Cloud SQL instances, Budgets, and IAM Groups) and persist `terraform output -json` into Firebase DB.
   * **Atomic API Pipeline (Student Services & Roster Mapping):** Used for fast (2–5 second) creation and deletion of individual student services and Cloud Identity cohort roster assignments.
4. **Single-Action Workspace Locking:** Every administrative or student mutation executes as a **single atomic action** guarded by a scoped lock in Firebase DB (`locks/root`, `locks/folder_<id>`, `locks/cohort_<id>`, `locks/project_<id>`, `locks/student_<email>`). While an action is running, concurrent viewers see a live **Observer Mode** lock banner and real-time 5-stage pipeline progress.
5. **Capacity-Driven Cohort Sharding ($\le 100$ Students / Project):** Because shared GCP projects have quota boundaries (such as 100 Data Stores per project in Vertex AI Search and shared Cloud SQL connection pools), a Cohort of size $N$ automatically initializes $\lceil N / 100 \rceil$ **Project Shards**.
6. **Pooled Folder Budgets + Over-Subscribable Project Limits with Overrides:** True financial envelopes are enforced via Pooled Folder Budgets (`resource_ancestors`) at the Root, School, Sub-folder, and Cohort levels. Individual Project Shards receive a default spend limit (which can intentionally sum to more than the parent folder budget to absorb uneven usage across shards) and support per-project limit overrides.
7. **Unified `LIVE` vs. `SIMULATE` Control Config:** A single system `control_config` toggles between `LIVE` and `SIMULATE` modes, isolating Firebase DB paths under `/environments/live/...` and `/environments/simulate/...`. In `SIMULATE` mode, Terraform pipelines run real `terraform validate` against compiled `.tfvars.json` and persist synthesized `terraform output -json` structures into `/environments/simulate/...` so UI refreshes behave identically to production.

---

## 2. Persona 1: IT Admin (Root & Organizational Governance)

### 2.1 Role Summary
The **IT Admin** owns the top-level organizational structure, billing account attachment, and delegation boundaries under the **Root Sandbox Folder**. Once the IT Admin sets up a School Folder (and optional Department Sub-folders), assigns a Pooled Folder Budget, and maps a BU Admin IAM Group, day-to-day cohort and project operations are fully delegated to the BU Admin.

### 2.2 GCP Resource Hierarchy Owned by IT Admin

```text
[Root Sandbox Folder]  (Seeded at Day-0 Bootstrap; Root Pooled Budget)
 │
 ├── 🗼 Control Tower Project (Hosts BFF, Visual Canvas UI, Firebase DB, TF State Bucket)
 │
 ├── 🏛️ School Folder: Business School
 │    • Billing Account Reference: XXXX-YYYY-ZZZZ
 │    • Pooled School Folder Budget: $15,000
 │    • Mapped BU Admin Group: grp-bu-admin-biz@domain.edu (Cascades to all children)
 │
 └── 🏛️ School Folder: College of Engineering
      • Billing Account Reference: XXXX-YYYY-ZZZZ
      • Pooled School Folder Budget: $40,000
      • Mapped BU Admin Group (School-wide): grp-bu-admin-eng-dean@domain.edu
      │
      ├── 📂 Sub-folder: Computer Science
      │    • Pooled Sub-folder Budget: $25,000
      │    • Mapped BU Admin Group (Dept-scoped): grp-bu-admin-cs@domain.edu
      │
      └── 📂 Sub-folder: Electrical Engineering
           • Pooled Sub-folder Budget: $15,000
           • Mapped BU Admin Group (Dept-scoped): grp-bu-admin-ee@domain.edu
```

### 2.3 Functional Capabilities (IT Admin Own Layer)

| Capability ID | Action Name | Description & Business Rules | Pipeline & Lock Scope |
| :--- | :--- | :--- | :--- |
| **`IT-01`** | **Create School Folder** | Creates a top-level GCP Folder directly under the Root Sandbox Folder (`parent = folders/<root_folder_id>`), associates the Billing Account ID in metadata, and sets an initial Pooled Folder Budget. | `itadmin` Terraform Pipeline · Lock: `locks/root` |
| **`IT-02`** | **Create Department Sub-folder** | Creates a child GCP Sub-folder under an existing School Folder (`parent = folders/<school_folder_id>`) so large schools can partition governance and budgets by department. | `itadmin` Terraform Pipeline · Lock: `locks/folder_<school_id>` |
| **`IT-03`** | **Map BU Admin IAM Group to Folder / Sub-folder** | Selects an existing Cloud Identity Group (or creates/assigns `grp-bu-admin-<slug>`) and binds it to the target School Folder or Department Sub-folder. Permissions cascade automatically to all Cohort Folders and Project Shards created underneath. | `itadmin` Terraform Pipeline · Lock: `locks/folder_<target_id>` |
| **`IT-04`** | **Configure / Update Pooled Folder Budget** | Sets or updates the `google_billing_budget` (`budget_filter.resource_ancestors = ["folders/<id>"]`) for the Root Folder, a School Folder, or a Department Sub-folder, wired to the Control Tower Pub/Sub topic for live spend tracking. | `itadmin` Terraform Pipeline · Lock: `locks/folder_<target_id>` |
| **`IT-05`** | **Decommission Empty School / Sub-folder** | Removes a School Folder or Department Sub-folder via Terraform, permitted **only** when zero active Cohorts exist underneath it. | `itadmin` Terraform Pipeline · Lock: `locks/folder_<target_id>` |
| **`IT-06`** | **Manage Global Control Config (`LIVE` / `SIMULATE`)** | Toggles the Control Tower execution mode (`LIVE` vs. `SIMULATE`), configures simulation outcomes (`SUCCESS` / `FAILURE` + target fail step) for testing, or resets `/environments/simulate`. | BFF Control Engine · Immediate |

### 2.4 Inherited Capabilities
Because `IT Admin ⊃ BU Admin ⊃ Student`:
* An IT Admin can zoom into any **School Folder** or **Department Sub-folder** on the Visual Canvas and perform any **BU Admin** action (create a Cohort, initialize project shards, override a project budget, map Cloud Identity student groups, or teardown a cohort).
* An IT Admin can zoom all the way into any **Student Sandbox Canvas** and trigger atomic service creation or deletion on behalf of that student.

### 2.5 IT Admin Business Rules & Validation Guardrails
1. **Maximum Folder Depth Before Cohort:** IT Admins can create **School Folders** (Depth 1 under Root) and **Department Sub-folders** (Depth 2 under Root). Cohorts sit either directly under a School Folder (Depth 2) or under a Department Sub-folder (Depth 3).
2. **Cascading Admin Visibility:**
   * A BU Admin mapped at a **School Folder** (e.g., `College of Engineering`) automatically inherits BU Admin visibility and rights across that School Folder **and** all of its Department Sub-folders (`Computer Science`, `Electrical Engineering`).
   * A BU Admin mapped at a **Department Sub-folder** (`Computer Science`) sees and manages **only** `Computer Science` and its child Cohorts — they cannot see `Electrical Engineering` or sibling schools.
3. **Budget Envelope Rule vs. Over-Subscription:**
   * At the Folder level (`Root -> School -> Sub-folder`), the Visual Canvas displays both **Allocated Child Folder Budgets** and **Actual Pooled Spend** (streamed from Cloud Billing Budget Pub/Sub notifications).
   * Child folder budgets can be configured flexibly by the IT Admin (with a visual warning if the sum of child folder budgets exceeds the parent folder budget, or hard-capped if strict envelope mode is enabled).
4. **Single-Action Serialization:**
   * Creating a new top-level School Folder acquires `locks/root` for the duration of the Terraform run.
   * Modifying an existing School Folder or creating a Sub-folder inside it acquires `locks/folder_<school_id>`, placing all other admins viewing that School subtree into **Observer Mode** until the pipeline run finishes and persists its `terraform output -json` to Firebase DB.

---

## 3. Persona 2: BU Admin (School / Department / Cohort Operator)
*(Next section to draft and review)*

---

## 4. Persona 3: Student (Sandbox Builder)
*(Pending after Persona 2 review)*
