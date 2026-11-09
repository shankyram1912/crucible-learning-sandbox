# Learning Sandbox: Business Requirements (Master)

What the platform is for, who uses it, how playgrounds are organized and configured, and the journeys of each persona. Technical design: [tdd-master.md](../02-tdd/tdd-master.md).

**Persona documents (journeys and the design decisions behind them):**
- **IT Admin:** [brs-it-admin-cuj.md](brs-it-admin-cuj.md)
- **BU Admin:** [brs-bu-admin-cuj.md](brs-bu-admin-cuj.md)
- **Student:** to be written (reference: [brs-student-cuj.md](../../specs-reference/01-brs/brs-student-cuj.md))

---

## 1. The business problem

Universities and enterprises run courses, labs and hackathons for hundreds or thousands of students on Google Cloud. Doing this in shared projects under pooled budgets runs into three problems:

1. **Isolation in shared projects:** broad roles let students see, change or delete each other's resources and exhaust shared budgets.
2. **The central IT bottleneck:** central IT owns billing, cost codes and guardrails, while schools and faculty own the courses. If every course needs an IT ticket, setup takes days instead of minutes.
3. **Governed cost tracking:** spend has to be attributed to the right school, cost code and category, without relying on people tagging resources correctly.

The Learning Sandbox is a self-service platform, run from a central **Control Tower**, that separates:
- **Governance (IT Admin):** service catalog, templates, cost tags, billing accounts, budgets, and where playgrounds may live.
- **Course setup (BU Admin):** playgrounds created from templates, inside the space IT gave them.
- **Learning (Student):** just-in-time workspaces inside a playground (to be specified).

---

## 2. Personas

```text
IT Admin    members of grp-lsb-it-admins@
  │  Governs the catalog, templates, cost tags and Playground Folders.
  │  Has equal access to every Playground Folder and playground.
  ▼
BU Admin    members of grp-lsb-bu-admins@ (IT Admins are nested inside)
  │  Builds and runs playgrounds in the Playground Folders whose BU Admin group they're in.
  ▼
Student     members of the groups mapped to a playground (to be specified)
```

1. **IT Admins can do everything a BU Admin can,** everywhere.
2. **Group membership is managed outside the platform,** in the Admin console. The platform only reads it.
3. **Plain users** (no admin role, not in a playground) see nothing yet.

---

## 3. Configuration model

Configuration flows from IT-governed catalogs to the playgrounds BU Admins create.

```text
Service catalog (IT)        GCP services, versioned; one version marked current
        │
        ▼
Playground templates (IT)   sets of service versions + project layout, versioned
        │
        ▼
Playground (BU)             created from one template version, kept until explicitly upgraded

Tag catalog (IT)            cost centers (with their codes) and categories
        │
        ▼
Playground Folder (IT)      cost tags, billing account, budget, one BU Admin group
        │
        ▼
Playground (BU)             BU tracking code and subcategory
```

1. **Versioned, never edited in place:** services and templates get a new version for every change. Existing playgrounds are unaffected until upgraded.
2. **Retire, don't delete:** anything already in use (a service, a template, a tag value) can only be retired; deleting is allowed only if it was never used.
3. **Roles live in Terraform:** which roles each group gets is defined in each service's Terraform module. Elevated privileges are a separate service.

---

## 4. How playgrounds are organized

```text
Organization
└── any folder                 ordinary GCP folder (not managed by the platform)
    └── Playground Folder      created by an IT Admin
        │                      cost tags, billing account, budget, one BU Admin group
        └── Playground         created by a BU Admin from a template
            │                  BU tracking code, subcategory, owners, mapped groups
            └── projects       created only by the platform, linked to the folder's billing account
```

1. **Two levels only:** Playground Folder, then playground. No nesting of either.
2. **A Playground Folder can sit under any folder** the IT Admin can see. Access granted on the parent flows into it.
3. **Projects are created only by the platform.** Projects created by hand in a playground aren't supported.
4. **The Control Tower** is a separate project; it isn't a playground.

---

## 5. Core business rules

1. **Cost attribution:** every Playground Folder carries a cost center, cost center code and category from the IT catalog; every playground adds its own BU tracking code and subcategory. Projects inherit them as tags and carry them as labels.
2. **One billing account per Playground Folder,** chosen at creation and never changed. The platform links every project to it.
3. **One budget per Playground Folder,** required, in the billing account's currency, with alert levels at 50, 75, 90 and 100%. Notifications are out of scope for now.
4. **One BU Admin group per Playground Folder.** Everyone who manages its playgrounds is added to that group in the Admin console.
5. **Guardrails per Playground Folder,** on top of whatever the organization and parent folders already apply.
6. **No simulate or dry-run mode:** every action acts on real Google Cloud.
7. **Every change records who asked for it.**

---

## 6. Responsibilities by level

| Level | IT Admin | BU Admin | Student |
|---|---|---|---|
| Service catalog, templates, tag catalog | Manage | Read | none |
| Playground Folder | Create, update, decommission | Read the folders whose group they're in | none |
| Playground | Same as BU Admin | Create, configure, decommission | To be specified |
| Projects in a playground | Same as BU Admin | Through the platform only | To be specified |

---

## 7. Journeys per persona

- **IT Admin:** manages the service catalog, playground templates, cost centers and categories, and Playground Folders. [brs-it-admin-cuj.md](brs-it-admin-cuj.md)
- **BU Admin:** creates playgrounds from templates, maps groups, configures services and decommissions playgrounds. [brs-bu-admin-cuj.md](brs-bu-admin-cuj.md)
- **Student:** to be written.
