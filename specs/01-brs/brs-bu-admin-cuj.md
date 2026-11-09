# Learning Sandbox: BU Admin Journeys

> Master: [brs-master.md](brs-master.md) · Technical design: [tdd-master.md](../02-tdd/tdd-master.md)
> Persona: BU Admin (members of `grp-lsb-bu-admins@`, managing the Playground Folders whose BU Admin group they're in)

Each journey is one sentence, followed by the design decisions behind it.

---

## BU-01 Create a playground
As a BU Admin, I want to create a playground from a template in a Playground Folder I manage, to accomplish a ready environment for a course.

- I only see the Playground Folders whose BU Admin group I'm in. The platform checks this live on each request.
- The playground keeps the template version it was created with, until explicitly upgraded.
- I set the BU tracking code and subcategory here; they're never set on the folder.
- Projects are created only by the pipeline and linked to the folder's billing account.
- I can name an optional Playground Admin group (at most one existing group, for example the course's TAs). Its members get the same rights as BU Admins, for this playground only: owners of its projects, able to manage them in the Cloud console and to configure the playground through the platform (except decommissioning).
- On every project, my BU Admin group, the IT Admins group and the Playground Admin group each get full owner access.
- I enter the expected number of students. The platform creates expected students ÷ the template's students per project projects, rounded up.
- I must set a **required budget** on the playground (in the Playground Folder's billing account currency, with the same 50, 75, 90 and 100% alert levels, created by the platform).
- I can also set an **optional per-project shard budget**, less than or equal to the playground budget, as a default across shards or overridden on individual shards.

---

## BU-02 Map groups to the playground
As a BU Admin, I want to map existing groups of the playground's users (students or other designated users) to the groups the template expects, to accomplish the right people getting access.

- Groups already exist; the platform never creates groups or changes their members.
- Roles come from each service's Terraform module.

---

## BU-03 Configure playground services and template version
As a BU Admin, I want to enable additional optional services, adjust per-student allowances, or upgrade a playground to a newer template version, to accomplish a playground that evolves safely with the course.

- Mandatory services are always enabled and cannot be unchecked.
- Services are **add-only**: once enabled on a playground, a service stays enabled for the life of the playground. Required prerequisite services are added automatically.
- Each change is saved as a new version of the playground's configuration and applied across every project in the playground.
- I set each service's per-student allowance for my playground, within the limits the template and service allow. Lowering an allowance is non-destructive: it only gates new creations and leaves existing student resources untouched.
- **Template upgrades** are explicit and additive/non-destructive: BU Admins, Playground Admins (for their playground), and IT Admins can upgrade a playground to a newer template version (per playground; no bulk upgrade). New mandatory or default services are added, already-enabled services stay enabled even if removed from the template, and updated service module versions are applied.

---

## BU-04 Expand playground student capacity
As a BU Admin, I want to increase a playground's expected student count when enrollment grows, to accomplish more project shard capacity without disturbing existing students.

- Expected student count is **grow-only** (never shrunk).
- When `ceil(new_expected_students / students_per_project)` exceeds the current project count, the pipeline adds new project shards (`p(K+1)..pM`) initialized with all currently enabled playground services, leaving existing shards (`p01..pK`) untouched.
- Allowed for BU Admins, Playground Admins (for their playground), and IT Admins.

---

## BU-05 Decommission a playground
As a BU Admin, I want to decommission a playground when the course ends, to accomplish stopping all its billing costs.

- Allowed for **BU Admins and IT Admins only** (not Playground Admins).
- Decommissioning **disables billing** on the playground's projects to stop spend immediately and marks the playground decommissioned in configuration (exact billing-disable mechanics finalized in TDD).
- **No resource or project deletion:** deleting projects, folders, or inside-project resources is an external cleanup activity outside current scope (potential future journey).

---

## Moved to the student CUJs
Choosing which project new students land in, suspending or removing a student, and searching for or acting on behalf of a student.
