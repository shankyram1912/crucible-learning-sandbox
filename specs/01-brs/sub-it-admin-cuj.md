# IT Admin — Critical User Journeys (`THE WHY`)

> **Master Document:** [Business Requirements Specification — Master (`THE WHAT`)](brs-master.md)  
> **Companion Details Document:** [IT Admin Implementation Details (`THE HOW`)](../02-tdd/sub-it-admin-details.md)  
> **Persona:** Layer 1 — IT Admin (`IT Admin ⊃ BU Admin [School Admin ⊃ Cohort Admin] ⊃ Student`)

---

## Overview of IT Admin Goals

The IT Admin's mission is to configure **version-tracked global platform defaults & service catalog guardrails**, attach **Cloud Billing Accounts and Root/School Pooled Budgets**, create **Top-Level School Folders**, and assign **Top-Level School Admins** — handing off all internal School organization (Department Sub-folders, Cohort Admin assignments, and Cohort operations) to the School Admins so Central IT never becomes a recurring operational bottleneck.

---

## Critical User Journeys (CUJs)

### CUJ-IT-01: Configure Version-Tracked Global Platform Defaults, Service Sizes & Quota Bounds
> **As an** IT Admin,  
> **I want to** manage the institution-wide defaults on the IT Admin Global Config screen (loaded from the Platform Service Catalog Config) — including the default students per project shard (`100` by default), default enabled services for new cohorts (`Service Account`, `Gemini`, `GCS`, `Cloud SQL`, `Cloud Run`, `Vertex AI Search`), underlying service sizes (e.g., Cloud SQL tier, Cloud Run CPU/memory), and service quota defaults (`min`) and `max` ceilings — with every configuration change version-tracked so previous versions can be viewed,  
> **So that** every new Cohort created by a School or Cohort Admin inherits from the latest active configuration version while existing Cohorts remain completely unaffected.

* **Business Inputs:**
  * `Default Students per Project Shard` (defaults to `100` students/project)
  * `Default Enabled Services` for new Cohorts (`SA`, `Gemini`, `GCS`, `Cloud SQL`, `Cloud Run`, `Vertex AI Search`, etc.)
  * `Per-Service Sizes & Underlying Settings` (e.g., shared Cloud SQL instance tier/storage, Cloud Run CPU/memory limits)
  * `Per-Service Quota Defaults (Min) & Max Ceilings` (with override allowed)
* **Business Outcome:** Saves a new immutable, version-tracked configuration snapshot in Firebase DB (allowing the IT Admin to view previous configuration versions at any time). Subsequent Cohort creations inherit from the latest version, while **existing Cohorts are unaffected**.

---

### CUJ-IT-02: Associate Billing Account & Configure the Root Pooled Budget
> **As an** IT Admin,  
> **I want to** associate the organization's Cloud Billing Account with the Root Sandbox Folder and set a Root Pooled Folder Budget,  
> **So that** aggregate cloud spend across all Top-Level School Folders, Department Sub-folders, and Cohorts is tracked under one top-level financial envelope and displays a red budget alert banner if total spend reaches or exceeds 100%.

* **Business Inputs:** `Billing Account ID`, `Currency Code`, and `Root Pooled Budget Amount`.
* **Business Outcome:** Provisions/updates the Root-level `google_billing_budget` (`resource_ancestors = ["folders/<root_folder_id>"]`) and records the default billing account reference for top-level School Folders.

---

### CUJ-IT-03: Onboard a Top-Level School Folder & Assign Top-Level School Admins
> **As an** IT Admin,  
> **I want to** create a Top-Level School Folder under the Root Sandbox Folder, assign it a Pooled School Folder Budget, and map Top-Level School Admins (Cloud Identity Users or Groups, e.g., `grp-school-admin-eng@domain.edu`) to that School Folder,  
> **So that** a new School (e.g., *Business School* or *College of Engineering*) has an isolated organizational boundary, a pooled financial envelope, and empowered School Admins who can self-serve their own Department Sub-folders, Cohort Admins, and Cohorts.

* **Business Inputs:** `School Display Name`, `School Slug`, `Billing Account ID` (defaults to Root Billing Account), `Pooled School Folder Budget`, and `Top-Level School Admin User(s) / Group(s)`.
* **Business Outcome:** Provisions the Top-Level School Folder, Pooled School Budget, and cascading School Admin IAM bindings via IT Admin Terraform (`src/terraform/itadmin`), persisting the School Folder and School Admin mapping to Firebase DB.

---

### CUJ-IT-04: Update Top-Level School Admins or Adjust Pooled School Budgets
> **As an** IT Admin,  
> **I want to** add or remove Top-Level School Admins on an existing School Folder and monitor/adjust Pooled Budgets at the Root and School Folder levels,  
> **So that** school leadership transitions and budget top-ups are handled cleanly and any School crossing 100% of its pooled budget surfaces a Red Budget Alert Banner.

* **Business Inputs:** `Target School Folder`, updated `School Admin User(s) / Group(s)`, and/or `Updated Pooled School Budget Amount`.
* **Business Outcome:** Updates the School Folder's IAM bindings and `google_billing_budget` via IT Admin Terraform and refreshes spend alert states.

---

### CUJ-IT-05: Decommission an Empty Top-Level School Folder
> **As an** IT Admin,  
> **I want to** cleanly remove a Top-Level School Folder that has zero active Department Sub-folders or Cohorts underneath it,  
> **So that** retired organizational units and their billing budgets do not clutter the Root hierarchy.

* **Business Pre-condition:** Zero active child Sub-folders or Cohorts exist under the target School Folder.
* **Business Outcome:** Destroys the School Folder and its associated budget via IT Admin Terraform and removes it from Firebase DB.

---

### CUJ-IT-06: Act as a School Admin, Cohort Admin, or Student via Cumulative Inheritance
> **As an** IT Admin,  
> **I want to** drill down into any School Folder, Department Sub-folder, Cohort Folder, Project Shard, or individual Student Slice and perform any School Admin, Cohort Admin, or Student operation (`IT Admin ⊃ School Admin ⊃ Cohort Admin ⊃ Student`),  
> **So that** I can assist a School Admin with sub-folder setup, help a Cohort Admin override a project shard spend limit, or troubleshoot a student's App container without switching accounts.

* **Business Inputs:** Any School Admin, Cohort Admin, or Student action within the selected scope.
* **Business Outcome:** Executes the target workflow with full audit attribution to the acting IT Admin.

---

### CUJ-IT-07: Switch Platform Execution Between `LIVE` and `SIMULATE` Modes
> **As an** IT Admin,  
> **I want to** toggle the platform's central `control_config` between `LIVE` mode and `SIMULATE` mode (with configurable `SUCCESS` / `FAILURE` pipeline outcomes isolated under `/environments/simulate`),  
> **So that** I can dry-run and validate Terraform and Atomic pipeline flows end-to-end without mutating live GCP folders, projects, or billing budgets.

* **Business Inputs:** `Execution Mode (LIVE | SIMULATE)` and `Simulation Outcome Flags (SUCCESS | FAILURE)`.
* **Business Outcome:** Switches the active Firebase DB environment namespace (`/environments/live` vs. `/environments/simulate`) and pipeline execution behavior.
