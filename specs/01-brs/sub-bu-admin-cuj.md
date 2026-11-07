# BU Admin (School Admin & Cohort Admin) — Critical User Journeys (`THE WHY`)

> **Master Document:** [Business Requirements Specification — Master (`THE WHAT`)](brs-master.md)  
> **Companion Details Document:** [BU Admin Implementation Details (`THE HOW`)](../02-tdd/sub-bu-admin-details.md)  
> **Persona:** Layer 2 — BU Admin (`School Admin ⊃ Cohort Admin ⊃ Student` — **All BU Admins are by default Cohort Admins**)

---

## Overview of BU Admin Roles & Goals

Within the Business Unit (BU) layer, **every BU Admin is by default a Cohort Admin** within their delegated scope, while Top-Level School Admins also hold folder-tree and admin-delegation capabilities:
1. **Top-Level School Admin (Assigned by IT Admin on a School Folder):** Is a Cohort Admin across the entire School by default, and additionally organizes **Department Sub-folders** under their School Folder, manages sub-folder budgets, decommissions empty sub-folders, and can assign additional **Cohort Admins** either at a **Department Sub-folder level** or directly at a **Cohort Folder level**.
2. **Cohort Admin (Default for all BU Admins, or assigned at a Sub-folder / Cohort level):** Creates and manages **Cohorts** within their scope — sizing cohorts ($\lceil N / 100 \rceil$ project shards), maintaining or switching the Cohort's **Current Active Provisioning Project** based on remaining capacity, enabling services (with mandatory `Service Account` locked ON and automatic prerequisite resolution), setting per-student quantity overrides, mapping the **Cohort Student Email Group**, suspending students or deleting individual student slices, adjusting project shard spend limits, supporting students, and tearing down completed cohorts.

---

## Part A: School Admin Critical User Journeys

### CUJ-BU-01: Organize a School Folder into Department Sub-folders
> **As a** Top-Level School Admin,  
> **I want to** create Department Sub-folders (e.g., *Computer Science*, *Electrical Engineering*) underneath my delegated School Folder and assign each sub-folder an optional Pooled Sub-folder Budget,  
> **So that** multi-department schools can segregate cohorts, budgets, and department-level Cohort Admins without needing Central IT.

* **Business Inputs:** `Parent School Folder`, `Sub-folder Display Name`, `Sub-folder Slug`, and `Optional Pooled Sub-folder Budget`.
* **Business Outcome:** Provisions the GCP Sub-folder and optional `google_billing_budget` under the School Folder in an isolated Sub-folder Terraform state and records it in Firebase DB.

---

### CUJ-BU-02: Assign Additional Cohort Admins at the Sub-folder or Cohort Level
> **As a** Top-Level School Admin,  
> **I want to** assign additional Cohort Admins (Cloud Identity Users or Groups) either to a **Department Sub-folder** (so they can create and manage all Cohorts in that department) or to a specific **Cohort Folder** (so a course instructor or TA only manages that single Cohort),  
> **So that** faculty and lab coordinators have least-privilege administrative autonomy over their exact academic scope while I retain default Cohort Admin rights across the entire School.

* **Business Inputs:** `Target Scope (Department Sub-folder OR specific Cohort Folder)` and `Cohort Admin User(s) / Group(s)`.
* **Business Outcome:** Binds cascading read/inspection IAM at the target folder scope and grants Cohort Admin rights for that Sub-folder or Cohort in Firebase DB.

---

### CUJ-BU-03: Update Department Sub-folder Budgets or Decommission an Empty Sub-folder
> **As a** Top-Level School Admin,  
> **I want to** update the Pooled Sub-folder Budget or Cohort Admin mappings on an existing Department Sub-folder, or cleanly decommission a Department Sub-folder that has zero active Cohorts underneath it,  
> **So that** department reorganizations and budget adjustments happen self-service within the School.

* **Business Pre-condition (for Decommission):** Zero active Cohorts exist under the target Department Sub-folder.
* **Business Outcome:** Updates or destroys the Department Sub-folder and its associated budget via Sub-folder Terraform and updates Firebase DB.

---

## Part B: Cohort Admin Critical User Journeys *(Default for All BU Admins)*

### CUJ-BU-04: Create & Initialize a Cohort (Inheriting from Active IT Admin Config Version)
> **As a** Cohort Admin (or School Admin),  
> **I want to** create a new Cohort Folder under my School Folder or Department Sub-folder by specifying the Cohort name/slug, expected student count ($N$, with default `100` students per project inherited from IT Admin Config), Pooled Cohort Budget, Default Project Shard Limit, Enabled Services (`Service Account` locked as mandatory; optional services enforcing Service Catalog prerequisites), and Per-Service Per-Student Quantities (taking `min` from the Service Catalog Config by default with optional Cohort override),  
> **So that** the platform automatically initializes $\lceil N / 100 \rceil$ Project Shards (`<cohort_slug>-p01..pNN`) with the required APIs, shared project infrastructure (such as Shared Cloud SQL), and budgets via Cohort Terraform, and sets `<cohort_slug>-p01` as the initial **Current Active Provisioning Project**.

* **Business Inputs:**
  * `Parent Folder` (School Folder or Department Sub-folder)
  * `Cohort Display Name` & `Cohort Slug` (e.g., `cs101-fall`)
  * `Expected Student Size (N)` & `Students per Project` (default `100` $\rightarrow$ initializes $K = \lceil N / 100 \rceil$ shards: `<cohort_slug>-p01..pKK`)
  * `Pooled Cohort Folder Budget` (e.g., `\$8,000`) & `Default Project Shard Limit` (e.g., `\$3,000`)
  * `Enabled Services` (inherited from active IT Admin Config version: `Service Account` [Mandatory — always ON], `Gemini`, `GCS`, `Cloud SQL`, `Cloud Run`, `Vertex AI Search` [requires `GCS`])
  * `Per-Service Per-Student Quantity` (pre-populated with `min` from Service Catalog Config; `Unlimited (∞)` for GCS Managed Folders; override allowed at the Cohort level)
* **Business Outcome:** Pins the Cohort to the active IT Admin Config version for underlying service sizes, initializes the Cohort Folder and $\lceil N / 100 \rceil$ Project Shards via Cohort Terraform (`src/terraform/buadmin`), sets `active_provisioning_project_id = "<cohort_slug>-p01"`, and persists outputs to Firebase DB.

---

### CUJ-BU-05: Map Cohort Student Email Group & Manage the Active Provisioning Project
> **As a** Cohort Admin (or School Admin),  
> **I want to** map a **Cohort Student Email Group** (e.g., `grp-cs101-students@school.edu`) to the Cohort and view or manually switch the Cohort's **Current Active Provisioning Project** (`<cohort_slug>-pNN`) based on remaining shard capacity,  
> **So that** any student in the Cohort's email group who logs in and enters the Cohort workspace is automatically initialized into the Current Active Provisioning Project without manual per-student Terraform runs, and I can redirect new student initializations to another shard whenever needed.

* **Business Inputs:**
  * `Target Cohort` + `Cohort Student Email Group(s)` (e.g., `grp-cs101-students@school.edu`)
  * Optional: `Selected Active Provisioning Project Shard` (`<cohort_slug>-pNN` with remaining capacity `< 100`)
* **Business Outcome:**
  * Associates the Cohort Student Email Group(s) with the Cohort so group members see the Cohort upon login.
  * Maintains `active_provisioning_project_id` on the Cohort (automatically advancing to the next shard when a shard hits `100 / 100` initialized students, or switching immediately when changed by the Cohort Admin).

---

### CUJ-BU-06: Edit Cohort Enabled Services & Per-Student Quantities Non-Destructively
> **As a** Cohort Admin (or School Admin),  
> **I want to** enable additional optional services on an existing Cohort (automatically enabling any Service Catalog prerequisites and running Cohort Terraform to provision shared project infrastructure), disable previously enabled optional services without deleting already-provisioned student services, or adjust per-student service quantities without affecting student resources already deployed in excess of the new quantity,  
> **So that** mid-term adjustments to course requirements never destroy or disrupt existing student work.

* **Business Inputs:** `Target Cohort`, updated `Enabled Services` toggles (`Service Account` remains locked ON as mandatory), and/or updated `Per-Student Quantity Overrides`.
* **Business Outcome:**
  * **When a service is newly enabled:** Automatically enables its prerequisites from the Service Catalog Config (e.g., enabling `Vertex AI Search` enables `GCS`), runs Cohort Terraform to enable project APIs / shared infrastructure (e.g., Shared Cloud SQL instance `sql-<project_id>`), and ensures any missing Student-Level Singletons (`bkt-...`, `db_<student_slug>`) are auto-initialized when students enter the Cohort workspace.
  * **When an enabled optional service is disabled:** Blocks new provisioning of that service going forward while preserving 100% of already-provisioned project and student resources.
  * **When a per-student quantity is lowered:** Updates the Cohort allowance gate for future creations (`deployed_count < new_quantity`) while leaving any student's existing deployed resources in excess of the new quantity completely untouched.

---

### CUJ-BU-07: Offboard an Individual Student — Suspend Student vs. Delete Student Slice
> **As a** Cohort Admin (or School Admin),  
> **I want to** either **Suspend** an individual student in a Cohort (temporarily revoking their access while keeping their resources intact) or **Delete a Student Slice** (permanently tearing down their App Containers and Student-Level Singletons in that Cohort),  
> **So that** I can handle both temporary academic holds/audits and permanent course drops cleanly.

* **Business Inputs:** `Target Cohort`, `Target Student Email`, and selected action (`SUSPEND_STUDENT` | `UNSUSPEND_STUDENT` | `DELETE_STUDENT_SLICE`).
* **Business Outcome:**
  * **Option A — Suspend Student (`SUSPEND_STUDENT`):** Revokes `user:<student_email>` access bindings and locks/hides the Cohort sandbox in the student's portal while preserving all of the student's Student-Level Singletons and App Containers (`app-<app_slug>`). Can be reversed via `UNSUSPEND_STUDENT`.
  * **Option B — Delete Student Slice (`DELETE_STUDENT_SLICE`):** Tears down all of the student's App Containers (`app-<app_slug>`) and their Student-Level Singletons (`sa-<student_slug>`, `bkt-<project_id>-<student_slug>`, `db_<student_slug>`) via the Atomic Pipeline, removes the student's initialized record from the Cohort shard, and increments the shard's remaining seat capacity.

---

### CUJ-BU-08: Drill Into a Project Shard to Override Project Spend Limits or Switch Active Provisioning Target
> **As a** Cohort Admin (or School Admin),  
> **I want to** drill down into a specific Project Shard (`<cohort_slug>-pNN`) to set or adjust a Per-Project Spend Limit Override, monitor shard spend and remaining student capacity, or mark that shard as the Cohort's **Current Active Provisioning Project**,  
> **So that** uneven student consumption across shards is absorbed smoothly and any shard or Cohort crossing 100% spend surfaces a Red Budget Alert Banner.

* **Business Inputs:** `Target Project Shard ID` (`<cohort_slug>-pNN`), `Project Spend Limit Override Amount`, and/or `Set as Active Provisioning Project`.
* **Business Outcome:** Updates that project shard's `google_billing_budget` via Cohort Terraform and/or updates `active_provisioning_project_id` on the Cohort in Firebase DB.

---

### CUJ-BU-09: Expand Cohort Student Capacity Non-Disruptively
> **As a** Cohort Admin (or School Admin),  
> **I want to** increase a Cohort's student size $N$ (e.g., from `350` to `430` students) when enrollment grows beyond current shard capacity,  
> **So that** additional Project Shards (`<cohort_slug>-p05`) are initialized non-disruptively alongside existing shards `p01..p04` and become available as provisioning targets.

* **Business Inputs:** `Target Cohort` and increased `Expected Student Size (N)`.
* **Business Outcome:** Initializes the additional `<cohort_slug>-pNN` shard(s) via Cohort Terraform without modifying or interrupting existing shards or students.

---

### CUJ-BU-10: Search Students Across Scope & Act on a Student's Behalf via Cumulative Inheritance
> **As a** Cohort Admin (or School Admin),  
> **I want to** search for any student by email or name within my delegated scope to see all Cohort(s) and Project Shard(s) they belong to, inspect their Student-Level Singletons and App Containers (`app-<app_slug>`), and initialize or create/delete App-specific services on their behalf (`BU Admin ⊃ Student`),  
> **So that** I can verify student progress or directly assist a student during a lab session.

* **Business Inputs:** `Student Email or Name Search Query` $\rightarrow$ selected `Student Slice` (`<student_email>` in `<cohort_slug>-pNN`).
* **Business Outcome:** Resolves all Cohort/Shard assignments for that student inside the admin's delegated scope and allows inspecting or executing Student-level actions on the student's behalf.

---

### CUJ-BU-11: Execute Full Cohort Teardown at End of Semester or Hackathon
> **As a** Cohort Admin (or School Admin),  
> **I want to** execute a full **Cohort Teardown** when a course or hackathon concludes,  
> **So that** all student App resources, Student-Level Singletons, shared Cloud SQL instances, Project Shards (`<cohort_slug>-p01..pNN`), budgets, and the Cohort Folder are cleanly destroyed (`terraform destroy`) and billing stops immediately.

* **Business Inputs:** `Target Cohort` + explicit `Cohort Slug Confirmation`.
* **Business Outcome:** Runs Cohort teardown across all `<cohort_slug>-p01..pNN` shards and the Cohort Folder, removing all cloud resources and marking the Cohort archived/destroyed in Firebase DB.
