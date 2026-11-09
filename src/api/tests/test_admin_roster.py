"""AdminRoster tests with a stub directory reader."""

import pytest

from lsb_api.admin_roster import AdminRoster, RosterNotLoaded
from tests.test_health import settings

IT = "grp-lsb-it-admins@shankyram.altostrat.com"
BU = "grp-lsb-bu-admins@shankyram.altostrat.com"


class Reader:
    def __init__(self, data, fail=False):
        self.data, self.fail, self.calls = data, fail, []

    def group_members(self, group):
        self.calls.append(group)
        if self.fail:
            raise RuntimeError("directory down")
        return self.data.get(group, {})


def test_loads_settings_groups_and_answers_lookups():
    reader = Reader({IT: {"a@x": "DIRECT"}, BU: {"a@x": "INDIRECT", "b@x": "DIRECT"}})
    r = AdminRoster(settings(), reader)
    r.refresh()
    assert sorted(reader.calls) == sorted([IT, BU])
    assert r.groups_of("A@x") == {IT: "DIRECT", BU: "INDIRECT"}
    assert r.groups_of("b@x") == {BU: "DIRECT"} and r.groups_of("c@x") == {}


def test_extra_platform_admin_group_is_loaded():
    reader = Reader({})
    AdminRoster(settings(LSB_PLATFORM_ADMIN_GROUPS="grp-ops@x"), reader).refresh()
    assert "grp-ops@x" in reader.calls


def test_not_loaded_raises():
    with pytest.raises(RosterNotLoaded):
        AdminRoster(settings(), Reader({})).groups_of("a@x")


def test_failed_refresh_keeps_previous_roster():
    reader = Reader({IT: {"a@x": "DIRECT"}})
    r = AdminRoster(settings(), reader)
    r.refresh()
    reader.fail = True
    with pytest.raises(RuntimeError):
        r.refresh()
    assert r.groups_of("a@x") == {IT: "DIRECT"}
