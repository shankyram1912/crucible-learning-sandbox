# LSB Control Tower TDD: APIs, Platform Users Domain

> Parent: [tdd-apis-master.md](tdd-apis-master.md)

Platform users are the people with a **platform role**: IT Admins and BU Admins. Their group membership is managed outside the platform by people with directory rights (Admin console); **the platform only reads it** ([tdd-master.md](../tdd-master.md) section 2.2). This domain answers who has which platform role. Listing platform users (with filters such as IT Admins, BU Admins, mapped Playground Folders, playground users and projects) comes later, once Playground Folders and playgrounds exist.

| # (build order) | Operation | REST | CLI | Status |
|---|---|---|---|---|
| 04 | Platform role | `GET /v1/platform-users/role` | `lsb platform-users role [EMAIL]` | Built, to test live |

Replaces the `group members` rows (10 to 12) of [apis-v0-interface.md](../../specs-reference/apis-v0-interface.md) A.2 and B for the service groups; the platform no longer changes membership.

---

## 1. Common rules

1. **Admin roster in memory:** platform roles and personas come from an in-memory roster of the **transitive user members of the admin groups in settings** (`IT_ADMINS_GROUP`, `BU_ADMINS_GROUP`, and any group in `LSB_PLATFORM_ADMIN_GROUPS`), so a role check never calls the directory on the request path (`src/api/lsb_api/admin_roster.py`).
   - **Loaded at startup** as the final step before the API serves requests: one Cloud Identity `searchTransitiveMemberships` call (paged) per admin group, following nested groups (`DirectoryReader.group_members`).
   - **Refreshed in the background** every `LSB_ADMIN_ROSTER_REFRESH_SECONDS` (default 300). A refresh replaces the roster only if every group was read; on failure the previous roster stays and the next cycle retries.
   - **Never loaded** (directory unreadable since startup): role and persona checks answer `500 INTERNAL` until a refresh succeeds.
   - **Staleness:** a membership change in the Admin console applies within one refresh period.
2. **Only admins are cached.** Students and other users are never loaded; anyone not in the roster is `OTHER`. Student and playground checks are designed with the playground operations.
3. **Identity:** the roster is read as the API's own identity (ADC locally, `sa-lsb-api` deployed), which needs read access to group memberships. No directory write rights anywhere.
4. **Synchronous, read-only;** not a job.

---

## 2. Operation 04: platform role

**Purpose:** the platform role of the caller, or of another user (Platform Admins only).

**Request:** `GET /v1/platform-users/role[?email=<user email>]`

| Parameter | Required | Description |
|---|---|---|
| `email` | no | Another user's email. Without it, or when it is the caller's own email, the caller's role is returned |

**Logic** (admin roster, rule 1; direct or nested):
1. In `IT_ADMINS_GROUP`: `IT_ADMIN`.
2. Otherwise in `BU_ADMINS_GROUP`: `BU_ADMIN`.
3. Otherwise: `OTHER`.

IT Admins are also BU Admins through nesting; the highest role wins.

**Authorization:** common ACL ([tdd-apis-common-acl.md](tdd-apis-common-acl.md)): `platform_users.role` (own role) for any user (`USER`); `platform_users.role.other` (someone else's, checked when `email` is another user) for `IT_ADMIN` and `BU_ADMIN`.

**Response `200`:**
```json
{
  "email": "lsb-it-admin1@shankyram.altostrat.com",
  "platform_role": "IT_ADMIN",
  "matched_group": "grp-lsb-it-admins@shankyram.altostrat.com",
  "relation": "DIRECT"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `email` | string | yes | The user looked up (lowercase) |
| `platform_role` | enum | yes | `IT_ADMIN`, `BU_ADMIN` or `OTHER` |
| `matched_group` | string | no | The settings group that gave the role; absent for `OTHER` |
| `relation` | enum | no | `DIRECT`, or `INDIRECT` when the user is in that group through a nested group; absent for `OTHER` |

Pydantic model: `PlatformRoleResponse` in `src/api/lsb_api/models/platform_users.py`.

**Errors** ([tdd-apis-common-models.md](tdd-apis-common-models.md) section 5): `400 INVALID_REQUEST` (not an email), `401`, `403` (role not allowed by the ACL), `500 INTERNAL` (admin roster not loaded yet; details in the API log).

**CLI:** `lsb platform-users role [EMAIL]`
```
$ lsb platform-users role
  ✔ lsb-it-admin1@shankyram.altostrat.com    IT_ADMIN (IT Admin)    member of grp-lsb-it-admins@shankyram.altostrat.com directly

$ lsb platform-users role lsb-student1@shankyram.altostrat.com
  – lsb-student1@shankyram.altostrat.com    OTHER (no platform role)
```

**Test in the live environment:** as `admin@`: own role `IT_ADMIN` (direct); `lsb-bu-biz1@` gives `BU_ADMIN`; `lsb-student1@` gives `OTHER`. As `lsb-student1@`: own role `OTHER` (exit `0`); asking for another email gives exit `2` (`403`).
