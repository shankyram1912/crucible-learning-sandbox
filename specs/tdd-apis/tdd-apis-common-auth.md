# LSB Control Tower TDD: APIs, Common Auth

> Parent: [tdd-apis-master.md](tdd-apis-master.md)

Authentication, authorization and tokens for all API domains, and the read-only Firestore path for a future UI. Request headers and the server-built request context are in [tdd-apis-common-models.md](tdd-apis-common-models.md).

---

## 1. Authentication (always on)
1. Every request carries `Authorization: Bearer <ID token>`. Requests without a valid token get `401`, including requests from localhost. Two token types are accepted:
   - **Google ID token** (issuer `accounts.google.com`), used by the CLI.
   - **Firebase ID token** (issuer `securetoken.google.com/<project>`), used by a future UI signed in with Firebase Auth (Google sign-in).
2. For either type, the API verifies the token signature, issuer, expiry, allowed audience (configured list), and that the user belongs to the org domain (`shankyram.altostrat.com`). The caller's identity is the **email in the verified token**; the rest of the API does not care which type it was.
3. The API **never trusts identity claimed by the client** (for example an `X-User` header).
4. **Authorization** is decided by the API from the verified email, its group memberships and, for creation, the caller's own GCP rights ([tdd-master.md](../tdd-master.md) section 2). Failing it returns `403`.
   - **Personas:** IT Admin (`grp-lsb-it-admins@`), BU Admin (`grp-lsb-bu-admins@`, IT Admins included through nesting), Playground Folder controller, playground owner, student.
   - **Creation gates:** Playground Folders: caller in `grp-lsb-it-admins@`; playgrounds: caller in `grp-lsb-bu-admins@` (IT Admins included). In both cases the caller must also hold `resourcemanager.folders.create`, `resourcemanager.folders.setIamPolicy` and `resourcemanager.tagValueBindings.create` on the parent folder in standard GCP IAM.
   - **Group membership changes** for `grp-lsb-it-admins@` and `grp-lsb-bu-admins@`: IT Admins only.
5. **User access token.** Alongside the ID token, the client sends the caller's Google OAuth **access token** in `X-LSB-Access-Token` (CLI: from the gcloud login / ADC; UI: from Google sign-in with the `cloud-platform` scope). The API uses it, as the user, for the **config stage**: the creation-gate checks (`testIamPermissions`), the folder picker, and creating Playground Folders and playgrounds (folders, IAM bindings, tags). It is used only within the request and never stored. The **pipeline stage** (Terraform after a playground is configured) runs as the platform: Cloud Run's service account starts a predefined Cloud Build trigger that runs as the Terraform runner ([tdd-master.md](../tdd-master.md) section 2.10).

## 2. Clients get tokens differently, the API treats them the same
| Client | Where the token comes from |
|---|---|
| **CLI** | The user's gcloud login / ADC, via `google-auth` |
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
