# Session & Persona Discovery API (`tdd-apis-session.md`)

> **Domain Master:** [tdd-apis-master.md](tdd-apis-master.md)  
> **Route Prefix:** `/api/v1/session`

---

## 1. Endpoints

### `GET /api/v1/session/me`
Resolves the logged-in user's identity, normalized student slugs (`student_slug`, `student_sql_slug`), cumulative persona roles, delegated admin scopes, and entitled Student Cohorts (by matching the caller's Google Groups against `Cohort.current_config.student_group_emails[]`).

#### Response `200 OK`
```json
{
  "ok": true,
  "data": {
    "email": "alice.tan@school.edu",
    "student_slug": "alice-tan",
    "student_sql_slug": "alice_tan",
    "personas": {
      "is_it_admin": false,
      "is_school_admin": false,
      "is_cohort_admin": false,
      "is_student": true
    },
    "admin_scopes": {
      "schools": [],
      "subfolders": [],
      "cohorts": []
    },
    "entitled_student_cohorts": [
      {
        "cohort_slug": "cs101-fall",
        "display_name": "CS101 Fall 2026",
        "school_slug": "eng",
        "cohort_status": "READY",
        "matched_group": "grp-cs101-lec1@school.edu",
        "workspace_init_status": "INITIALIZED",
        "assigned_project_id": "cs101-fall-p01"
      }
    ]
  }
}
```
*(If `entitled_student_cohorts` is `[]` and the caller has no admin scopes, the UI renders the **"No Sandbox Assigned"** screen displaying `email`).*
