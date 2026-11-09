# Companion Agent Skills — Master (`tdd-skills-master.md`)

> **Parent TDD Master:** [../tdd-master.md](../tdd-master.md)  
> **Domain Sub-Specs:**
> * [tdd-skills-agy-portal-guide.md](tdd-skills-agy-portal-guide.md) — Packaged `SKILL.md` Companion User Guide for Students & Admins in Antigravity

---

## 1. Purpose & Boundary

The `src/agy-skill/` module packages a downloadable / installable **Antigravity Skill (`agy-portal-guide`)** that acts strictly as a **user guide and code-recipe companion** for the Learning Sandbox Self-Service Portal (`CUJ-ST-06`):

* **What it does:** Guides a student inside their AI coding assistant (Antigravity) on how to enter their Cohort workspace in the Portal, create App Containers (`app-<app_slug>`) and App-scoped services in the Portal UI, and connect their application code to their provisioned resources using `sa-<student_slug>` impersonation (`--impersonate-service-account`).
* **What it does NOT do:** It is **not** a provisioning CLI or BFF client — all resource creation and deletion happens in the Self-Service Portal UI.
