# Crucible (Learning Sandbox): Student & Designated User Journeys

> Master: [brs-master.md](brs-master.md) · Technical design: [tdd-master.md](../02-tdd/tdd-master.md)
> Persona: **Playground User — Student or Designated User** (members of the existing Google groups mapped 1-to-1 to a playground's template user group slots at creation)
> Admin Acting on Behalf: BU Admins ([BU-06](brs-bu-admin-cuj.md)), Playground Admins (for their assigned playground), and IT Admins ([IT-08](brs-it-admin-cuj.md)) can execute these workspace and app-container journeys on behalf of a playground user, recording the acting admin on every job.

Each journey is framed as *"As a playground user, I want to ..., to accomplish ..."*, followed by the design decisions behind it. Every change runs as a **tracked job**.

---

## ST-01 Select a playground and auto-initialize my workspace on entry
As a playground user, I want to sign in, see the playgrounds my user groups are mapped to, and have the platform automatically initialize my workspace and user singleton resources when I first enter an active playground, to accomplish getting my isolated baseline identity and singleton resources ready without manual cloud setup.

- **Seeing playgrounds and status:**
  - I see every playground whose mapped user groups I belong to, and I can work across multiple playgrounds independently (each backed by its own shard placement, workspace, user singleton resources, and app containers).
  - If I hold no admin role and do not belong to any mapped user group, I see a *"No Sandbox Assigned"* state in the portal UI displaying my signed-in email.
  - If my portal access to a playground is **suspended** ([BU-05](brs-bu-admin-cuj.md)), or if a playground is **decommissioned** ([BU-08](brs-bu-admin-cuj.md) / [IT-07](brs-it-admin-cuj.md)), the playground still appears in my list clearly marked **Suspended** or **Decommissioned** as appropriate: I can view my workspace, app containers, and own job history read-only, but **all actions are blocked** until I am restored or the playground is recommissioned.
- **Automatic workspace initialization on first entry (tracked job, done once):**
  - On first entry into an active playground, the platform automatically places me in a project shard with free capacity (up to the template's `max_students_per_project`) and runs a **tracked job** to create **all** my **user singleton resources** in one go — exactly one per mandatory service that defines a singleton (illustrative AI-template examples: service account `sa-<user>`, Gemini access, Cloud Storage bucket `bkt-<project>-<user>`, and Cloud SQL logical database `db_<user>`).
  - Because only mandatory services define singletons, my workspace is **never re-initialized**: when an admin enables an additional optional service later ([BU-03](brs-bu-admin-cuj.md)), I simply gain new app resource types.
  - **Capacity exhausted:** if every shard of the playground is already full, my entry is blocked with a clear capacity-exhausted state until an admin raises the playground's expected number of students ([BU-04](brs-bu-admin-cuj.md)), which adds shards.
  - Once workspace initialization completes, creating **app containers** (`app-<name>`) is unlocked.

---

## ST-02 Create an app container (`app-<name>`)
As a playground user, I want to create a named app container (such as `app-lab1` or `app-capstone`) inside my initialized workspace, to accomplish organizing the app resources for a specific assignment, lab, or application cleanly.

- **Pre-condition:** my workspace in the playground is initialized, my portal access is active (not suspended), and the playground is active (not decommissioned).
- Registers `app-<name>` inside my workspace in the platform so I can provision, inspect, and delete app resources grouped under that container.

---

## ST-03 Provision app resources inside an app container within my allowance
As a playground user, I want to provision app resources from the playground's enabled services inside any of my app containers — mixing and matching across my per-user allowance — to accomplish allocating my quota across one or multiple apps however my coursework requires.

- Available **app resource** types come from the services enabled on the playground's pinned template version (illustrative AI-template examples: Cloud Storage managed folders `apps/<app>/<folder>/` inside `bkt-<project>-<user>`, Postgres schemas `db_<user>.<app>_<schema>`, Cloud Run services `run-<user>-<app>-<svc>` running under `sa-<user>`, and Vertex AI Search data stores and apps `search-ds-<user>-<app>-<name>` / `search-app-<user>-<app>-<name>`).
- **Two-level cap check:** provisioning is allowed when the service is enabled on the playground, my total deployed count of that resource across **all** my app containers in this playground is below the playground's configured **per-user allowance** (`min` up to a finite `max` — there is no unlimited allowance), **and** my project shard has remaining capacity within the service's **quota per project**.
- Provisioning runs as a **tracked job** through the Control Tower pipeline, binds usage-only permissions to my user identity and `sa-<user>`, and increments my used allowance count.

---

## ST-04 Delete an app resource or an entire app container to reclaim allowance
As a playground user, I want to delete an individual app resource or delete an entire app container (`app-<name>`) through the platform when I finish a lab or refactor my work, to accomplish tearing down those app-level GCP resources cleanly and freeing up my per-user allowance for other apps.

- Deleting an individual app resource runs as a **tracked job** that tears down that GCP resource and decrements my used count so the allowance can immediately be reused in the same or another app container.
- Deleting an entire app container (`app-<name>`) runs as a **tracked job** that tears down all app resources inside that container and frees their allowance, **without affecting my user singleton resources** (such as `sa-<user>`, `bkt-<project>-<user>`, or `db_<user>`) or any of my other app containers.

---

## ST-05 Develop and operate in Google Cloud Console and Antigravity IDE
As a playground user, I want to open direct links from my user singleton resources and app containers into Google Cloud Console (ClickOps) and use the companion Antigravity IDE guide skill, to accomplish building, testing, and deploying inside my provisioned resources without hitting GCP IAM errors.

- **Usage rights only in GCP:** I hold data-plane and operational usage rights on my own provisioned singleton and app resources (for example uploading files to my bucket's managed folders, running SQL inside my Postgres schemas using IAM database authentication, tuning my Vertex AI Search apps, and deploying container revisions to my Cloud Run services running as `sa-<user>`), without IAM-change rights or top-level GCP resource create/delete permissions outside the platform.
- The companion **Antigravity IDE guide skill** helps me navigate the self-service portal/CLI and consume my provisioned sandbox services from my IDE (it is a companion guide, not a direct provisioning bypass).

---

## ST-06 View my own tracked jobs
As a playground user, I want to view my own tracked jobs in each playground, to accomplish monitoring progress and troubleshooting my workspace initialization and app-resource operations.

- I see the status, progress, errors, and timestamps of **my own jobs** in each playground (workspace initialization and app-container or app-resource creations and deletions, including jobs executed on my behalf by an admin), also while I am suspended or the playground is decommissioned.
- I cannot see other users' jobs, Playground Folder jobs, or playground-level admin jobs.

---

## Not in the platform (for playground users)
- Creating, deleting, or changing IAM on top-level GCP resources directly outside the platform.
- Deleting or resetting user singleton resources, or deleting my workspace slice.
- Choosing or switching which project shard my workspace lands in.
- Viewing other users' workspaces, app containers, or tracked jobs.
