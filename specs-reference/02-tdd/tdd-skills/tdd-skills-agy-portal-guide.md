# Antigravity Portal Guide Skill Specification (`tdd-skills-agy-portal-guide.md`)

> **Domain Master:** [tdd-skills-master.md](tdd-skills-master.md)  
> **Source Location:** `src/agy-skill/SKILL.md`

---

## 1. Skill Metadata & Triggering

```yaml
---
name: learning-sandbox-guide
description: Companion guide for students using the Learning Sandbox Self-Service Portal. Explains how to locate your assigned Cohort Project Shard (<cohort_slug>-pNN), authenticate using your mandatory Student Service Account (sa-<student_slug>), and connect code inside Antigravity to your singleton GCS Bucket (bkt-<project_id>-<student_slug>), singleton Cloud SQL Postgres DB (db_<student_sql_slug>), and App-Container resources (app-<app_slug>: Managed Folders, Postgres Schemas, Cloud Run services, and Vertex AI Search apps).
---
```

---

## 2. Core Workflows Covered in `SKILL.md`

1. **Step 1 — Entering Your Cohort Workspace (Auto-Initialization):**
   * Log into the Learning Sandbox Portal and select your Cohort (matched via your Cohort Student Email Group).
   * Entering the Cohort workspace automatically assigns you to your Cohort's active Project Shard (`<cohort_slug>-pNN`) and initializes your Student-Level Singletons (`sa-<student_slug>`, `Gemini`, `bkt-<project_id>-<student_slug>`, `db_<student_sql_slug>`).
2. **Step 2 — Authenticating Local / Antigravity Code via Service Account Impersonation:**
   ```bash
   gcloud config set project <cohort_slug>-pNN
   gcloud auth application-default login \
     --impersonate-service-account=sa-<student_slug>@<cohort_slug>-pNN.iam.gserviceaccount.com
   ```
3. **Step 3 — Consuming App-Level Services (`app-<app_slug>`):**
   * **GCS Managed Folders (`gs://bkt-<project_id>-<student_slug>/apps/<app_slug>/<folder>/`):** Read/write objects scoped to the App folder.
   * **Postgres Schemas (`db_<student_sql_slug>.<app_slug>_<schema>`):** Connect via Cloud SQL Python Connector with `enable_iam_auth=True` and `options="-c search_path=<app_slug>_<schema>"`.
   * **Cloud Run Services (`run-<student_slug>-<app_slug>-<svc>`):** Deploy new container revisions via `gcloud run services update run-<student_slug>-<app_slug>-<svc> --image=... --service-account=sa-<student_slug>@...`.
   * **Vertex AI Search (`search-ds-<student_slug>-<app_slug>-<name>` & `search-app-...`):** Upload documents to `gs://bkt-.../apps/<app_slug>/<name>-docs/` and query the Search Engine via Discovery Engine SDK.
