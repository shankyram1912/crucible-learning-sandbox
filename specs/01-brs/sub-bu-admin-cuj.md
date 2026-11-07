# BU Admin — Critical User Journeys (THE WHY)

> **Parent Document:** [01 — Business & Functional Specification](brs-master.md)  
> **Companion Details Document:** [BU Admin Implementation Details (HOW)](sub-bu-admin-details.md)  
> **Persona:** Persona 2 — BU Admin (School / Department / Cohort Operator)

---

## Overview of BU Admin Goals
The BU Admin (Faculty Lead, Lab Coordinator, or Department Admin) operates within the **School Folder(s)** or **Department Sub-folder(s)** delegated to their BU Admin IAM Group. Their mission is to **create and size academic/lab Cohorts, initialize Project Shards with the right GCP services, onboard students via Cloud Identity or CSV, manage per-project spend limits, support students, and teardown cohorts at the end of a term** — all without waiting on Central IT.

---

## Critical User Journeys (CUJs)

### CUJ-BU-01: Create & Initialize a Cohort Based on Expected Student Size
> **As a** BU Admin,  
> **I want to** create a new Cohort Folder under my School Folder or Department Sub-folder by specifying the Cohort slug, expected student count ($N$), Cohort budget, default project shard limit, and which GCP services to enable,  
> **So that** the platform automatically initializes $\lceil N / 100 \rceil$ Project Shards (`<cohort_slug>-p01..pNN`) with the required APIs, shared infrastructure, and budgets weeks before student enrollment closes.

* **Business Inputs:**
  * `Parent Folder` (School Folder or Department Sub-folder)
  * `Cohort Name` & `Cohort Slug` (e.g., `cs101-fall`)
  * `Expected Student Size (N)` (e.g., `350` $\rightarrow$ initializes `4` shards: `cs101-fall-p01` .. `cs101-fall-p04`)
  * `Pooled Cohort Folder Budget` (e.g., `$8,000`) & `Default Project Shard Limit` (e.g., `$3,000`)
  * `Enabled Project-Level Terraform Services`: `Gemini (Default)`, `GCS`, `Cloud Run`, `Vertex AI Search`, `Shared Cloud SQL Postgres`
* **Business Outcome:** Cohort Folder and $\lceil N / 100 \rceil$ Project Shards are initialized via Terraform (`src/terraform/buadmin`), with outputs persisted to Firebase DB and `N_shards * 100` empty student seats ready for assignment.

---

### CUJ-BU-02: Drill Into a Project Shard to Add Services or Override Project Spend Limit
> **As a** BU Admin,  
> **I want to** drill down into a specific Project Shard (`<cohort_slug>-pNN`) to enable an additional Terraform-managed project service (such as turning on Shared Cloud SQL for that shard) or set a Per-Project Spend Limit Override,  
> **So that** uneven usage across student shards (e.g., a heavy capstone shard needing a `$5,000` limit instead of the `$3,000` default) is accommodated without hitting premature alerts while staying within the pooled Cohort budget.

* **Business Inputs:** `Target Project Shard ID`, updated `Enabled Services` flags, and/or `Project Limit Override Amount`.
* **Business Outcome:** Updates that project shard's Terraform configuration and `google_billing_budget` under a single-action lock.

---

### CUJ-BU-03: Onboard Students to a Cohort via Cloud Identity Users/Groups or CSV
> **As a** BU Admin,  
> **I want to** map Cloud Identity Users, Cloud Identity User Groups, or a CSV of student emails to an initialized Cohort,  
> **So that** students are automatically sharded across the Cohort's `<cohort_slug>-p01..pNN` projects ($\le 100$ students per project) and each student's personal Service Account (`sa-<student_slug>`) and baseline Gemini access are automatically provisioned.

* **Business Inputs:** `Target Cohort` + selected `Cloud Identity Group(s)` / `Cloud Identity User(s)` / uploaded `CSV email list`.
* **Business Outcome:**
  * Bin-packs students across `<cohort_slug>-p01..pNN` ($\le 100$ seats per shard).
  * Adds each student to their assigned shard's Student IAM Group (`grp-students-<project_id>`).
  * Creates each student's dedicated Service Account (`sa-<student_slug>@<project_id>.iam.gserviceaccount.com`) and binds baseline usage permissions (`iam.serviceAccounts.actAs` on `sa-<student_slug>` and default Gemini access).
  * Records the student-to-project mapping in Firebase DB (supporting students enrolled in multiple cohorts simultaneously).

---

### CUJ-BU-04: Expand a Cohort When Enrollment Grows Beyond Current Shard Capacity
> **As a** BU Admin,  
> **I want to** increase a Cohort's student size (e.g., from `350` to `430` students) when enrollment exceeds existing shard capacity,  
> **So that** an additional Project Shard (`<cohort_slug>-p05`) is initialized non-disruptively alongside `p01..p04`.

---

### CUJ-BU-05: Search for Any Student to Inspect or Manage Their Sandbox
> **As a** BU Admin,  
> **I want to** search for a student by email or name across my School/Department folders to see which Cohort(s) and Project Shard(s) they belong to and inspect their provisioned services,  
> **So that** I can verify their progress or trigger service creation/deletion on their behalf (via inherited Student capabilities) if they need assistance during a lab.

---

### CUJ-BU-06: Teardown a Cohort at End of Semester or Hackathon
> **As a** BU Admin,  
> **I want to** execute a full **Cohort Teardown** when a course or hackathon concludes,  
> **So that** all student slices, shared Cloud SQL instances, project shards (`<cohort_slug>-p01..pNN`), budgets, and the Cohort Folder are cleanly destroyed (`terraform destroy`) and billing stops immediately.
