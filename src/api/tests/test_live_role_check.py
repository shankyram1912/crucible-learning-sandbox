"""LSB_ROLE_CHECK_USE_CACHE=false: ACL role checks read the directory live and refresh the roster."""

import pytest
from fastapi.testclient import TestClient

from lsb_api.admin_roster import AdminRoster, RosterNotLoaded
from lsb_api.directory import DirectoryError, UserGroup
from lsb_api.main import create_app
from tests.test_health import ADMIN, STUDENT, FakeDb, FakeVerifier, auth, settings

IT = "grp-lsb-it-admins@shankyram.altostrat.com"
BU = "grp-lsb-bu-admins@shankyram.altostrat.com"
OTHER_GROUP = "grp-cs100-students@shankyram.altostrat.com"


class Reader:
    """Directory stub: `roster` answers the full load, `live` answers per-user live reads."""

    def __init__(self, roster, live, fail_live=False):
        self.roster, self.live, self.fail_live, self.live_calls = roster, live, fail_live, []

    def group_members(self, group):
        return dict(self.roster.get(group, {}))

    def user_groups(self, email, *, refresh=False):
        self.live_calls.append(email)
        if self.fail_live:
            raise DirectoryError("directory down", 503)
        return [UserGroup(email=g, name=f"groups/{g}", display_name=g, relation=rel)
                for g, rel in self.live.get(email, {}).items()]


# Cached roster: ADMIN is an IT Admin, STUDENT is nobody. Live directory: ADMIN was removed, STUDENT was added.
CACHED = {IT: {ADMIN: "DIRECT"}, BU: {ADMIN: "INDIRECT"}}
LIVE = {ADMIN: {OTHER_GROUP: "DIRECT"}, STUDENT: {BU: "DIRECT", OTHER_GROUP: "DIRECT"}}


def app_with(use_cache, reader, load=True):
    roster = AdminRoster(settings(), reader)
    if load:
        roster.refresh()
    app = create_app(settings(LSB_ROLE_CHECK_USE_CACHE=use_cache), verifier=FakeVerifier(), roster=roster,
                     db_checker=FakeDb())
    return TestClient(app), roster


def test_cache_mode_uses_roster_only():
    reader = Reader(CACHED, LIVE)
    c, _ = app_with(True, reader)
    assert c.get("/v1/health/api", headers=auth("admin")).status_code == 200
    assert c.get("/v1/health/api", headers=auth("student")).status_code == 403
    assert reader.live_calls == []


def test_live_mode_reads_directory_and_refreshes_roster():
    reader = Reader(CACHED, LIVE)
    c, roster = app_with(False, reader)
    assert c.get("/v1/health/api", headers=auth("student")).status_code == 200   # added in the directory
    assert c.get("/v1/health/api", headers=auth("admin")).status_code == 403     # removed in the directory
    assert reader.live_calls == [STUDENT, ADMIN]
    assert roster.groups_of(STUDENT) == {BU: "DIRECT"}   # only admin groups are kept
    assert roster.groups_of(ADMIN) == {}


def test_live_mode_user_operation_never_calls_directory():
    reader = Reader(CACHED, LIVE)
    c, _ = app_with(False, reader)
    assert c.get("/v1/health/service", headers=auth("student")).status_code in (200, 503)
    assert c.get("/v1/platform-users/me/roles", headers=auth("student")).status_code == 200
    assert reader.live_calls == []


def test_live_mode_roles_api_uses_cache_for_target():
    """Only the role check is live: the caller is read live, the looked-up user comes from the roster."""
    reader = Reader(CACHED, {**LIVE, ADMIN: {IT: "DIRECT"}})
    c, _ = app_with(False, reader)
    r = c.get(f"/v1/platform-users/{STUDENT}/roles", headers=auth("admin"))
    assert r.status_code == 200 and r.json()["roles"] == ["USER"]   # roster still says STUDENT is nobody
    assert reader.live_calls == [ADMIN]


def test_live_mode_reuses_live_result_for_own_email():
    reader = Reader(CACHED, {**LIVE, ADMIN: {IT: "DIRECT"}})
    c, _ = app_with(False, reader)
    r = c.get(f"/v1/platform-users/{ADMIN}/roles", headers=auth("admin"))
    assert r.json()["groups"] == [{"group": IT, "relation": "DIRECT"}]   # the live answer, not the roster's
    assert reader.live_calls == [ADMIN]


def test_live_mode_works_without_roster_load():
    reader = Reader(CACHED, LIVE)
    c, _ = app_with(False, reader, load=False)
    assert c.get("/v1/health/api", headers=auth("student")).status_code == 200


def test_live_mode_directory_failure_is_500_without_fallback():
    reader = Reader(CACHED, LIVE, fail_live=True)
    c, _ = app_with(False, reader)
    r = c.get("/v1/health/api", headers=auth("admin"))   # the cache would have allowed it
    assert r.status_code == 500 and r.json()["error"]["code"] == "INTERNAL"


def test_refresh_user_on_unloaded_roster_keeps_lookups_closed():
    roster = AdminRoster(settings(), Reader(CACHED, LIVE))
    assert roster.refresh_user(STUDENT) == {BU: "DIRECT"}
    with pytest.raises(RosterNotLoaded):
        roster.groups_of(STUDENT)
