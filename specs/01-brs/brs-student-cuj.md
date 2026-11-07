# Student — Critical User Journeys (`THE WHY`)

> **Master Document:** [Business Requirements Specification — Master (`THE WHAT`)](brs-master.md)  
> **Companion Details Document:** [Student Implementation Details (`THE HOW`)](../02-tdd/sub-student-details.md)  
> **Persona:** Layer 3 — Student (JIT Workspace Initialization + App-Level Containers)

---

## Overview of Student Goals

The Student logs into the Self-Service Portal with their school/organization email, sees the **Cohort(s)** they are assigned to based on the **Cohort Student Email Group(s)** they belong to, and selects a Cohort to enter. Upon entering the Cohort workspace, the platform checks whether their Student Slice has been initialized — **automatically initializing their Student-Level Singletons (`1` mandatory `sa-<student_slug>`, `Gemini` access, `1` `bkt-<project_id>-<student_slug>`, and `1` `db_<student_slug>` if enabled on the Cohort) into the Cohort's Current Active Provisioning Project (`<cohort_slug>-pNN`) if not yet initialized**. Once initialized, **App Container (`app-<app_slug>`) creation is enabled**, allowing the student to freely mix, match, and delete App-specific services (`GCS Managed Folders` [$\infty$], `Postgres Schemas`, `Cloud Run Services`, and `Vertex AI Search Data Stores & Apps`) within their Cohort's per-student allowance.

---

## Critical User Journeys (CUJs)

### CUJ-ST-01: Log In, Select Cohort (from Email Group Membership) & Auto-Initialize Workspace on Entry
> **As a** Student,  
> **I want to** log in with my email, select a Cohort I am assigned to (based on the Cohort Student Email Groups I belong to), and have the platform automatically check and initialize my Student-Level Singletons (`1` mandatory `sa-<student_slug>`, `Gemini`, `1` `bkt-<project_id>-<student_slug>`, and `1` `db_<student_slug>` if enabled on the Cohort) in the Cohort's Current Active Provisioning Project (`<cohort_slug>-pNN`) as soon as I enter the Cohort workspace,  
> **So that** my baseline student identity, storage bucket, and logical database are provisioned automatically on first entry and **App Container (`app-<app_slug>`) creation is immediately enabled**.

* **Unassigned Fallback:** If my email does not belong to any Cohort Student Email Group, I see a clear *"No Sandbox Assigned"* status displaying my logged-in email so I can request onboarding.
* **Multi-Cohort Selection:** If I belong to multiple Cohort Student Email Groups (e.g., `cs101-fall` and `ai-hackathon`), I can select and switch between my assigned Cohort workspaces, each backed by its own Project Shard assignment, Student-Level Singletons, and App Containers.
* **Automatic Initialization Check on Entry:**
  * If my Student Slice in the selected Cohort is not yet initialized (or if a BU Admin recently enabled an additional Student-Level Singleton service like `GCS` or `Cloud SQL` on the Cohort), entering the workspace automatically runs the initialization pipeline into my assigned shard (or claims a seat in the Cohort's `active_provisioning_project_id` on first entry).
  * Once initialization completes, the **Create App Container (`app-<app_slug>`)** action is unlocked.

---

### CUJ-ST-02: Create an App-Level Container (`app-<app_slug>`)
> **As a** Student (whose Cohort workspace is initialized),  
> **I want to** create a named **App-Level Container (`app-<app_slug>`)** (such as `app-lab1` or `app-capstone`) inside my Cohort workspace,  
> **So that** I have a clean logical container to group the services, folders, schemas, and search indices for a specific assignment or application.

* **Business Pre-condition:** Student Slice initialization for the Cohort is complete (`status == "INITIALIZED"`).
* **Business Inputs:** `App Display Name` and `App Slug` (`<app_slug>`).
* **Business Outcome:** Registers `app-<app_slug>` under my Student Slice in Firebase DB so I can add, view, and manage App-specific services inside that container.

---

### CUJ-ST-03: Mix & Match App-Specific Services Inside an App Container Within My Per-Student Allowance
> **As a** Student,  
> **I want to** provision App-specific services inside any of my App Containers (`app-<app_slug>`) — mixing and matching across my Cohort's per-student service allowance:
> * **GCS Managed Folders (Unlimited $\infty$):** `gs://bkt-<project_id>-<student_slug>/apps/<app_slug>/<folder>/` inside my Student Bucket
> * **Postgres Schemas:** `db_<student_slug>.<app_slug>_<schema>` inside my Student Logical DB
> * **Cloud Run Services:** `run-<student_slug>-<app_slug>-<svc>` running under my `sa-<student_slug>` identity
> * **Vertex AI Search Data Stores & Apps:** `search-ds-<student_slug>-<app_slug>-<name>` (wired to my App's GCS Managed Folder) and `search-app-<student_slug>-<app_slug>-<name>`  
> **So that** I can allocate my per-student quota across one or multiple Apps however my coursework requires (e.g., deploying 3 Cloud Run services in a single App, or 1 Cloud Run service in each of 3 Apps).

* **Business Pre-condition:** The service is currently enabled on the Cohort, and my total deployed count of that service across all my Apps in this Cohort is strictly less than the Cohort's current per-student quantity (`deployed_count < cohort_allowance`).
* **Business Outcome:** Provisions the requested App-specific resource via the Control Tower's Atomic Pipeline, attaches student/app labels and tags, binds usage-only permissions to `user:<student_email>` and `sa-<student_slug>`, and increments my used service counter (`deployed_count / cohort_allowance`).

---

### CUJ-ST-04: Delete Individual App-Specific Services or an Entire App Container to Reclaim Allowance
> **As a** Student,  
> **I want to** delete any individual App-specific service (`GCS Managed Folder`, `Postgres Schema`, `Cloud Run Service`, or `Vertex AI Search Data Store & App`) or delete an entire App Container (`app-<app_slug>`) via the Self-Service Portal when I finish a lab or want to refactor my architecture,  
> **So that** the underlying App-level GCP resources are cleanly torn down and my per-student service allowance is immediately freed up to use in other Apps — without affecting my Student-Level Singletons (`sa-<student_slug>`, `bkt-...`, `db_<student_slug>`) or my other App Containers.

* **Business Inputs:** Selected `App-Specific Service` or `App Container (app-<app_slug>)` to delete.
* **Business Outcome:** Tears down the selected App-level GCP resource(s) via the Atomic Pipeline and decrements `deployed_count` so the student can immediately provision new App services within their allowance.

---

### CUJ-ST-05: Develop & Operate in Google Cloud Console (ClickOps) and Antigravity IDE
> **As a** Student,  
> **I want to** open deep-links from my Student-Level Singletons and App Containers directly into Google Cloud Console (ClickOps) and use the companion Antigravity IDE Guide Skill,  
> **So that** I can upload files to my bucket's managed folders, run SQL DDL/DML inside my Postgres schemas using IAM Database Authentication, preview and tune my Vertex AI Search apps, and deploy container revisions to my Cloud Run services using `sa-<student_slug>` without ever hitting GCP IAM errors.
