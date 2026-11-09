# LSB Control Tower TDD: Tag and Label Binding Deep Dive

> Parent: [tdd-master.md](../tdd-master.md) (decisions in sections 1.7 Billing labels and 1.8 Playground tags)

How playground tags and project labels are bound: which permissions GCP checks, who can bind which key, how values are validated, how tags and labels stay in step, and how GCP was observed to behave. tdd-master 1.7 and 1.8 hold the decisions (key set, kinds, where bound); this spec explains the binding mechanics behind them.

---

## 1. Model in brief

| | Playground tags | Project labels |
|---|---|---|
| What | Resource Manager tags, five **dynamic** keys at org level | Key-value pairs on a project |
| Keys | `cost-center-bu`, `cost-center-code`, `cost-category`, `bu-tracking-code`, `bu-subcategory` | The same five names |
| Bound on | Playground Folders (all five) and playgrounds (override `bu-tracking-code`, `bu-subcategory`) | Every project: Control Tower from `LABEL_*` configuration, playground projects copied from their effective tags |
| Inherited | Yes, by every folder, project and resource below | No |
| Who can change | Only holders of Tag User on the key (and on the resource) | Anyone who can edit the project, including project owners |
| Role | **Source of truth** | Copy, for label-based billing views |
| Control Tower | Not tagged | Labeled |

---

## 2. Tag binding principles

1. **Two permission checks per binding.** Binding a tag needs `resourcemanager.tagValueBindings.create` (role Tag User, `roles/resourcemanager.tagUser`) on **both** sides:
   - **Resource side:** the folder or project being tagged.
   - **Tag side:** the tag value. A dynamic value has no resource of its own, so GCP checks the **tag key** (section 5).
2. **Key grants decide who binds which keys.** Step 5 (`PlaygroundTagsCreate`) grants Tag User on the keys, and nothing else is needed at org level:

   | Key | Tag User held by | Effect |
   |---|---|---|
   | `cost-center-bu`, `cost-center-code`, `cost-category` | `grp-lsb-it-admins@` | Only IT Admins bind the IT-governed keys, in the platform or in the Console |
   | `bu-tracking-code`, `bu-subcategory` | `grp-lsb-bu-admins@` | BU Admins, and IT Admins through nesting |

3. **Resource grants decide where.** IT Admins get Tag User on the common ancestor of the school folders (step 6, `ControlTowerIdentityCreate`), so they can tag any Playground Folder below it. BU Admins named as controllers of a Playground Folder get Folder Admin, Tag User and Project Creator on it (tdd-master 2.4), so they can tag the playgrounds below it and nothing outside it.
4. **Bound with the caller's own token.** Playground Folder create and playground create (API operations 07 and 08, JobSync) bind the tags as the calling IT or BU Admin, so GCP applies principles 1 to 3 to that person. No platform service account needs tag rights for these operations.
5. **Two layers of value validation:**
   - **GCP checks the pattern** `^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$` on every binding, from any client. A value that doesn't match is rejected with `INVALID_ARGUMENT` (section 5).
   - **The API checks the catalog** for the three IT-governed keys: the value must be in the Firestore catalog list. GCP cannot check this, so a Console binding is limited only by the pattern and by who holds Tag User on the key (IT Admins).
6. **IAM protects the override rules.** A playground's direct binding overrides the inherited value for that key. The IT-governed keys are never overridden at playground level: BU Admins hold no Tag User on them, so GCP refuses the override even in the Console (section 5).
7. **One value per key per resource.** Changing a value is a re-tag: the job deletes the resource's binding for that key, then binds the new value, and updates the labels of the affected projects in the same job (section 3).
8. **Location and project:** tag bindings on folders are global (no `--location`) and don't need a project. A client that sends a quota project the caller can't use fails before the tag check is reached.
9. **Not used in IAM conditions or org policies:** dynamic values can't be used there (tdd-master 1.8 rule 5).

---

## 3. Label binding principles

1. **Labels go on projects only** (tdd-master 1.7). Project labels attribute every cost in the project, including resources that can't be labeled.
2. **Copied from the effective tags,** never hand-written:
   - **Platform-created projects:** labeled at creation by the job that creates them.
   - **Console-created projects:** the playground project hook (tdd-master 2.5, to-do 6a) copies the effective tags onto the new project.
   - **Re-tagging a playground:** the same job updates the folder's tag bindings and the labels on all its projects.
3. **Tags win on drift.** Project owners can edit labels; they can't change tags. Reconciliation re-applies labels from the effective tags.
4. **One value format** for tags and labels (the pattern above), so every tag value is a valid label value.
5. **Control Tower:** labels from `LABEL_*` in `initialize.env`, applied by the operation that creates the project; no tags.

---

## 4. Responsibilities

| Concern | Enforced by |
|---|---|
| Who may bind each key | GCP IAM: Tag User on the key (step 5) |
| Where they may bind | GCP IAM: Tag User on the folder or its ancestor (step 6; controllers for BU Admins) |
| Value format | GCP: the key's allowed-values pattern |
| Allowed values for IT-governed keys | API: Firestore catalog check before binding |
| Labels match tags | Platform jobs and the playground project hook |

---

## 5. How GCP behaves: the evidence

The principles in section 2 rest on how GCP checks a binding, which the documentation doesn't spell out for dynamic values. Observed live on 2026-11-09 with test users holding no org-level roles.

**The tag side is checked on the key.** With no value resource to check, GCP checks Tag User on the key: a BU Admin's attempt on `cost-category` was denied on the key itself.

**Each key follows its grant.** Every key behaved exactly as step 5 grants it:

| Key | IT Admin | BU Admin |
|---|---|---|
| `cost-center-bu` | Can bind | Cannot bind |
| `cost-center-code` | Can bind | Cannot bind |
| `cost-category` | Can bind | Cannot bind |
| `bu-tracking-code` | Can bind (through nesting) | Can bind |
| `bu-subcategory` | Can bind (through nesting) | Can bind |

**GCP enforces the pattern itself.** A value that doesn't match the key's pattern (for example `Bad_Value`) is rejected with `INVALID_ARGUMENT`, so the API checks only the catalog, not the format.

**One value per key per folder.** Each user needed their own folder to bind the same BU keys, because a folder carries one value per key (principle 7 in section 2).
