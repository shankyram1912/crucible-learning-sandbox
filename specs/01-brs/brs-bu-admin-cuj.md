# Learning Sandbox: BU Admin Journeys

> Master: [brs-master.md](brs-master.md) · Technical design: [tdd-master.md](../02-tdd/tdd-master.md)
> Persona: BU Admin (members of `grp-lsb-bu-admins@`, managing the Playground Folders whose BU Admin group they're in)

Each journey is one sentence, followed by the design decisions behind it. Questions still to settle are marked **Open**.

---

## BU-01 Create a playground
As a BU Admin, I want to create a playground from a template in a Playground Folder I manage, to accomplish a ready environment for a course.

- I only see the Playground Folders whose BU Admin group I'm in. The platform checks this live on each request.
- The playground keeps the template version it was created with.
- I set the BU tracking code and subcategory here; they're never set on the folder.
- Projects are created only by the pipeline and linked to the folder's billing account.
- I can name an optional Playground Admin group (at most one existing group, for example the course's TAs). Its members get the same rights as BU Admins, for this playground only: owners of its projects, able to manage them in the Cloud console and to configure the playground through the platform.
- On every project, my BU Admin group, the IT Admins group and the Playground Admin group each get full owner access.
- I enter the expected number of students. The platform creates expected students ÷ the template's students per project projects, rounded up.
- **Open:** does a playground get its own budget (none, optional or required)?

---

## BU-02 Map groups to the playground
As a BU Admin, I want to map existing groups of the playground's users (students or other designated users) to the groups the template expects, to accomplish the right people getting access.

- Groups already exist; the platform never creates groups or changes their members.
- Roles come from each service's Terraform module.

---

## BU-03 Configure playground services
As a BU Admin, I want to turn the template's optional services on or off, to accomplish a playground that matches the course.

- Required services are added automatically.
- Each change is saved as a new version of the playground's configuration.
- I set each service's per-student allowance for my playground, within the limits the template and service allow.
- **Open:** turning a service off stops new provisioning but never deletes existing resources?
- **Open:** who can upgrade a playground to a newer template version: BU Admins, IT Admins, or both?

---

## BU-04 Add projects to a playground
As a BU Admin, I want to add projects when enrollment grows, to accomplish more capacity without disturbing existing students.

- **Open:** design not started.

---

## BU-05 Decommission a playground
As a BU Admin, I want to tear down a playground when the course ends, to accomplish stopping all its costs.

- **Open:** design not started.

---

## Moved to the student CUJs
Choosing which project new students land in, suspending or removing a student, and searching for or acting on behalf of a student.
