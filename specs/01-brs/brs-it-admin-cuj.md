# Learning Sandbox: IT Admin Journeys

> Master: [brs-master.md](brs-master.md) · Technical design: [tdd-master.md](../02-tdd/tdd-master.md)
> Persona: IT Admin (members of `grp-lsb-it-admins@`)

Each journey is one sentence, followed by the design decisions behind it. Questions still to settle are marked **Open**.

---

## IT-01 Manage the service catalog
As an IT Admin, I want to add, version, update and retire GCP service definitions, to accomplish one controlled list of services that templates are built from.

- Each service has versions, and one version is marked current.
- A version holds: name and description, the Terraform module and its pinned ref, the APIs it enables, the services it requires, whether it's on by default or optional, max per project, min per student, sizes and settings, and the groups it expects (for example students).
- Which roles each group gets is defined in the Terraform module, not in the catalog.
- Elevated privileges are a separate service, not an option on an existing one.
- New templates default to the current version; older versions stay selectable until retired.
- A service or version that's in use can only be retired, never deleted. Deleting is allowed only if it was never used.
- **Open:** should a service also be markable as **mandatory** (always on, can't be turned off), like Service Account?

---

## IT-02 Manage playground templates
As an IT Admin, I want to build playground templates from service versions, to accomplish ready-made playground shapes that BU Admins choose from.

- Each template has versions, and one version is marked current. Every edit creates a new version.
- A version holds: name and description, the service versions it includes (each on by default or optional), students per project (which, with the playground's expected students, decides how many projects a playground gets), the groups it expects, and quota and size settings within each service's limits.
- A playground keeps the template version it was created with, until it's explicitly upgraded.
- Every template is available in every Playground Folder.
- Retire, don't delete, once in use.

---

## IT-03 Manage cost centers and their codes
As an IT Admin, I want to keep the list of cost centers (one per school) and each one's codes, to accomplish billing tags that only IT can assign.

- Each code belongs to one cost center.
- Values can't be changed. A different value is a new entry, and the old one is retired.
- Retire, don't delete, once in use.

---

## IT-04 Manage cost categories
As an IT Admin, I want to keep one shared list of cost categories, to accomplish the same categories across all schools.

- One list for all schools.
- Values can't be changed; retire, don't delete, once in use.

---

## IT-05 Create a Playground Folder
As an IT Admin, I want to create a Playground Folder with a billing account, budget, cost tags and a BU Admin group, to accomplish a governed, budgeted space where a BU builds its playgrounds.

- **Where:** I browse from the top of the organization and pick any folder I can see. GCP checks that I have the rights to create there. The folder can't be moved later.
- **Inherited access:** anyone with access on the parent folder also has it inside. Picking the parent is my responsibility.
- **Guardrails:** applied on the Playground Folder. They add to whatever the org and parent folders already apply.
- **Billing account:** I pick from the accounts I can see. It can't be changed later. Every project under the folder is linked to it by the platform.
- **Budget:** required, in the billing account's currency. Alert levels 50, 75, 90 and 100% are platform-wide. No email notifications for now. The platform creates the budget.
- **Cost tags:** cost center, cost center code and category, chosen from the lists in IT-03 and IT-04. Nothing else is tagged on the folder.
- **BU Admin group:** exactly one group, which must already be inside the BU Admins group. People are added to it in the Admin console. It manages the playgrounds and their tags in the folder.
- **Project owners:** on every playground project, the BU Admin group, the IT Admins group and the playground's Playground Admin group each get full owner access.
- **Projects are created only by the pipeline,** which gets project-creation rights on the Playground Folder and links each project to its billing account.
- **Prerequisite:** the platform has billing rights on every billing account used for playgrounds, granted by the platform setup.

---

## IT-06 Update a Playground Folder
As an IT Admin, I want to rename a Playground Folder, change its cost tags, budget or BU Admin group, to accomplish keeping it in line with the school.

- Changing cost tags also updates the labels on every project in the folder.
- Swapping the BU Admin group moves the access from the old group to the new one.
- The billing account and the parent folder can't be changed.

---

## IT-07 Decommission a Playground Folder
As an IT Admin, I want to decommission an empty Playground Folder, to accomplish removing containers that are no longer used.

- Only when it has no active playgrounds.
- The budget and access are removed and the folder is deleted (GCP keeps it recoverable for 30 days).
- The platform keeps the record, marked decommissioned.

---

## IT-08 Act on any Playground Folder or playground
As an IT Admin, I want to do anything a BU Admin can do, anywhere, to accomplish helping BUs without switching accounts.

- IT Admins are owners of every playground project, and reach every Playground Folder through their standing access.
- Every change records who asked for it.

---

## Not in the platform
- Adding or removing people in groups (done in the Admin console).
- Creating ordinary folders, such as school folders (done in the Console).
- A simulate or dry-run mode.
