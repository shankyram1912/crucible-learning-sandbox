# Student — Secondary Implementation Details (`THE HOW`)

> **Master Document:** [Business Requirements Specification — Master (`THE WHAT`)](../01-brs/brs-master.md)
> **TDD Master Document:** [Technical Design & LLD — Master](tdd-master.md)  
> **Companion CUJ Document:** [Student CUJs (`THE WHY`)](../01-brs/brs-student-cuj.md)  
> **Pipeline Source Location:** `src/bff/pipelines/` (Atomic Pipeline — Student Workspace Auto-Init + App Container CRUD)

---

## 1. Cohort Resolution & Automatic Student Workspace Initialization on Entry

When a student (`<student_email>`, normalized to `student_slug` from the email prefix before `@`, e.g., `alice.tan@school.edu` $\rightarrow$ `alice-tan`, SQL slug `alice_tan`) logs into the Portal:

1. **Cohort Resolution via Cohort Student Email Groups:**
   * The BFF resolves which **Cohort Student Email Groups** (`cohort_student_groups`) include `<student_email>` as a member.
   * If zero Cohort groups match, the Portal returns `status = "UNASSIGNED"` (*"No Sandbox Assigned"*).
   * If one or more Cohort groups match, the student selects a Cohort to enter.
2. **Workspace Entry Check & Shard Seat Allocation (`active_provisioning_project_id`):**
   * When the student enters the workspace for `<cohort_slug>`, the BFF inspects `/environments/{mode}/cohorts/{cohort_slug}/students/{student_slug}`:
   * **Case A — First-Time Entry (`project_id` not yet assigned):**
     * Inside a Firestore transaction on the Cohort document, the BFF assigns the student to the Cohort's **`active_provisioning_project_id`** (`<cohort_slug>-pNN`) and increments that shard's `initialized_student_count` (`+1`).
     * If `initialized_student_count` reaches `students_per_project` (default `100`), `active_provisioning_project_id` automatically advances to the next shard in `<cohort_slug>-p01..pKK` with remaining capacity (`< 100`).
   * **Case B — Returning Entry (`project_id` already assigned):**
     * Uses the student's existing assigned `project_id` (`<cohort_slug>-pNN`), even if the Cohort Admin has since switched `active_provisioning_project_id` to another shard for new students.
3. **Automatic Student-Level Singleton Initialization (Atomic Pipeline):**
   * On workspace entry, the BFF checks whether all Student-Level Singletons currently enabled on the Cohort (`policy_enabled_services`) have been initialized for this student.
   * **If any enabled singleton is not yet initialized**, the BFF automatically triggers the **Student Workspace Init** Atomic Pipeline under `locks/student_<student_slug>_<project_id>` to provision the missing singleton(s):
     1. **`1` Service Account (Mandatory — Always Created):** Creates `sa-<student_slug>@<project_id>.iam.gserviceaccount.com` and binds `roles/iam.serviceAccountUser` (`iam.serviceAccounts.actAs`) on `sa-<student_slug>` to `user:<student_email>`.
     2. **`Gemini` Access (`if policy_enabled_services.gemini`):** Binds `roles/aiplatform.user` to `serviceAccount:sa-<student_slug>@...` (in addition to the student's Cohort group access).
     3. **`1` Student GCS Bucket (`if policy_enabled_services.gcs`):** Creates `bkt-<project_id>-<student_slug>` with Uniform Bucket-Level Access and binds `roles/storage.objectUser` to `user:<student_email>` and `serviceAccount:sa-<student_slug>@...`.
     4. **`1` Student Cloud SQL Logical DB (`if policy_enabled_services.cloud_sql`):** Creates logical Postgres database `db_<student_sql_slug>` on the shard's shared `sql-<project_id>` instance, registers `<student_email>` (`CLOUD_IAM_USER`) and `sa-<student_slug>@...` (`CLOUD_IAM_SERVICE_ACCOUNT`), and runs `REVOKE CONNECT ON DATABASE db_<student_sql_slug> FROM PUBLIC; GRANT ALL PRIVILEGES ON DATABASE db_<student_sql_slug> TO "<student_email>", "sa-<student_slug>@...";` with connection limit per `service_sizes.connection_limit_per_student`.
   * **Unlocking App Creation:** Once `workspace_init_status == "INITIALIZED"`, the student's **Create App Container (`app-<app_slug>`)** capability is enabled.

---

## 2. App-Level Containers (`app-<app_slug>`, Managed via Atomic Pipeline)

Once their Student Slice is initialized, a student can create multiple **App-Level Containers (`app-<app_slug>`)** and freely **mix, match, and delete** App-specific services across their Apps within the Cohort's per-student service allowance (`min` from Service Catalog Config + Cohort override):

| App-Specific Service | Resource Naming Pattern | What Atomic `CREATE` Provisions | Usage Rights Bound to `user:<student>` & `sa-<student_slug>` (No IAM / No GCP Top-Level Delete) | What Atomic `DELETE` Tears Down (Frees Student Allowance) |
| :--- | :--- | :--- | :--- | :--- |
| **1. GCS Managed Folder** | `gs://bkt-<project_id>-<student_slug>/apps/<app_slug>/<folder>/` | Creates a GCS Managed Folder (`google.storage.control.v2.StorageControl.CreateManagedFolder`) inside the student's singleton bucket `bkt-<project_id>-<student_slug>`. **Allowance: Unlimited ($\infty$)** | Inherited `roles/storage.objectUser` on `bkt-<project_id>-<student_slug>` (full object read/write/delete inside the managed folder). | Deletes objects under `apps/<app_slug>/<folder>/` and removes the Managed Folder *(blocked if an active Vertex AI Search Data Store in that App is wired to that folder)*. |
| **2. Postgres Schema** | `db_<student_sql_slug>.<app_slug>_<schema>` | Connects to `sql-<project_id>/<db_<student_sql_slug>>` and runs `CREATE SCHEMA <app_slug>_<schema> AUTHORIZATION "<student_email>"; GRANT ALL ON SCHEMA <app_slug>_<schema> TO "sa-<student_slug>@...";`. | Full DDL/DML (`CREATE TABLE`, `INSERT`, `SELECT`, `DROP TABLE`) inside `<app_slug>_<schema>` via IAM DB Auth. | Runs `DROP SCHEMA <app_slug>_<schema> CASCADE;` inside `db_<student_sql_slug>` and decrements the student's schema counter (`deployed_count - 1`). |
| **3. Cloud Run Service** | `run-<student_slug>-<app_slug>-<svc>` | Deploys starter container revision to `run-<student_slug>-<app_slug>-<svc>` running as `serviceAccountName = sa-<student_slug>@...`, sized per the Cohort's pinned `service_sizes` (CPU/memory/max instances), with labels `{ student = <student_slug>, app = <app_slug> }`. | Custom Cloud Run Service Usage Role bound on `run-<student_slug>-<app_slug>-<svc>` (`run.services.get`, `run.services.update`, `run.routes.invoke`, `run.operations.get`; excludes `run.services.delete` and `run.services.setIamPolicy`). | Deletes `run-<student_slug>-<app_slug>-<svc>` via Cloud Run v2 API and decrements the student's Cloud Run counter (`deployed_count - 1`). |
| **4. Vertex AI Search Data Store & App** | Data Store: `search-ds-<student_slug>-<app_slug>-<name>`<br>Search App: `search-app-<student_slug>-<app_slug>-<name>` | *(Auto-creates Managed Folder `apps/<app_slug>/<name>-docs/` if needed).* Creates GCS Data Connector (`search-ds-...`) pointed at `gs://bkt-.../apps/<app_slug>/<name>-docs/*` + linked Search Engine (`search-app-...`). | Custom Discovery Engine Usage Role bound on `search-ds-...` and `search-app-...` via `:setIamPolicy` (search, preview, tune serving configs, import/view documents; excludes `engines.delete`, `dataStores.delete`, and `setIamPolicy`). | Deletes `search-app-<student_slug>-<app_slug>-<name>` and `search-ds-<student_slug>-<app_slug>-<name>` via Discovery Engine API and decrements the student's Vertex Search counter (`deployed_count - 1`). |

---

## 3. Pooled Per-Student Allowance Enforcement & Non-Destructive Reduction

1. **Pre-Flight Allowance Gate on Atomic `CREATE`:**
   * For any countable App-level service $s \in \{\texttt{cloud\_sql\_schema}, \texttt{cloud\_run}, \texttt{vertex\_search}\}$, the Atomic Pipeline sums the student's active instances of $s$ across **all** `app-<app_slug>` containers in that Cohort project:
     $$\text{total\_deployed}(s) = \sum_{\text{app} \in \text{student.apps}} \text{count}(\text{app}, s)$$
   * **Gate Rule:** `CREATE` is allowed if and only if:
     $$\texttt{cohort.policy\_enabled\_services}[s] == \texttt{true} \quad \land \quad \text{total\_deployed}(s) < \texttt{cohort.per\_student\_quantity}[s]$$
2. **Behavior When a BU Admin Disables a Service or Lowers Quantity:**
   * If `cohort.policy_enabled_services[s]` is later set to `false` or `cohort.per_student_quantity[s]` is lowered below a student's current $\text{total\_deployed}(s)$, existing deployed instances remain `READY` and functional (`total_deployed / new_quantity`).
   * The student can continue using or deleting their existing App-specific services; new `CREATE` calls for $s$ are simply blocked until `policy_enabled_services[s] == true` and $\text{total\_deployed}(s) < \texttt{cohort.per\_student\_quantity}[s]$.
3. **Whole-App Container Deletion (`DELETE app-<app_slug>`):**
   * Deleting an App Container iterates through all services inside `app-<app_slug>` in dependency order (`Vertex AI Search` $\rightarrow$ `Cloud Run` $\rightarrow$ `Postgres Schemas` $\rightarrow$ `GCS Managed Folders`), tears them down via the Atomic Pipeline, decrements the student's `total_deployed` counters, and removes the `app-<app_slug>` container record from Firebase DB.

---

## 4. Single-Action Lock Matrix for Student Operations

| Operation | Lock Document in Firebase DB | Lock Lease TTL | Blocked Concurrent Actors |
| :--- | :--- | :--- | :--- |
| **Auto-Initialize Student Workspace on Cohort Entry (`sa-<student_slug>`, `bkt-...`, `db_<student_slug>`)** | `locks/student_<student_slug>_<project_id>` | 2 minutes | Concurrent initializations or App mutations on that student's slice |
| **Create / Delete App Container (`app-<app_slug>`) or App-Specific Service (`Managed Folder`, `DB Schema`, `Cloud Run`, `Vertex AI Search`)** | `locks/student_<student_slug>_<project_id>` | 2 minutes | Concurrent mutations on that specific student's slice in that project shard (all other students in `<cohort_slug>-pNN` continue operating in parallel without lock contention) |
