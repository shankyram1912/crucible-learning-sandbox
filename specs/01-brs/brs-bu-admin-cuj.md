# Crucible (Learning Sandbox): BU Admin & Playground Admin Journeys

> Master: [brs-master.md](brs-master.md) · Technical design: [tdd-master.md](../02-tdd/tdd-master.md)
> Personas:
> - **BU Admin:** members of `grp-lsb-bu-admins@`, managing the Playground Folders whose BU Admin group they belong to
> - **Playground Admin:** members of a playground's optional Playground Admin group (for example course TAs), with the same rights as a BU Admin **scoped to that single playground**. Playground Admins **cannot create, decommission, or recommission playgrounds**, and see no Playground Folder-level jobs.

Each journey is framed as *"As a BU Admin, I want to ..., to accomplish ..."*, followed by the design decisions behind it and its Playground Admin scope. Every change runs as a **tracked job** — jobs are the platform's audit trail. All mutating journeys require an **active** playground (and an active Playground Folder); a decommissioned playground is read-only, including its job history, until recommissioned (BU-09).

---

## BU-01 Create a playground
As a BU Admin, I want to create a playground from a template in a Playground Folder I manage, to accomplish a ready, budgeted environment for a course, lab, or hackathon.

- **Allowed for:** BU Admins (in Playground Folders whose BU Admin group I belong to, checked live per request) and IT Admins — **not Playground Admins**.
- Creating a playground runs as a **tracked job**; projects are created only by the pipeline and linked to the Playground Folder's billing account.
- **Template (`current` version, permanently pinned):** I pick an active playground template. New playgrounds always start on that template's `current` version and stay **permanently pinned to that template version for life** (never upgraded).
- **Expected students and shards:** I enter the expected number of students. The platform creates $\lceil \text{expected\_students} \div \text{max\_students\_per\_project} \rceil$ project shards, rounded up.
- **BU tags (un-cataloged, immutable once created):** I enter literal `bu-tracking-code` and `bu-subcategory` tag values (not drawn from a catalog — what you see is what you get; never set on the Playground Folder, and **cannot be updated once created**). Both inherited IT folder tags and BU playground tags are copied onto every project shard as billing labels.
- **Budgets:** I must set a **required playground budget** (in the Playground Folder's billing account currency, with platform-wide 50, 75, 90 and 100% alert levels, created by the platform), and I can set an **optional per-project shard budget** ($\le$ the playground budget, as a default across shards or overridden on individual shards; new shards added later inherit the default).
- **Optional Playground Admin group (immutable once created):** I can optionally name **at most one** existing Google group (for example the course's TAs), which **cannot be changed or swapped after creation** (membership is managed in the Admin console). Its members get the same rights as BU Admins for this playground only, except creating, decommissioning, or recommissioning playgrounds.
- **Mapped user groups (fixed at creation):** I map **strictly one existing Google group** of playground users (students or other designated users) to each user group slot expected by the template. The platform never creates groups or changes their members, GCP IAM roles come from each service's Terraform module, and **mapped user groups cannot be changed or swapped once the playground is created** (membership is managed in the Admin console).
- **Initial services and per-user allowances:** mandatory services are always enabled and cannot be unchecked; enabled-by-default services start enabled and can be unchecked before creation; disabled-by-default services start disabled and can be turned on (prerequisite services are added automatically). Only mandatory services give users singleton resources; optional services add app resources only. For each enabled service, I set the per-user allowance from `min` (the minimum and default) up to the finite `max` ceiling, subject to the project shard quota.
- **Project owners:** on every project shard, the folder's BU Admin group, the IT Admins group, and — if configured — the Playground Admin group each get full `roles/owner` access.

---

## BU-02 Update a playground's name or budgets
As a BU Admin, I want to rename a playground or update its playground budget and optional per-project shard budgets, to accomplish keeping its name and spend limits aligned with the course.

- **Allowed for:** BU Admins, Playground Admins (for their assigned playground), and IT Admins.
- Renaming and updating budgets each run as a **tracked job**; budget updates adjust the required playground budget and/or optional per-project shard budgets ($\le$ playground budget, default or per-shard override) in the Playground Folder's billing account currency.
- **Immutable once created:** a playground's **template version, BU tags (`bu-tracking-code`, `bu-subcategory`), optional Playground Admin group, and mapped user groups cannot be changed, swapped, or upgraded** after creation.

---

## BU-03 Configure playground services and per-user allowances
As a BU Admin, I want to enable additional optional services from the playground's template or adjust per-user allowances, to accomplish evolving the playground safely as course needs grow.

- **Allowed for:** BU Admins, Playground Admins (for their assigned playground), and IT Admins.
- Mandatory services are always enabled and cannot be unchecked; **a playground's template version can never be upgraded**.
- Services are **add-only**: I can enable additional optional services defined in the playground's pinned template version (required prerequisite services are added automatically), and once enabled a service stays enabled for the life of the playground.
- Each configuration change creates a new configuration version and runs as a **tracked job** applied across every project shard in the playground. Because optional services never define user singletons, enabling one only adds new **app resource** types for users — **no existing workspace is ever re-initialized**.
- I can adjust each enabled service's **per-user allowance** within `[min, max]` (bounded by the project shard quota). Lowering an allowance is non-destructive: it only gates new creations and leaves existing user resources untouched.

---

## BU-04 Expand playground student capacity
As a BU Admin, I want to increase a playground's expected student count when enrollment grows or every shard is full, to accomplish adding project shard capacity without disturbing existing users.

- **Allowed for:** BU Admins, Playground Admins (for their assigned playground), and IT Admins.
- Expected student count is **grow-only** (never shrunk).
- When $\lceil \text{new\_expected\_students} \div \text{max\_students\_per\_project} \rceil$ exceeds the current project count, a **tracked job** adds new project shards (`p(K+1)..pM`) initialized with all currently enabled playground services and the default per-project shard budget (if one is set), leaving existing shards (`p01..pK`) and workspaces untouched.
- **Capacity exhausted:** when every shard is full, new users entering the playground are blocked with a capacity-exhausted state; raising the expected student count here is the admin action that lets them in.

---

## BU-05 Suspend or restore a user's portal access
As a BU Admin, I want to suspend or restore a user's portal access to a playground, to accomplish blocking or re-enabling platform actions by that user without touching their underlying GCP resources.

- **Allowed for:** BU Admins, Playground Admins (for their assigned playground), and IT Admins.
- Suspending and restoring each run as a **tracked job**.
- While suspended, the user still sees the playground in their list, marked **Suspended**, read-only (including their own job history), with **all actions blocked**; **nothing happens to their underlying workspace, singleton resources, or app resources in GCP**.
- **No user or slice removal:** there is no removing a user or deleting a user's workspace slice from a playground.

---

## BU-06 Search for and act on behalf of a playground user
As a BU Admin, I want to search for a playground user and act on their behalf on their workspace and app containers, to accomplish supporting and troubleshooting users directly.

- **Allowed for:** BU Admins (in their folders), Playground Admins (in their assigned playground), and IT Admins.
- **Linked to the Student / User journeys:** searching for a user lets me inspect their workspace and app containers and execute the Student / User workspace and app-container journeys ([brs-student-cuj.md](brs-student-cuj.md)) on their behalf within the playground's allowances, recording the acting admin on every job.

---

## BU-07 View Playground Folder and playground jobs
As a BU Admin, I want to view Playground Folder jobs in my folders and all jobs at a playground level filtered by projects and users, to accomplish operational visibility and troubleshooting across my courses.

- **Allowed for:**
  - **BU Admins (and IT Admins):** view **Playground Folder-level jobs** for folders they manage, plus all **playground-level jobs** inside those folders filtered by **project (shard)** and by **user**.
  - **Playground Admins:** view all **playground-level jobs** for their assigned playground filtered by **project (shard)** and by **user** (no Playground Folder-level jobs).
- Covers every tracked job: creation, rename or budget update, configuration update, shard expansion, portal access suspension or restore, workspace initialization, app-container or resource action, decommission, and recommission — jobs are the only audit trail.
- Shows job status, progress, errors, timestamps, and who triggered each job; job history stays viewable while a playground is decommissioned.

---

## BU-08 Decommission a playground
As a BU Admin, I want to decommission a playground when the course ends or pauses, to accomplish stopping all billing across its projects immediately.

- **Allowed for:** **BU Admins and IT Admins only** (not Playground Admins).
- Decommissioning runs as a **tracked job** that **disables billing** across all of the playground's associated projects so cloud spend stops immediately, and marks **both the playground and its associated projects as decommissioned** in the platform.
- **Read-only while decommissioned:** the playground stays viewable (configuration and job history) by admins, and by its users marked **Decommissioned**, but every mutating action (BU-02 to BU-06 and all user journeys) is blocked until it is recommissioned (BU-09).
- **Never deleted from the platform or GCP:** neither platform records nor GCP folders, projects, budgets, workspaces, or inside-project resources are deleted; deletion is an external manual cleanup activity outside current scope.

---

## BU-09 Recommission a playground
As a BU Admin, I want to recommission a decommissioned playground, to accomplish resuming the course with every workspace exactly as it was left.

- **Allowed for:** **BU Admins and IT Admins only** (not Playground Admins).
- **Pre-condition:** the playground's Playground Folder is active (a decommissioned folder must be recommissioned by an IT Admin first, IT-10, which reactivates all its playgrounds).
- Recommissioning runs as a **tracked job** that re-enables billing (re-linking every project to the folder's billing account) across all of the playground's projects and marks **the playground and its projects as active** again.
- Because nothing was deleted, every workspace, singleton, and app resource is available again immediately; users see the playground as active.

---

## Not in the platform
- Creating Google groups or adding/removing group members (done in the Admin console).
- Changing, swapping, or upgrading a playground's template version, BU tags, optional Playground Admin group, or mapped user groups after creation.
- Removing a user from a playground or deleting their workspace slice / underlying resources.
- Choosing or manually switching which project shard new users land in.
- Deleting decommissioned GCP folders, projects, budgets, or resources (handled as external manual cleanup).
