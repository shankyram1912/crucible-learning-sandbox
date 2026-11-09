# Crucible (Learning Sandbox) Control Tower TDD: Tag and Label Binding Deep Dive

> Parent: [tdd-master.md](../tdd-master.md) (decisions in sections 1.7 Billing labels and 1.8 Playground tags)

How playground tags and project labels are bound: which permissions GCP checks, who can bind which key, how values are validated, why tags and labels never drift apart, and how GCP authorizes a binding. tdd-master 1.7 and 1.8 hold the decisions (key set, kinds, where bound, immutability); this spec explains the binding mechanics behind them.

---

## 1. Model in brief

| | Playground tags | Project labels |
|---|---|---|
| What | Resource Manager tags, five **dynamic** keys at org level | Key-value pairs on a project |
| Keys | `cost-center-bu`, `cost-center-code`, `cost-category`, `bu-tracking-code`, `bu-subcategory` | The same five names |
| Bound on | Playground Folders (the three IT keys) and playgrounds (`bu-tracking-code`, `bu-subcategory`) | Every project: Control Tower from `LABEL_*` configuration, playground projects copied from their effective tags |
| When | Once, by the job that creates the Playground Folder or the playground | Once, by the job that creates the project (playground creation or shard expansion) |
| Mutable | **No.** Tags are set at creation and never updated, like the parent folder, billing account and admin groups | Project owners can technically edit labels in the Console; the platform never rewrites them |
| Inherited | Yes, by every folder, project and resource below | No |
| Who can bind | Only holders of Tag User on the key (and on the resource) | Anyone who can edit the project, including project owners |
| Role | **Source of truth** | Copy, for label-based billing views |
| Control Tower | Not tagged | Labeled |

---

## 2. Tag binding principles

1. **Two permission checks per binding.** Binding a tag needs `resourcemanager.tagValueBindings.create` (role Tag User, `roles/resourcemanager.tagUser`) on **both** sides:
   - **Resource side:** the folder being tagged.
   - **Tag side:** the tag value. A dynamic value has no resource of its own, so GCP checks the **tag key** (section 5).
2. **Key grants decide who binds which keys.** Day-0 step 5 (`PlaygroundTagsCreate`) grants Tag User on the keys, and nothing else is needed at org level:

   | Key | Tag User held by | Effect |
   |---|---|---|
   | `cost-center-bu`, `cost-center-code`, `cost-category` | `grp-lsb-it-admins@` | Only IT Admins bind the IT-governed keys, in the platform or in the Console |
   | `bu-tracking-code`, `bu-subcategory` | `grp-lsb-bu-admins@` | BU Admins, and IT Admins through nesting |

3. **Resource grants decide where.** IT Admins get Tag User on the common ancestor of the folders where Playground Folders may be created (their standing grant, bound by Day-0 step 6 `ControlTowerIdentityCreate`; which ancestor is tdd-master open item 3.2.4), so they can tag any Playground Folder below it. The **one BU Admin group** of a Playground Folder gets Folder Admin and Tag User on that folder, bound by the folder-creation job (tdd-master 2.4; no Project Creator), so it can tag the playgrounds below it and nothing outside it.
4. **Bound with the caller's own token.** Playground Folder create and playground create (API operations 07 and 08, JobSync) bind the tags as the calling IT or BU Admin, so GCP applies principles 1 to 3 to that person. No platform service account needs tag rights for these operations.
5. **Two layers of value validation:**
   - **GCP checks the pattern** `^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$` on every binding, from any client. A value that doesn't match is rejected with `INVALID_ARGUMENT` (section 5).
   - **The API checks the catalog** for the three IT-governed keys: the value must be an active entry in the Firestore catalog (`cost-center-code` under the chosen `cost-center-bu`). Catalog entries are literal tag values (what you see is what you get) with an add-new or mark-disabled lifecycle: a disabled value can't be chosen for a new Playground Folder, while folders already carrying it keep it. GCP cannot check the catalog, so a Console binding is limited only by the pattern and by who holds Tag User on the key (IT Admins). The two BU keys are **un-cataloged**: BU Admins choose any value within the pattern.
6. **IAM protects where each key is bound.** The IT-governed keys are bound only on Playground Folders. BU Admins hold no Tag User on them, so GCP refuses a playground-level binding of those keys even in the Console (section 5).
7. **Bound once, never changed.** A folder carries one value per key (section 5), and the platform never deletes or replaces a binding: there is no re-tag operation, no job touches tags after creation, and decommission / recommission leave tags in place. Correcting a cost assignment means creating a new Playground Folder or playground.
8. **Location and project:** tag bindings on folders are global (no `--location`) and don't need a project. A client that sends a quota project the caller can't use fails before the tag check is reached.
9. **Not used in IAM conditions or org policies:** dynamic values can't be used there (tdd-master 1.8 rule 6).

---

## 3. Label binding principles

1. **Labels go on projects only** (tdd-master 1.7). Project labels attribute every cost in the project, including resources that can't be labeled.
2. **Copied once from the effective tags,** never hand-written: the job that creates a project (playground creation, or shard expansion) reads the effective tag values of the playground (its own two BU keys plus the three IT keys inherited from the Playground Folder) and writes them as the project's labels. Because tags are immutable, this copy never needs to be repeated and no later job rewrites labels.
3. **Hand-made projects are out of scope.** Projects created in the Console inside a playground are unsupported (tdd-master 2.1 rule 5): they inherit the tags, but the platform does not label them and there is no project hook or auto-labeler.
4. **Tags win on drift.** Project owners can edit labels; they can't change tags. Billing attribution by tag is therefore always correct even if someone edits a label; label-based views are a convenience copy.
5. **One value format** for tags and labels (the pattern above), so every tag value is a valid label value.
6. **Control Tower:** labels from `LABEL_*` in `initialize.env`, applied by the operation that creates the project; no tags.

---

## 4. Responsibilities

| Concern | Enforced by |
|---|---|
| Who may bind each key | GCP IAM: Tag User on the key (Day-0 step 5, `PlaygroundTagsCreate`) |
| Where they may bind | GCP IAM: Tag User on the folder or its ancestor (Day-0 step 6, `ControlTowerIdentityCreate`, for IT Admins; the Playground Folder grant for its BU Admin group) |
| Value format | GCP: the key's allowed-values pattern |
| Allowed values for IT-governed keys | API: Firestore catalog check (active entry) before binding |
| Tags never change after creation | API: no update or re-tag operation exists; folder and playground tags are immutable fields |
| Labels match tags | The project creation job (playground creation and shard expansion) copies the effective tags once |

---

## 5. How GCP checks a binding

GCP's documentation does not spell out how dynamic tag values are authorized; these are the facts the principles in section 2 rest on.

**The tag side is checked on the key.** A dynamic value has no resource of its own, so GCP checks Tag User on the tag key. A BU Admin holding Tag User only on the BU keys is denied on `cost-category` at the key itself, whatever resource they target.

**Each key follows its grant.** Tag User on the key, combined with Tag User on the folder, is all a binding needs:

| Key | IT Admin | BU Admin |
|---|---|---|
| `cost-center-bu` | Can bind | Cannot bind |
| `cost-center-code` | Can bind | Cannot bind |
| `cost-category` | Can bind | Cannot bind |
| `bu-tracking-code` | Can bind (through nesting) | Can bind |
| `bu-subcategory` | Can bind (through nesting) | Can bind |

**GCP enforces the pattern itself.** A value that doesn't match the key's allowed-values pattern (for example `Bad_Value`) is rejected with `INVALID_ARGUMENT`, so the API checks only the catalog, not the format.

**One value per key per folder.** A folder carries at most one binding per tag key; binding a second value for the same key on the same folder is rejected (principle 7 in section 2).
