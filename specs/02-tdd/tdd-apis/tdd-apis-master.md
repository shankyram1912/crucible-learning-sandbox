# FastAPI BFF & Operational API Domains — Master (`tdd-apis-master.md`)

> **Parent TDD Master:** [../tdd-master.md](../tdd-master.md)  
> **Domain Sub-Specs:**
> * [tdd-apis-routing-and-middleware.md](tdd-apis-routing-and-middleware.md) — Central Router Tree, OIDC Auth, Cumulative Persona Resolver (`IT Admin ⊃ School Admin ⊃ Cohort Admin ⊃ Student`) & `simulate` Flag Middleware
> * [tdd-apis-session.md](tdd-apis-session.md) — `/api/v1/session/*` (Caller Identity, Cumulative Roles & Entitled Cohorts)
> * [tdd-apis-it-admin.md](tdd-apis-it-admin.md) — `/api/v1/it-admin/*` (`ServiceCatalog`, Version-Tracked `ITAdminGlobalConfig` `v1..vN`, School CRUD & Retry)
> * [tdd-apis-bu-admin.md](tdd-apis-bu-admin.md) — `/api/v1/bu-admin/*` (Department Sub-folders, Cohort & Version-Tracked `CohortConfig` `v1..vN`, Active Provisioning Shard Switch, Student Group Resync, Student Governance & Cohort Teardown)
> * [tdd-apis-student.md](tdd-apis-student.md) — `/api/v1/student/*` (Entitled Cohort List, JIT Workspace Entry Auto-Initialization, `AppContainer` & `AppServiceInstance` CRUD)

---

## 1. API Design Principles

1. **Domain-Aligned Route Prefixes (`/api/v1/{domain}`):**
   * Every route prefix maps 1-to-1 to an operational domain (`session`, `it-admin`, `bu-admin`, `student`).
2. **Cumulative Persona Authorization (`IT Admin ⊃ School Admin ⊃ Cohort Admin ⊃ Student`):**
   * Higher personas inherit all permissions of lower personas within their scope. Furthermore, **all BU Admins (`School Admin` and `Cohort Admin`) are Cohort Admins by default** within their assigned School/Sub-folder/Cohort subtree.
3. **Request-Level `simulate: bool` Parameter:**
   * Any mutating endpoint (`POST`, `PUT`, `PATCH`, `DELETE`) accepts `?simulate=true` (or `"simulate": true` in the request payload) and passes `simulate: bool` directly down to the Cloud Build Terraform Pipeline or Atomic Python Pipeline.
4. **Lazy Cloud Build Status Reconciliation on Read (`GET`):**
   * Whenever a `GET` request inspects a `School`, `DepartmentSubfolder`, or `Cohort` whose `status` is `PROVISIONING`, `UPDATING`, or `TEARING_DOWN` and `active_cloud_build_id != null`, the API handler lazily checks `cloudbuild.projects.builds.get(active_cloud_build_id)` and reconciles Firestore before returning the response.

---

## 2. Standard Response & Error Envelopes

### Synchronous / Reconciled Resource Response (`200 OK` / `201 Created`)
```json
{
  "ok": true,
  "simulate": false,
  "data": { ... }
}
```

### Asynchronous Cloud Build Pipeline Response (`202 Accepted`)
```json
{
  "ok": true,
  "simulate": false,
  "status": "PROVISIONING",
  "latest_config_version_id": "v3",
  "applied_config_version_id": "v2",
  "active_cloud_build_id": "cb-7721aa03",
  "data": { ... }
}
```

### Standard Error Response (`400`, `403`, `409`, `422`, `500`)
```json
{
  "ok": false,
  "error": {
    "code": "ALLOWANCE_EXCEEDED",
    "message": "Student alice-tan has already deployed 3/3 Cloud Run services in cohort cs101-fall.",
    "details": { "service_type": "CLOUD_RUN_SERVICE", "deployed": 3, "limit": 3 }
  }
}
```
