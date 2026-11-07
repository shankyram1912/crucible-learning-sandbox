# IT Admin — Critical User Journeys (THE WHY)

> **Parent Document:** [01 — Business & Functional Specification](../01-business-spec.md)  
> **Companion Details Document:** [IT Admin Implementation Details (HOW)](it-admin-details.md)  
> **Persona:** Persona 1 — IT Admin (Root & Organization Governance)

---

## Overview of IT Admin Goals
The IT Admin's mission is to establish **organizational structure, financial guardrails, and delegated administrative boundaries** once per School or Department so that Business Unit (BU) Admins can self-serve course cohorts without central IT becoming a recurring operational bottleneck.

---

## Critical User Journeys (CUJs)

### CUJ-IT-01: Onboard a New School Folder Under the Root Sandbox
> **As an** IT Admin,  
> **I want to** create a top-level School Folder under the Root Sandbox Folder and associate it with a Cloud Billing Account and an initial Pooled Folder Budget,  
> **So that** a new School (e.g., *Business School* or *College of Engineering*) has an isolated organizational boundary and financial envelope ready for delegation.

* **Trigger on Visual Canvas:** IT Admin clicks **`+ Add School Folder`** on the Root Sandbox Folder node.
* **Inputs Provided:**
  * `School Display Name` (e.g., `College of Engineering`) and `Slug` (`eng`)
  * `Billing Account ID` (defaults to the Root Sandbox Billing Account)
  * `Pooled School Folder Budget` (e.g., `$40,000` per quarter/academic year)
* **Outcome on Canvas:**
  * Acquires `locks/root` for the single action.
  * Streams the 5-stage Terraform pipeline progress in the drawer.
  * Renders the new **School Folder Node** on the Root Canvas with its live `$0 / $40,000` budget meter.

---

### CUJ-IT-02: Partition a Large School into Department Sub-folders
> **As an** IT Admin,  
> **I want to** create Department Sub-folders (e.g., *Computer Science*, *Electrical Engineering*) underneath an existing School Folder,  
> **So that** multi-department schools can segregate cohorts, budgets, and department coordinators while still rolling up to the School's umbrella folder.

* **Trigger on Visual Canvas:** IT Admin clicks **`+ Add Sub-folder`** on a School Folder node.
* **Inputs Provided:**
  * `Sub-folder Display Name` (e.g., `Computer Science`) and `Slug` (`cs`)
  * `Optional Pooled Sub-folder Budget` (e.g., `$25,000`)
* **Outcome on Canvas:**
  * Acquires `locks/folder_<school_id>` (leaving other Schools unlocked).
  * Creates the child GCP Sub-folder and optional sub-folder budget via Terraform, and renders the child node under the School Folder.

---

### CUJ-IT-03: Delegate Governance by Mapping a BU Admin IAM Group
> **As an** IT Admin,  
> **I want to** map a Cloud Identity Group (e.g., `grp-bu-admin-cs@domain.edu`) to either a School Folder or a Department Sub-folder,  
> **So that** members of that group automatically gain BU Admin rights on that folder and all descendant Cohort Folders and Project Shards without manual per-project IAM updates.

* **Trigger on Visual Canvas:** IT Admin selects a School Folder or Department Sub-folder node and clicks **`Map BU Admin Group`**.
* **Inputs Provided:**
  * Search & select an existing **Cloud Identity Group** (or specify a new group email to bind).
* **Outcome on Canvas:**
  * Acquires `locks/folder_<target_id>`.
  * Binds the group at the target GCP Folder level via Terraform and records the mapping in Firebase DB.
  * Displays the mapped **BU Admin Group badge** on the Folder card; any user in that group logging into the portal now lands directly on that Folder's BU Admin Canvas.

---

### CUJ-IT-04: Monitor & Adjust Pooled Folder Budgets Across Schools
> **As an** IT Admin,  
> **I want to** view real-time actual spend against Pooled Folder Budgets at the Root, School, and Sub-folder levels and adjust folder budget allocations when needed,  
> **So that** the institution stays within its overall cloud funding commitment while reallocating budget to high-demand schools.

* **Trigger on Visual Canvas:** IT Admin views the spend meters on the Root Canvas or clicks **`Edit Folder Budget`** on any Folder node.
* **Outcome on Canvas:**
  * Shows warn indicator if child folder budget allocations exceed the parent folder's pooled budget.
  * Runs the `itadmin` Terraform budget update under `locks/folder_<target_id>` and updates the folder's threshold alerts (`50%`, `80%`, `90%`, `100%`).

---

### CUJ-IT-05: Decommission an Empty School or Department Sub-folder
> **As an** IT Admin,  
> **I want to** cleanly remove a School Folder or Department Sub-folder that no longer has any active Cohorts or Sub-folders underneath it,  
> **So that** obsolete organizational folders and budgets do not clutter the Root hierarchy.

* **Trigger on Visual Canvas:** IT Admin clicks **`Delete Folder`** on an empty School or Sub-folder node (button is disabled if child Sub-folders or Cohorts exist).
* **Outcome on Canvas:**
  * Acquires `locks/folder_<target_id>`, runs `terraform destroy` on that folder's state, removes the node from Firebase DB, and refreshes the tree.

---

### CUJ-IT-06: Act as a BU Admin or Student via Cumulative Inheritance
> **As an** IT Admin,  
> **I want to** drill down into any School/Sub-folder, Cohort, Project Shard, or individual Student Sandbox Canvas and execute BU Admin or Student actions directly,  
> **So that** I can assist faculty with cohort setup, override a project shard limit, or troubleshoot a student's sandbox without switching accounts.

* **Trigger on Visual Canvas:** IT Admin double-clicks any School/Sub-folder (enters Zoom Level 1/2 BU Admin View), any Project Shard (enters Zoom Level 2 Project Drilldown), or searches a student email (enters Zoom Level 3 Student Sandbox Canvas).

---

### CUJ-IT-07: Switch Between `LIVE` and `SIMULATE` Execution Modes
> **As an** IT Admin,  
> **I want to** toggle the platform's central `control_config` between `LIVE` mode and `SIMULATE` mode (with configurable `SUCCESS` / `FAILURE` pipeline outcomes),  
> **So that** I can dry-run and validate Terraform and Atomic pipeline flows end-to-end on the Visual Canvas before executing against live GCP billing accounts.
