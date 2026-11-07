# Student — Critical User Journeys (THE WHY)

> **Parent Document:** [01 — Business & Functional Specification](../01-business-spec.md)  
> **Companion Details Document:** [Student Implementation Details (HOW)](student-details.md)  
> **Persona:** Persona 3 — Student (Sandbox Builder)

---

## Overview of Student Goals
The Student wants to log into the Self-Service Portal with their school/organization email, immediately see their pre-configured **Gemini** and **Service Account (`sa-<student_slug>`)** baseline inside their assigned Cohort Project Shard, and self-serve the **creation and deletion** of up to **4 optional GCP services** (`GCS Bucket`, `Vertex AI Search Agent`, `Cloud SQL Database`, `Cloud Run`) in seconds — then use Google Cloud Console ClickOps and Antigravity IDE to build their application without hitting IAM or permission errors.

---

## Critical User Journeys (CUJs)

### CUJ-ST-01: Log In and Resolve Cohort Sandbox (Single, Multi-Cohort, or Unassigned)
> **As a** Student,  
> **I want to** log in with my email and automatically load my assigned Cohort Project Shard (or switch between my enrolled Cohorts if I belong to more than one),  
> **So that** I immediately see my active **Gemini** and **Service Account (`sa-<student_slug>`)** baseline and the optional services available for my course without needing to know GCP folder hierarchies.

* **Unassigned Fallback:** If my email has not yet been mapped to any Cohort by a BU Admin, I see a clear *"No Sandbox Assigned"* status with my email address so I can request onboarding.
* **Empty Optional Services Prompt:** If I have not configured any optional services in my Cohort project yet, the portal informs me that no optional services are currently set up and invites me to configure one.

---

### CUJ-ST-02: Configure a Dedicated GCS Bucket
> **As a** Student,  
> **I want to** configure my personal GCS Bucket (`bkt-<project_id>-<student_slug>`) via the portal,  
> **So that** I get an isolated storage bucket (pre-initialized with a `/rag-docs/` folder) where I and my `sa-<student_slug>` Service Account have full object read/write/delete usage rights in Google Cloud Console ClickOps and code.

---

### CUJ-ST-03: Configure a Pre-Wired Vertex AI Search Agent (Option A)
> **As a** Student,  
> **I want to** configure a Vertex AI Search Agent via the portal,  
> **So that** the platform automatically creates both my GCS Folder Data Connector (`ds-<student_slug>` pointed at `gs://bkt-<project_id>-<student_slug>/rag-docs/*`) and my linked Search App (`app-<student_slug>`) with usage rights granted to me and my `sa-<student_slug>`, allowing me to upload documents and tune/query my Search Agent in Google Cloud Console ClickOps without hitting the Discovery Engine `CreateEngine` empty-IAM lockout.

---

### CUJ-ST-04: Configure an Isolated Cloud SQL PostgreSQL Database
> **As a** Student,  
> **I want to** configure a Cloud SQL Database via the portal,  
> **So that** the platform provisions an isolated logical PostgreSQL database (`db_<student_slug>`) on my project shard's pre-warmed Cloud SQL instance in ~2 seconds and grants IAM Database Authentication to me and my `sa-<student_slug>` with zero database passwords to manage.

---

### CUJ-ST-05: Configure a Cloud Run Service Running as `sa-<student_slug>`
> **As a** Student,  
> **I want to** configure a Cloud Run Service (`run-<student_slug>`) via the portal,  
> **So that** a tagged, pre-wired Cloud Run service running under my `sa-<student_slug>` identity is created for me, allowing me to deploy new container revisions and view logs in ClickOps or Antigravity IDE while seamlessly calling Gemini, my GCS Bucket, my Cloud SQL DB, and my Vertex AI Search Agent.

---

### CUJ-ST-06: Delete Any Provisioned Optional Service via the Portal
> **As a** Student,  
> **I want to** delete any of my 4 optional services (`GCS Bucket`, `Vertex AI Search Agent`, `Cloud SQL Database`, or `Cloud Run`) directly through the Self-Service Portal when I want to reset or clean up my work,  
> **So that** the underlying GCP resource is cleanly torn down and the service slot returns to unconfigured so I can provision a fresh instance anytime.
