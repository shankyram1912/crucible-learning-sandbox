"""DirectoryReader tests with a stub HTTP session (no GCP calls)."""

import pytest

from lsb_api.directory import DirectoryError, DirectoryReader


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, str(body)

    def json(self):
        return self._body


class StubSession:
    def __init__(self, pages):
        self.pages, self.calls = list(pages), []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        return self.pages.pop(0)


def m(group, relation="DIRECT", roles=("MEMBER",), security=True, name="groups/x"):
    labels = {"cloudidentity.googleapis.com/groups.discussion_forum": ""}
    if security:
        labels["cloudidentity.googleapis.com/groups.security"] = ""
    return {"groupKey": {"id": group}, "group": name, "displayName": group.split("@")[0],
            "relationType": relation, "roles": [{"role": r} for r in roles], "labels": labels}


def test_direct_and_nested_groups_across_pages():
    s = StubSession([
        Resp(200, {"memberships": [m("grp-cs100-students@x.com")], "nextPageToken": "p2"}),
        Resp(200, {"memberships": [m("grp-lsb-bu-admins@x.com", relation="INDIRECT", roles=()),
                                   m("GRP-BA101-STUDENTS@x.com")]}),
    ])
    r = DirectoryReader(session=s)
    groups = r.user_groups("Lsb-Student2@x.com")
    assert [g.email for g in groups] == ["grp-ba101-students@x.com", "grp-cs100-students@x.com",
                                         "grp-lsb-bu-admins@x.com"]
    assert groups[2].relation == "INDIRECT" and groups[0].roles == ("MEMBER",)
    url, params = s.calls[0]
    assert url.endswith("/groups/-/memberships:searchTransitiveGroups")
    assert "member_key_id == 'lsb-student2@x.com'" in params["query"]
    assert "groups.discussion_forum' in labels" in params["query"]
    assert s.calls[1][1]["pageToken"] == "p2"


def test_direct_entry_wins_over_nested_duplicate():
    s = StubSession([Resp(200, {"memberships": [m("g@x.com", relation="INDIRECT", roles=()), m("g@x.com")]})])
    (g,) = DirectoryReader(session=s).user_groups("u@x.com")
    assert g.relation == "DIRECT"


def test_cache_and_refresh():
    s = StubSession([Resp(200, {"memberships": [m("g@x.com")]}), Resp(200, {"memberships": []})])
    r = DirectoryReader(session=s, cache_seconds=300)
    assert r.is_member("G@x.com", "u@x.com")
    assert r.is_member("g@x.com", "u@x.com") and len(s.calls) == 1   # cached
    assert r.user_groups("u@x.com", refresh=True) == [] and len(s.calls) == 2


def test_no_groups():
    r = DirectoryReader(session=StubSession([Resp(200, {})]))
    assert r.user_groups("u@x.com") == []


def test_error_is_raised_with_status():
    r = DirectoryReader(session=StubSession([Resp(403, {"error": {"message": "denied"}})]))
    with pytest.raises(DirectoryError) as e:
        r.user_groups("u@x.com")
    assert e.value.status == 403 and "denied" in str(e.value)


def test_rejects_quote_in_email():
    with pytest.raises(DirectoryError):
        DirectoryReader(session=StubSession([])).user_groups("a'b@x.com")


def test_group_members_follows_nesting_and_skips_group_entries():
    s = StubSession([
        Resp(200, {"name": "groups/bu"}),
        Resp(200, {"memberships": [
            {"member": "groups/it", "preferredMemberKey": [{"id": "grp-lsb-it-admins@x.com"}], "relationType": "DIRECT"},
            {"member": "users/1", "preferredMemberKey": [{"id": "Admin@x.com"}], "relationType": "INDIRECT"},
        ], "nextPageToken": "p2"}),
        Resp(200, {"memberships": [
            {"member": "users/2", "preferredMemberKey": [{"id": "lsb-bu-biz1@x.com"}], "relationType": "DIRECT"},
            {"member": "users/1", "preferredMemberKey": [{"id": "admin@x.com"}], "relationType": "DIRECT"},
        ]}),
    ])
    members = DirectoryReader(session=s).group_members("GRP-LSB-BU-ADMINS@x.com")
    assert members == {"admin@x.com": "DIRECT", "lsb-bu-biz1@x.com": "DIRECT"}
    assert s.calls[0][1] == {"groupKey.id": "grp-lsb-bu-admins@x.com"}
    assert s.calls[1][0].endswith("/groups/bu/memberships:searchTransitiveMemberships")
    assert s.calls[2][1]["pageToken"] == "p2"


def test_group_members_lookup_error():
    with pytest.raises(DirectoryError):
        DirectoryReader(session=StubSession([Resp(404, {})])).group_members("nope@x.com")
