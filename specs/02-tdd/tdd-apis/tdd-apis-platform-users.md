# LSB Control Tower TDD: APIs, Platform Users Domain

> Parent: [tdd-apis-master.md](tdd-apis-master.md)

Platform users are the people with a **platform role**: IT Admins and BU Admins. Their group membership is managed outside the platform by people with directory rights (Admin console); **the platform only reads it** ([tdd-master.md](../tdd-master.md) section 2.2). This domain answers who has which platform role. Listing platform users (with filters such as IT Admins, BU Admins, mapped Playground Folders, playground users and projects) comes later, once Playground Folders and playgrounds exist.

| # (build order) | Operation | REST | CLI | Status |
|---|---|---|---|---|
| 04 | Platform roles | `GET /v1/platform-users/me/roles`, `GET /v1/platform-users/{email}/roles` | `lsb platform-users roles [EMAIL]` | Done |

Replaces the `group members` rows (10 to 12) of [apis-v0-interface.md](../../../specs-reference/apis-v0-interface.md) A.2 and B for the service groups; the platform no longer changes membership.

---

## 1. Common rules

1. **Admin roster in memory:** platform roles and personas come from an in-memory roster of the **transitive user members of the admin groups in settings** (`IT_ADMINS_GROUP`, `BU_ADMINS_GROUP`, and any group in `LSB_PLATFORM_ADMIN_GROUPS`), so a role check never calls the directory on the request path (`src/api/lsb_api/admin_roster.py`).
   - **Loaded at startup if possible** as the final step before the API serves requests. A failure is logged and the API starts anyway: one Cloud Identity `searchTransitiveMemberships` call (paged) per admin group, following nested groups (`DirectoryReader.group_members`).
   - **Refreshed in the background** every `LSB_ADMIN_ROSTER_REFRESH_SECONDS` (default 300). A refresh replaces the roster only if every group was read; on failure the previous roster stays and the next cycle retries.
   - **Never loaded** (directory unreadable since startup): role and persona checks answer `500 INTERNAL` until a refresh succeeds.
   - **Staleness:** a membership change in the Admin console applies within one refresh period, unless live role checks are on (rule 6).
2. **Only admins are cached.** Students and other users are never loaded; anyone not in the roster holds only `USER`, and the roles answer lists **only admin groups** (a student in `grp-ba101-students@` shows no groups). **Open, revisit with the playground operations (to-do list item 08):** reading and showing non-admin groups (for example a live `/{email}/groups` and `/me/groups` operation), and student and playground role checks.
3. **Identity:** the roster is read as the API's own identity (ADC locally, `sa-lsb-api` deployed), which needs read access to group memberships. No directory write rights anywhere.
4. **Synchronous, read-only;** not a job.
5. **One implementation:** `roles_of()` in `src/api/lsb_api/context.py` is the only code that turns roster groups into roles. The ACL check and the platform roles API both use it, so they always agree. The caller's roles are computed once per request and cached on the request context.
6. **Live role checks (optional):** with `LSB_ROLE_CHECK_USE_CACHE=false`, the **ACL role check** skips the roster and reads the caller's groups from the directory (one `searchTransitiveGroups` call, `DirectoryReader.user_groups`). It keeps only the admin groups from settings and writes the result back into the roster for that user, so the check also refreshes the cache. Everything else keeps using the roster, including the platform roles API (which reuses the live result for the caller in the same request). It works even if the roster never loaded. A failed directory read answers `500 INTERNAL` with the error in the API log; there is no fallback to the cache. Cost: one directory call per request to an admin route. `USER` operations never check roles, so they never call the directory.

---

## 2. Operation 04: platform roles

**Purpose:** every platform role a user holds, in the same vocabulary as the ACL ([tdd-apis-common-acl.md](tdd-apis-common-acl.md) section 1), for the caller or for another user.

**Request:** two routes, one ACL operation each (one method, one permission); both share the same logic.

| Route | Returns | ACL operation |
|---|---|---|
| `GET /v1/platform-users/me/roles` | The caller's roles (`me` alias) | `platform_users.roles.self` |
| `GET /v1/platform-users/{email}/roles` | Any user's roles, including the caller's | `platform_users.roles` |

**Logic** (admin roster, rule 1; direct or nested):
- `USER`: always (any authenticated user of the domain).
- `BU_ADMIN`: member of `BU_ADMINS_GROUP` (IT Admins are, through nesting).
- `IT_ADMIN`: member of `IT_ADMINS_GROUP`.
- `PLATFORM_ADMIN`: member of a group in `LSB_PLATFORM_ADMIN_GROUPS` (reserved for future use; today the same people as `BU_ADMIN`).

Roles are listed in that order.

**Authorization:** common ACL, checked on the route only (no check inside the operation): `platform_users.roles.self` for `USER`; `platform_users.roles` for `IT_ADMIN` and `BU_ADMIN`.

**Response `200`:**
```json
{
  "email": "admin@shankyram.altostrat.com",
  "roles": ["USER", "BU_ADMIN", "IT_ADMIN", "PLATFORM_ADMIN"],
  "groups": [
    { "group": "grp-lsb-bu-admins@shankyram.altostrat.com", "relation": "INDIRECT" },
    { "group": "grp-lsb-it-admins@shankyram.altostrat.com", "relation": "DIRECT" }
  ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `email` | string | yes | The user looked up (lowercase) |
| `roles` | list of enum | yes | Every role held: `USER`, `BU_ADMIN`, `IT_ADMIN`, `PLATFORM_ADMIN` (always at least `USER`) |
| `groups` | list of `{group, relation}` | yes | Admin groups from settings the user is in; `relation` is `DIRECT` or `INDIRECT` (through a nested group). Empty for a plain user |

Pydantic model: `PlatformRolesResponse` in `src/api/lsb_api/models/platform_users.py`.

**Errors** ([tdd-apis-common-models.md](tdd-apis-common-models.md) section 5): `400 INVALID_REQUEST` (not an email), `401`, `403` (`{email}` route without an allowed role), `500 INTERNAL` (admin roster not loaded yet; details in the API log).

**CLI:** `lsb platform-users roles [EMAIL]`
```
$ lsb platform-users roles
  ✔ admin@shankyram.altostrat.com    USER  BU_ADMIN  IT_ADMIN  PLATFORM_ADMIN
      member of grp-lsb-bu-admins@shankyram.altostrat.com (nested)
      member of grp-lsb-it-admins@shankyram.altostrat.com (direct)

$ lsb platform-users roles lsb-student1@shankyram.altostrat.com
  ✔ lsb-student1@shankyram.altostrat.com    USER
```

**Test in the live environment:** as `admin@`: all four roles; `lsb-bu-biz1@` gives `USER BU_ADMIN PLATFORM_ADMIN`; `lsb-student1@` gives `USER`. As `lsb-student1@`: own roles `USER`; asking for any email (the `{email}` route) gives exit `2` (`403`).
