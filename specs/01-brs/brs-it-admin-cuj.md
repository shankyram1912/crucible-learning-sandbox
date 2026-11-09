# Crucible (Learning Sandbox): IT Admin Journeys

> Master: [brs-master.md](brs-master.md) · Technical design: [tdd-master.md](../02-tdd/tdd-master.md)
> Persona: IT Admin (members of `grp-lsb-it-admins@`)

Each journey is framed as *"As an IT Admin, I want to ..., to accomplish ..."*, followed by the design decisions behind it. Every change runs as a **tracked job** — jobs are the platform's audit trail.

---

## IT-01 Manage the service catalog
As an IT Admin, I want to configure and version single-service templates in the service catalog, to accomplish one governed, flexible set of GCP building blocks that playground templates are composed from.

- Every **service template** in the catalog maps to a **single GCP service** and is **versioned**, with one version marked `current`.
- Each service version sets its **playground availability mode**, giving flexibility when rolling out services into playground templates:
  1. **Mandatory:** always enabled in every playground that uses it; cannot be unchecked (for example Service Account).
  2. **Enabled by default and optional:** starts enabled on new playgrounds, and can be unchecked before creation.
  3. **Disabled by default and optional:** starts disabled on new playgrounds, ready to be enabled at creation or added later.
- **Only mandatory services may define a user singleton resource.** Optional services (enabled or disabled by default) provide **app resources only**, so enabling an optional service on a playground later never requires re-initializing anyone's workspace.
- Each service version also sets:
  - Name, description, the **Terraform module** and its pinned ref, the GCP APIs it enables, the prerequisite services it requires, the user group slots it expects, and the **user singleton resources** (mandatory services only) and **app resources** it provides to playground users (students or other designated users).
  - **Service configuration defaults** (sizes and underlying settings passed to Terraform, such as shared Cloud SQL tier or Cloud Run CPU/memory).
  - **Quota per project** (maximum capacity per project shard) and **per-user bounds** (`min` is the minimum and default starting allowance per user, up to a **finite `max`** ceiling — there is no unlimited allowance).
- Which GCP IAM roles each group gets is defined in the Terraform module, not in the catalog.
- Elevated privileges are modeled as a separate service definition, not a flag on an existing one.
- New playground template versions default to each service's `current` version; older non-retired service versions stay selectable when composing a template until retired.
- **Never deleted:** service templates and service versions are never edited in place and **never hard-deleted** from the platform; obsolete or superseded ones can only be **retired** (blocking new selection while keeping existing uses intact).

---

## IT-02 Manage playground templates
As an IT Admin, I want to compose versioned playground templates from catalog service versions and set the per-project student ceiling, to accomplish ready-made playground shapes that BU Admins choose from.

- Each playground template has immutable **versions**, with one version marked `current`; every edit creates a new version.
- A template version composes **pinned service versions** from the service catalog (inheriting each service's mandatory, enabled-by-default-and-optional, or disabled-by-default-and-optional mode, prerequisites, user group slots, and service defaults, with optional template-level tuning within each service's bounds).
- A template version sets the **maximum number of students per project** (shard capacity ceiling, for example `100` students per project), which together with a playground's expected student count determines how many project shards are created.
- **Only the `current` version is used for new playgrounds, and never upgraded:** creating a new playground from a template always uses that template's `current` version, and **existing playgrounds stay permanently pinned to the template version they were created with for their entire life** (a playground's template version can never be upgraded).
- Every active (non-retired) template is available across every Playground Folder.
- **Never deleted:** playground templates and template versions are never edited in place and **never hard-deleted** from the platform; obsolete or superseded ones can only be **retired** (blocking new selection while keeping existing playgrounds intact).

---

## IT-03 Manage cost centers and their codes
As an IT Admin, I want to add new cost centers (one per school) and their cost center codes and mark obsolete ones disabled, to accomplish governed billing tags that only IT can assign.

- Each cost center code (`cost-center-code`) belongs to one cost center (`cost-center-bu`).
- **What you see is what you get:** each entry is the literal tag value itself, with no separate human-readable display label or description.
- Lifecycle is strictly **add new or mark disabled**: existing values are never edited in place or deleted from the platform. Disabled values cannot be chosen for new Playground Folders, while existing folders keep them.

---

## IT-04 Manage cost categories
As an IT Admin, I want to add new cost categories to one shared list and mark obsolete ones disabled, to accomplish consistent category tagging across all schools.

- One shared list of cost categories (`cost-category`) across all schools.
- **What you see is what you get:** each entry is the literal tag value itself, with no separate human-readable display label or description.
- Lifecycle is strictly **add new or mark disabled**: existing values are never edited in place or deleted from the platform. Disabled values cannot be chosen for new Playground Folders, while existing folders keep them.

---

## IT-05 Create a Playground Folder
As an IT Admin, I want to create a Playground Folder with a billing account, budget, IT cost tags and a BU Admin group, to accomplish a governed, budgeted space where a BU builds its playgrounds.

- Creating a Playground Folder runs as a **tracked job** that sets up the GCP folder, guardrails, tag bindings, folder budget, and IAM bindings.
- **Where:** I browse from the top of the organization and pick any existing folder I can see. GCP checks that I have the rights to create there. The folder cannot be moved later.
- **Inherited access:** anyone with access on the parent folder also has it inside. Picking the parent is my responsibility.
- **Guardrails:** applied on the Playground Folder, adding to whatever the organization and parent folders already enforce.
- **Billing account:** I pick from the billing accounts I can see. It cannot be changed later, and every project created under the folder is linked to it by the pipeline.
- **Budget:** required, in the billing account's currency, with platform-wide alert levels at 50, 75, 90 and 100% (email notifications are out of scope for now). Created by the platform.
- **IT Admin cost tags (set at Playground Folder level):** `cost-center-bu`, `cost-center-code`, and `cost-category`, chosen from the active values in IT-03 and IT-04. Only these three IT tags are set on the Playground Folder (BU tags are set on playgrounds), and **neither Playground Folder tags nor playground tags can be updated once created**. Folder tags are **inherited** by every playground, project, and resource below and are **copied onto every project below as billing labels**.
- **BU Admin group:** exactly one existing group, which must already be inside `grp-lsb-bu-admins@` and **cannot be changed or swapped once created** (who manages the folder changes by updating membership of that group in the Admin console). The group manages playgrounds inside the folder.
- **Project owners:** on every playground project, the folder's BU Admin group, the IT Admins group, and — if configured at playground creation — its **optional Playground Admin group** (at most one per playground, also immutable once created) each get full owner access.
- **Projects are created only by the pipeline,** which gets project-creation rights on the Playground Folder and links each project to its billing account.
- **Prerequisite:** the platform setup grants the required billing rights on every billing account used for playgrounds.

---

## IT-06 Update a Playground Folder
As an IT Admin, I want to rename a Playground Folder or update its budget, to accomplish keeping its name and spend alerts aligned with the school.

- Renaming and updating the budget each run as a **tracked job**; the budget update adjusts the Playground Folder's budget amount in the billing account's currency.
- **Only on an active folder:** a decommissioned Playground Folder is read-only until recommissioned (IT-10).
- **Immutable once created:** the **parent folder, billing account, IT cost tags, and BU Admin group cannot be changed or swapped** after the Playground Folder is created (likewise, on a playground, its **template version, BU tags, optional Playground Admin group, and mapped user groups** cannot be changed, swapped, or upgraded once created).

---

## IT-07 Decommission a Playground Folder
As an IT Admin, I want to decommission a Playground Folder, to accomplish stopping all billing across its playgrounds and projects when the container is paused or retired.

- Decommissioning a Playground Folder runs as a **tracked job** that disables billing across all underlying playgrounds' associated projects so cloud spend stops immediately, and marks the Playground Folder along with **all underlying playgrounds and projects as decommissioned** in the platform.
- **Read-only while decommissioned:** the folder and everything inside it stay viewable (configuration and job history) by every persona, but every mutating action on the folder, its playgrounds, and its users' workspaces is blocked until the folder is recommissioned (IT-10).
- **Never deleted from the platform or GCP:** neither the platform records nor the GCP folders, projects, budgets, workspaces, or inside-project resources are deleted; deletion is an external manual cleanup activity outside current scope.

---

## IT-08 Act on any Playground Folder, playground, or user workspace
As an IT Admin, I want to perform any BU Admin action on any Playground Folder or playground and act on behalf of playground users, to accomplish helping schools, courses, and users directly without switching accounts.

- IT Admins are owners of every playground project and reach every Playground Folder and playground through their standing access and platform role.
- IT Admins can act on behalf of playground users (students or other designated users) on their workspaces and app containers.
- Every change records the acting IT Admin who requested it.

---

## IT-09 View jobs across Playground Folders, playgrounds, projects, and users
As an IT Admin, I want to view Playground Folder jobs and all jobs at a playground level filtered by projects and users, to accomplish operational visibility and troubleshooting across every folder and playground.

- Every folder setup, provisioning, rename or budget update, configuration update, shard expansion, portal access suspension or restore, workspace initialization, app-container or resource action, decommission, and recommission runs as a **tracked job** recorded in the platform — jobs are the only audit trail.
- I can view **Playground Folder-level jobs** across all Playground Folders, and for any playground I can view all **playground-level jobs** filtered by **project (shard)** and by **user** (the requester or target workspace user), seeing job status, progress, errors, timestamps, and who triggered the job.

---

## IT-10 Recommission a Playground Folder
As an IT Admin, I want to recommission a decommissioned Playground Folder, to accomplish restoring billing and activity across its playgrounds and projects when the school needs them again.

- **Allowed for:** IT Admins only (the mirror of IT-07).
- Recommissioning runs as a **tracked job** that re-enables billing (re-linking every project to the folder's billing account) across all underlying playgrounds' associated projects, and marks the Playground Folder along with **all underlying playgrounds and projects as active** again.
- Because nothing was deleted, every playground configuration, workspace, singleton, and app resource is available again immediately; users see the playgrounds as active.
- A playground inside a decommissioned Playground Folder cannot be recommissioned on its own (BU-09); the folder must be recommissioned first.

---

## Not in the platform
- Adding or removing members of Google groups (done in the Admin console).
- Creating ordinary organizational folders, such as school folders (done in the Cloud console).
- Hard-deleting service templates, playground templates, catalog versions, or cost tag values from the platform (catalog items are retired or marked disabled, never deleted).
- Deleting decommissioned GCP projects, folders, budgets, or resources (handled as external manual cleanup).
- Upgrading an existing playground to a newer template version (playgrounds stay permanently pinned to their creation template version), or a simulate / dry-run execution mode.
