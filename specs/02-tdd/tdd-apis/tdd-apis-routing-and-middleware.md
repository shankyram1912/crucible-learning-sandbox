# Router Tree, Auth, Cumulative Persona Resolver & Middleware (`tdd-apis-routing-and-middleware.md`)

> **Domain Master:** [tdd-apis-master.md](tdd-apis-master.md)  
> **Source Location:** `src/bff/core/auth.py` and `src/bff/main.py`

---

## 1. FastAPI Router Tree (`/api/v1`)

```text
app (FastAPI)
└── /api/v1
    ├── /session        -> routers/session.py     (tdd-apis-session.md)
    ├── /it-admin       -> routers/it_admin.py    (tdd-apis-it-admin.md)
    ├── /bu-admin       -> routers/bu_admin.py    (tdd-apis-bu-admin.md)
    └── /student        -> routers/student.py     (tdd-apis-student.md)
```

---

## 2. Authentication & Cumulative Persona Resolution (`AuthContext`)

Every request authenticates the caller via Google OIDC / IAP JWT (`email`) and resolves their **Google Group memberships** (via Cloud Identity Groups API or dev override header in local development) to construct `AuthContext`:

```python
class AuthContext(BaseModel):
    email: str                                  # e.g. "alice.tan@school.edu"
    user_slug: str                              # e.g. "alice-tan"
    sql_slug: str                               # e.g. "alice_tan"
    member_groups: set[str]                     # e.g. {"grp-cs101-lec1@school.edu"}
    is_it_admin: bool                           # True if in platform_control.it_admin_principals
    school_admin_scopes: set[str]               # school_slugs where caller is School Admin
    subfolder_cohort_admin_scopes: set[str]     # "school__subfolder" IDs where caller is Cohort Admin
    cohort_admin_scopes: set[str]               # cohort_slugs where caller is Cohort Admin
    student_cohort_scopes: set[str]             # cohort_slugs where caller matches student_group_emails[]
```

### Cumulative Authorization Rules:
1. **`require_it_admin(ctx)`:** Passes if `ctx.is_it_admin == True`.
2. **`require_school_admin(ctx, school_slug)`:** Passes if `ctx.is_it_admin` **or** `school_slug in ctx.school_admin_scopes`.
3. **`require_cohort_admin(ctx, cohort)`:** Passes if:
   * `ctx.is_it_admin`, **or**
   * `cohort.school_slug in ctx.school_admin_scopes` *(all School Admins are Cohort Admins across their School by default)*, **or**
   * `f"{cohort.school_slug}__{cohort.parent_subfolder_slug}" in ctx.subfolder_cohort_admin_scopes`, **or**
   * `cohort.cohort_slug in ctx.cohort_admin_scopes`.
4. **`require_student_or_admin(ctx, cohort_slug, target_student_slug)`:** Passes if `(cohort_slug in ctx.student_cohort_scopes and ctx.user_slug == target_student_slug)` **or** `require_cohort_admin(ctx, cohort)` passes (allowing Admins to inspect or act on behalf of a student).

---

## 3. In-Flight Mutation Guard & `simulate` Flag Injection

1. **In-Flight Mutation Guard (`409 Conflict`):**
   * Before starting a new mutation on a `School`, `DepartmentSubfolder`, or `Cohort`, the middleware checks `entity.status`. If `entity.status in {"PROVISIONING", "UPDATING", "TEARING_DOWN"}` (and Lazy Poll Reconciliation confirms `active_cloud_build_id` is still `QUEUED` or `WORKING`), the API returns `409 Conflict` (`MUTATION_ALREADY_IN_PROGRESS`).
2. **`simulate: bool` Parameter Extraction:**
   * Extracts `simulate: bool = Query(default=False)` on all mutating routes and passes it into `CloudBuildTerraformRunner.trigger(..., simulate=simulate)` or `AtomicRunner.execute(..., simulate=simulate)`.
