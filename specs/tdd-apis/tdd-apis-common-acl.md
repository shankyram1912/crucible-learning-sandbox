# LSB Control Tower TDD: APIs, Common ACL

> Parent: [tdd-apis-master.md](tdd-apis-master.md)

One access control list decides who may call each operation. It is **configuration, not code**: the setting `LSB_ACL` maps **every operation explicitly to 1..N roles** ([tdd-apis-common-config.md](tdd-apis-common-config.md)). It is **common to every client**: the `lsb` CLI, direct REST calls, scripts, agent skills and the future UI all get the same answer, because access depends only on the caller's roles. Enforcement code: `src/api/lsb_api/acl.py` (`allow(operation)` dependency on each route); default map: `DEFAULT_ACL` in `src/api/lsb_api/settings.py`.

---

## 1. Roles

| Role | Who | Source |
|---|---|---|
| `USER` | Any authenticated user of the domain (verified ID token) | The token; no roster needed |
| `IT_ADMIN` | Members of `IT_ADMINS_GROUP` | In-memory admin roster ([tdd-apis-platform-users.md](tdd-apis-platform-users.md) section 1) |
| `BU_ADMIN` | Members of `BU_ADMINS_GROUP` (includes IT Admins through nesting) | Admin roster |
| `PLATFORM_ADMIN` | Members of `LSB_PLATFORM_ADMIN_GROUPS` | **Reserved for future use**; not in the ACL yet |

---

## 2. Rules

1. **Explicit:** every operation the API uses must have an entry with at least one role. The API **refuses to start** if a route's operation has no entry, if the ACL names an operation no route uses, or if an entry has an unknown role.
2. **One route, one operation:** each route maps to exactly one ACL operation, and role checks happen only on the route, never inside the handler. When different callers need different access (own data vs anyone's), use separate routes, with a `me` alias for the caller (for example `/v1/platform-users/me/roles` vs `/v1/platform-users/{email}/roles`).
3. **Default deny:** an operation not in the ACL cannot be called.
4. **Denied:** `403 PERMISSION_DENIED`, "This operation needs one of these roles: ...". If a role check needs the roster and it has not loaded yet: `500 INTERNAL`. `USER` operations work without the roster.
5. **Changing access is a configuration change:** override `LSB_ACL` (the whole map, as JSON) to change who may call what; the default lives in `DEFAULT_ACL` and changes with the code that adds operations.
6. **Every new operation adds its entry** to `DEFAULT_ACL` and to the table below in the same change.
7. **Scope checks stay in the operation:** the ACL decides *whether* a role may call an operation; the operation enforces *what* that caller may touch (for example only their own playground).

---

## 3. Default ACL

| Operation | Route | Roles |
|---|---|---|
| `health.api` | `GET /v1/health/api` | `IT_ADMIN`, `BU_ADMIN` |
| `health.db` | `GET /v1/health/db` | `IT_ADMIN` |
| `health.service` | `GET /v1/health/service` | `USER` |
| `platform_users.roles.self` | `GET /v1/platform-users/me/roles` | `USER` |
| `platform_users.roles` | `GET /v1/platform-users/{email}/roles` | `IT_ADMIN`, `BU_ADMIN` |
