"""Directory reads: which Google Groups a user belongs to.

The platform only reads the directory (specs/tdd-master.md section 2.2). One call to the Cloud Identity
API (`groups.memberships.searchTransitiveGroups`) returns every group a user is in, directly or through
nested groups. Results are cached per user for a short time.

Runs as the API's own identity (ADC locally). Calls are billed to the ADC quota project, or to
GOOGLE_CLOUD_QUOTA_PROJECT when set (source src/terraform/control-tower/initialize.sh).

Standalone:
    cd src/api && uv run python -m lsb_api.directory lsb-student2@shankyram.altostrat.com [more emails] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from dataclasses import asdict, dataclass, field

CLOUD_IDENTITY = "https://cloudidentity.googleapis.com/v1"
GOOGLE_GROUP_LABEL = "cloudidentity.googleapis.com/groups.discussion_forum"
SECURITY_LABEL = "cloudidentity.googleapis.com/groups.security"


class DirectoryError(Exception):
    """A directory call failed (permission, quota, network)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class UserGroup:
    email: str                      # group email, for example grp-cs100-students@shankyram.altostrat.com
    name: str                       # Cloud Identity resource name, groups/<id>
    display_name: str
    relation: str                   # DIRECT or INDIRECT (through a nested group)
    roles: tuple[str, ...] = ()     # MEMBER, MANAGER, OWNER (for DIRECT memberships)
    security: bool = False          # carries the security label


@dataclass
class _CacheEntry:
    at: float
    groups: list[UserGroup] = field(default_factory=list)


class DirectoryReader:
    """Reads group memberships with the API's own credentials."""

    def __init__(self, session=None, cache_seconds: float = 300.0, page_size: int = 200):
        if session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            session = AuthorizedSession(creds)
        self._session = session
        self._ttl = cache_seconds
        self._page_size = page_size
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    def user_groups(self, email: str, *, refresh: bool = False) -> list[UserGroup]:
        """Every group `email` belongs to, directly or through nesting, sorted by group email."""
        email = email.strip().lower()
        with self._lock:
            hit = self._cache.get(email)
            if hit and not refresh and time.monotonic() - hit.at < self._ttl:
                return list(hit.groups)
        groups = self._search(email)
        with self._lock:
            self._cache[email] = _CacheEntry(at=time.monotonic(), groups=groups)
        return list(groups)

    def group_emails(self, email: str) -> set[str]:
        return {g.email for g in self.user_groups(email)}

    def is_member(self, group_email: str, member_email: str) -> bool:
        return group_email.strip().lower() in self.group_emails(member_email)

    def group_members(self, group_email: str) -> dict[str, str]:
        """Transitive user members of a group: {user email: DIRECT or INDIRECT}. Nested groups are followed, not listed."""
        group_email = group_email.strip().lower()
        r = self._session.get(f"{CLOUD_IDENTITY}/groups:lookup", params={"groupKey.id": group_email}, timeout=10)
        if r.status_code != 200:
            raise DirectoryError(f"group lookup failed for {group_email} ({r.status_code}): {r.text[:200]}", r.status_code)
        name = r.json()["name"]
        members: dict[str, str] = {}
        token = None
        while True:
            params = {"pageSize": self._page_size}
            if token:
                params["pageToken"] = token
            r = self._session.get(f"{CLOUD_IDENTITY}/{name}/memberships:searchTransitiveMemberships",
                                  params=params, timeout=10)
            if r.status_code != 200:
                raise DirectoryError(f"searchTransitiveMemberships failed for {group_email} ({r.status_code}): "
                                     f"{r.text[:200]}", r.status_code)
            body = r.json()
            for m in body.get("memberships", []):
                if str(m.get("member", "")).startswith("groups/"):
                    continue  # a nested group; its users are listed separately
                relation = m.get("relationType", "DIRECT")
                for key in m.get("preferredMemberKey", []) or []:
                    email = str(key.get("id", "")).lower()
                    if email and (email not in members or relation == "DIRECT"):
                        members[email] = relation
            token = body.get("nextPageToken")
            if not token:
                break
        return members

    def forget(self, email: str) -> None:
        with self._lock:
            self._cache.pop(email.strip().lower(), None)

    def _search(self, email: str) -> list[UserGroup]:
        if "'" in email:
            raise DirectoryError(f"invalid email: {email!r}")
        query = f"member_key_id == '{email}' && '{GOOGLE_GROUP_LABEL}' in labels"
        found: dict[str, UserGroup] = {}
        token = None
        while True:
            params = {"query": query, "pageSize": self._page_size}
            if token:
                params["pageToken"] = token
            r = self._session.get(f"{CLOUD_IDENTITY}/groups/-/memberships:searchTransitiveGroups",
                                  params=params, timeout=10)
            if r.status_code != 200:
                try:
                    msg = r.json().get("error", {}).get("message", r.text)
                except ValueError:
                    msg = r.text
                raise DirectoryError(f"searchTransitiveGroups failed ({r.status_code}): {msg}", r.status_code)
            body = r.json()
            for m in body.get("memberships", []):
                g = UserGroup(
                    email=str(m.get("groupKey", {}).get("id", "")).lower(),
                    name=m.get("group", ""),
                    display_name=m.get("displayName", ""),
                    relation=m.get("relationType", "DIRECT"),
                    roles=tuple(x.get("role", "") for x in m.get("roles", []) if x.get("role")),
                    security=SECURITY_LABEL in (m.get("labels") or {}),
                )
                # Keep the DIRECT entry if a group is reachable both directly and through nesting.
                if g.email and (g.email not in found or g.relation == "DIRECT"):
                    found[g.email] = g
            token = body.get("nextPageToken")
            if not token:
                break
        return sorted(found.values(), key=lambda g: g.email)


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m lsb_api.directory",
                                description="List the Google Groups each user is in (direct and nested).")
    p.add_argument("emails", nargs="+", help="user (or group) emails")
    p.add_argument("--json", action="store_true", help="print JSON")
    args = p.parse_args(argv)
    reader = DirectoryReader(cache_seconds=0)
    out, rc = {}, 0
    for email in args.emails:
        try:
            out[email] = [asdict(g) for g in reader.user_groups(email)]
        except DirectoryError as exc:
            out[email] = {"error": str(exc)}
            rc = 1
    if args.json:
        print(json.dumps(out, indent=2))
        return rc
    for email, groups in out.items():
        print(f"\n{email}")
        if isinstance(groups, dict):
            print(f"  ✖ {groups['error']}")
            continue
        if not groups:
            print("  (no groups)")
        for g in groups:
            via = "direct" if g["relation"] == "DIRECT" else "nested"
            roles = ",".join(g["roles"]) if g["roles"] else ""
            print(f"  {g['email']:<48} {via:<7} {roles:<8} {g['display_name']}")
    print()
    return rc


if __name__ == "__main__":
    sys.exit(_main())
