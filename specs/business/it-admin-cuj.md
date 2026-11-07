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

* **Business Inputs:** `School Display Name`, `School Slug`, `Billing Account ID`, and `Pooled School Folder Budget`.
* **Business Outcome:** A new GCP Folder is provisioned under Root with a pooled folder budget tracking all future spend underneath that School.

---

### CUJ-IT-02: Partition a Large School into Department Sub-folders
> **As an** IT Admin,  
> **I want to** create Department Sub-folders (e.g., *Computer Science*, *Electrical Engineering*) underneath an existing School Folder,  
> **So that** multi-department schools can segregate cohorts, budgets, and department coordinators while still rolling up to the School's umbrella folder.

* **Business Inputs:** `Parent School Folder`, `Sub-folder Display Name`, `Sub-folder Slug`, and `Optional Pooled Sub-folder Budget`.
* **Business Outcome:** A child GCP Sub-folder and optional sub-folder budget are provisioned under the School Folder.

---

### CUJ-IT-03: Delegate Governance by Mapping a BU Admin IAM Group
> **As an** IT Admin,  
> **I want to** map a Cloud Identity Group (e.g., `grp-bu-admin-cs@domain.edu`) to either a School Folder or a Department Sub-folder,  
> **So that** members of that group automatically gain BU Admin rights on that folder and all descendant Cohort Folders and Project Shards without manual per-project IAM updates.

* **Business Inputs:** `Target Folder (School or Sub-folder)` and `Cloud Identity Group Email`.
* **Business Outcome:** The IAM group is bound at the target folder level (cascading down to all future child cohorts/projects) and registered as the authorized BU Admin group for that subtree.

---

### CUJ-IT-04: Monitor & Adjust Pooled Folder Budgets Across Schools
> **As an** IT Admin,  
> **I want to** track actual pooled spend against Pooled Folder Budgets at the Root, School, and Sub-folder levels and adjust folder budget allocations when needed,  
> **So that** the institution stays within its overall cloud funding commitment and sees immediate alerts when a folder exceeds 100% of its budget.

* **Business Inputs:** `Target Folder` and `Updated Pooled Budget Amount`.
* **Business Outcome:** Updates the folder's `google_billing_budget` and surfaces a red budget alert state if actual pooled spend reaches or exceeds 100%.

---

### CUJ-IT-05: Decommission an Empty School or Department Sub-folder
> **As an** IT Admin,  
> **I want to** cleanly remove a School Folder or Department Sub-folder that no longer has any active Cohorts or Sub-folders underneath it,  
> **So that** obsolete organizational folders and budgets do not clutter the Root hierarchy.

* **Business Pre-condition:** Zero active child Sub-folders or Cohorts exist under the target folder.
* **Business Outcome:** Destroys the folder and its associated folder budget via Terraform and removes it from Firebase DB.

---

### CUJ-IT-06: Act as a BU Admin or Student via Cumulative Inheritance
> **As an** IT Admin,  
> **I want to** operate within any School/Sub-folder, Cohort, Project Shard, or individual Student Sandbox using inherited BU Admin and Student capabilities,  
> **So that** I can assist faculty with cohort setup, override a project shard limit, or troubleshoot a student's sandbox without switching accounts.

---

### CUJ-IT-07: Switch Between `LIVE` and `SIMULATE` Execution Modes
> **As an** IT Admin,  
> **I want to** toggle the platform's central `control_config` between `LIVE` mode and `SIMULATE` mode (with configurable `SUCCESS` / `FAILURE` pipeline outcomes),  
> **So that** I can dry-run and validate Terraform and Atomic pipeline flows end-to-end against `/environments/simulate` before executing against live GCP billing accounts.
