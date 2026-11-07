# Student — Secondary Implementation Details (THE HOW)

> **Parent Document:** [01 — Business & Functional Specification](brs-master.md)  
> **Companion CUJ Document:** [Student CUJs (WHY)](sub-student-cuj.md)  
> **Pipeline Source Location:** `src/bff/pipelines/` (Atomic Pipeline)

---

## 1. Student Identity & Baseline Resources (Provisioned at Cohort Mapping)

When a student (`<student_email>`) is mapped to a Cohort Project Shard (`<cohort_slug>-pNN`):
* **`student_slug`:** Email prefix before `@`, normalized to lowercase alphanumeric and hyphens (`^[a-z0-9-]+$`), e.g., `alice.tan@school.edu` $\rightarrow$ `alice-tan`.
* **Baseline Active Nodes (Always Present, Not Deletable by Student):**
  1. **Gemini (Vertex AI):** Enabled via project-level `grp-students-<project_id>` membership + `roles/aiplatform.user` bound to `sa-<student_slug>`.
  2. **Service Account (`sa-<student_slug>`):** `sa-<student_slug>@<project_id>.iam.gserviceaccount.com`, created when the student is mapped to the project. `user:<student_email>` holds `roles/iam.serviceAccountUser` (`iam.serviceAccounts.actAs`) on this Service Account only (no `iam.serviceAccounts.create`, `delete`, or key creation rights).

---

## 2. The 4 Optional Student Services: Create, Usage Rights & Delete Matrix

Students have **no IAM management rights (`setIamPolicy`)** and **no top-level resource `create` or `delete` permissions in GCP**. All creation and deletion execute through the Control Tower's **5-Stage Atomic Pipeline** (`VALIDATING` $\rightarrow$ `CREATING`/`DELETING` $\rightarrow$ `TAGGING_LABELLING` $\rightarrow$ `BINDING_USAGE_RIGHTS` $\rightarrow$ `READY` / `NOT_CONFIGURED`) under lock `locks/student_<student_email>_<project_id>`.

| Optional Service | Resource Name Pattern | What Atomic `CREATE` Provisions | Usage Rights Bound to `user:<student>` & `sa-<student_slug>` (No IAM / No GCP Delete) | What Atomic `DELETE` Tears Down |
| :--- | :--- | :--- | :--- | :--- |
| **1. GCS Bucket** | `bkt-<project_id>-<student_slug>` | Creates bucket with Uniform Bucket-Level Access, initializes empty `rag-docs/` prefix, attaches labels & tag `student=<student_slug>`. | `roles/storage.objectUser` on `bkt-<project_id>-<student_slug>` (create/read/overwrite/delete objects inside the bucket; cannot delete the bucket or modify bucket IAM). | Force-deletes objects and deletes `bkt-<project_id>-<student_slug>` *(blocked if Vertex AI Search Agent is currently active)*. |
| **2. Vertex AI Search Agent** | Data Store: `ds-<student_slug>`<br>Search App: `app-<student_slug>` | *(Requires or auto-creates GCS Bucket first).* Creates GCS Data Connector/Data Store pointed at `gs://bkt-<project_id>-<student_slug>/rag-docs/*` + linked Search Engine (`app-<student_slug>`). | Custom Discovery Engine Usage Role on `ds-<student_slug>` and `app-<student_slug>` via `:setIamPolicy` (search, preview, tune serving configs, view documents; excludes `engines.delete`, `dataStores.delete`, and `setIamPolicy`). | Deletes `app-<student_slug>` and `ds-<student_slug>` via Discovery Engine API. |
| **3. Cloud SQL Database** | Logical DB: `db_<student_slug>`<br>(on `sql-<project_id>`) | Creates logical Postgres DB `db_<student_slug>` on the project shard's shared `sql-<project_id>` instance; registers `<student_email>` and `sa-<student_slug>` as `CLOUD_IAM_USER` / `CLOUD_IAM_SERVICE_ACCOUNT`. | Project-level `roles/cloudsql.client` + `roles/cloudsql.instanceUser` (via student group) + SQL `REVOKE CONNECT ON DATABASE db_<student_slug> FROM PUBLIC; GRANT ALL PRIVILEGES ON DATABASE db_<student_slug> TO "<student_email>", "sa-<student_slug>@...";` with `CONNECTION LIMIT 5`. | Terminates active backends on `db_<student_slug>` and runs `DROP DATABASE db_<student_slug>;`. |
| **4. Cloud Run Service** | `run-<student_slug>` | Deploys starter container revision to `run-<student_slug>` running as `serviceAccountName = sa-<student_slug>@...`, attaches labels & tag `student=<student_slug>`. | Custom Cloud Run Service Usage Role on `run-<student_slug>` (`run.services.get`, `run.services.update`, `run.routes.invoke`, `run.operations.get`; excludes `run.services.delete` and `run.services.setIamPolicy`). | Deletes Cloud Run service `run-<student_slug>` via Cloud Run v2 API. |

---

## 3. Dependency Rules Between the 4 Optional Services

1. **Service Account Prerequisite:** Already satisfied automatically because `sa-<student_slug>` is created when the student is mapped to the project shard.
2. **Vertex AI Search $\leftrightarrow$ GCS Bucket Dependency:**
   * **On Create:** `Vertex AI Search Agent` points its GCS Data Connector at `gs://bkt-<project_id>-<student_slug>/rag-docs/*`. If `bkt-<project_id>-<student_slug>` is not yet configured when the student configures `Vertex AI Search Agent`, the Atomic Intent Compiler automatically includes creating `bkt-<project_id>-<student_slug>` as Step 1 of the pipeline run.
   * **On Delete:** A student cannot delete `bkt-<project_id>-<student_slug>` while `ds-<student_slug>` / `app-<student_slug>` is active (must delete `Vertex AI Search Agent` first).
