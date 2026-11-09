# LSB Control Tower TDD: APIs, Common Auth

> Parent: [tdd-apis-master.md](tdd-apis-master.md)

Authentication, authorization and tokens for all API domains, and the read-only Firestore path for a future UI. Request headers and the server-built request context are in [tdd-apis-common-models.md](tdd-apis-common-models.md).

---

## 1. Authentication (always on)
1. Every request carries `Authorization: Bearer <ID token>`. Requests without a valid token get `401`, including requests from localhost. Two token types are accepted:
   - **Google ID token** (issuer `accounts.google.com`), used by the CLI. The CLI gets it from the user's **ADC** (`gcloud auth application-default login`): one ADC refresh returns both the ID token and the access token (`openid`, `email` and `cloud-platform` are among ADC's default scopes), so `lsb` needs no separate login. Its `aud` is one of gcloud's public client IDs (the ADC client for current logins, the gcloud CLI client for older ones), both accepted through `LSB_ALLOWED_AUDIENCES` ([tdd-apis-common-config.md](tdd-apis-common-config.md)). **Decided (2026-11-09): no separate `lsb` OAuth client.** The shared gcloud audience only lets a token be replayed by something already running with the user's gcloud credentials, which also holds the user's `cloud-platform` access token and can do more in GCP directly than through this API; config-stage changes run with the caller's own token, so GCP enforces their real rights. An own Desktop OAuth client stays possible later without code changes (`gcloud auth application-default login --client-id-file=...` plus its ID in `LSB_ALLOWED_AUDIENCES`), but is not planned.
   - **Firebase ID token** (issuer `securetoken.google.com/<project>`), used by a future UI signed in with Firebase Auth (Google sign-in). Its `aud` is the Firebase project ID, which the UI step adds to `LSB_ALLOWED_AUDIENCES`.
2. For either type, the API verifies the token signature, issuer, expiry, allowed audience (`LSB_ALLOWED_AUDIENCES`), **`email_verified` is true**, and the user belongs to the org domain `DOMAIN` (`shankyram.altostrat.com`): the **`hd` (hosted domain) claim** must equal it, not just the email suffix. **Only ID tokens are accepted as identity**; an access token in `Authorization` is rejected with `401`. Every request logs `client.id` (the token's audience). The caller's identity is the **email in the verified token**; the rest of the API does not care which type it was.
3. The API **never trusts identity claimed by the client** (for example an `X-User` header).
4. **Authorization** is decided by the API from the verified email, its group memberships and, for creation, the caller's own GCP rights ([tdd-master.md](../tdd-master.md) section 2). Failing it returns `403`.
   - **Personas:** IT Admin (`grp-lsb-it-admins@`), BU Admin (`grp-lsb-bu-admins@`, IT Admins included through nesting), Platform Admin (any group in `LSB_PLATFORM_ADMIN_GROUPS`, today `grp-lsb-bu-admins@`; see [tdd-apis-common-models.md](tdd-apis-common-models.md) section 3), Playground Folder controller, playground owner, student.
   - **Creation gates:** Playground Folders: caller in `grp-lsb-it-admins@`; playgrounds: caller in `grp-lsb-bu-admins@` (IT Admins included). In both cases the caller must also hold `resourcemanager.folders.create`, `resourcemanager.folders.setIamPolicy` and `resourcemanager.tagValueBindings.create` on the parent folder in standard GCP IAM.
   - **Group membership** is never changed by the API: people with directory rights manage all groups (Admin console). The API only reads memberships.
5. **User access token.** Alongside the ID token, the client sends the caller's Google OAuth **access token** in `X-LSB-Access-Token` (CLI: from the same ADC refresh; UI: from Google sign-in with the `cloud-platform` scope). The API uses it, as the user, for the **config stage**: the creation-gate checks (`testIamPermissions`), the folder picker, and creating Playground Folders and playgrounds (folders, IAM bindings, tags). It is used only within the request and never stored. The **pipeline stage** (Terraform after a playground is configured) runs as the platform: Cloud Run's service account starts a predefined Cloud Build trigger that runs as the Terraform runner ([tdd-master.md](../tdd-master.md) section 2.10).

## 2. Clients get tokens differently, the API treats them the same
| Client | Where the token comes from |
|---|---|
| **CLI** | The user's ADC, via `google-auth` (ID token and access token from one refresh) |
| **Future UI on Cloud Run** (Control Tower) | The user signs in with Google through **Firebase Auth** in the browser; the UI passes the **user's** Firebase ID token to the API as the bearer, and uses the same sign-in for its read-only Firestore listeners |

- A UI backend must **pass the user's token through**, never call the API with its own service account token. Otherwise every request looks like the same service account and persona checks break.
- Adding a UI later needs no change to the API's endpoints; only Firebase ID token verification is added to authentication.

---

## 3. UI live state: read-only Firestore access (future UI)
| Kind of call | UI | CLI |
|---|---|---|
| **Live state** (job and task progress, cohort status, lists) | Reads Firestore directly with real-time listeners | Polls the API (`GET /v1/jobs/{id}`, `lsb job watch`) |
| **Changes** | Calls the Self Service APIs | Calls the Self Service APIs |

What the direct read path requires (added by a later UI operation, not needed for the CLI-first MVP):
1. **Firebase enabled on the Control Tower project** (`firebase` API, a registered Web App for the client config). The existing database `lsb-control-tower-db` is used as is; the Firebase client SDK supports named databases.
2. **Firebase Auth with Google sign-in**, restricted to the org domain.
3. **Security rules on `lsb-control-tower-db`:**
   - **All client writes denied.** Only the API (its service account, through IAM) writes.
   - Reads allowed only for what the caller may see (for example a cohort's jobs only for that cohort's admins).
   - Rules cannot look up Google Group membership, so the API maintains each user's personas and cohorts as **Firebase custom claims** or in a **membership document** the rules read.
4. **The API stays the source of truth.** The UI never derives state on its own beyond displaying what the API wrote.
