"""Platform users domain tests: GET /v1/platform-users/role (admin roster)."""

from tests.test_health import ADMIN, STUDENT, FakeRoster, auth, client

IT = "grp-lsb-it-admins@shankyram.altostrat.com"
BU = "grp-lsb-bu-admins@shankyram.altostrat.com"
BU_USER = "lsb-bu-biz1@shankyram.altostrat.com"
GROUPS = {ADMIN: {IT: "DIRECT", BU: "INDIRECT"}, BU_USER: {BU: "DIRECT"}}


def app_with(groups=GROUPS, loaded=True):
    c, app = client()
    app.state.roster = FakeRoster(groups, loaded)
    return c


def test_own_role_it_admin_wins_over_nested_bu():
    r = app_with().get("/v1/platform-users/role", headers=auth("admin"))
    assert r.status_code == 200
    assert r.json() == {"email": ADMIN, "platform_role": "IT_ADMIN", "matched_group": IT, "relation": "DIRECT"}


def test_other_role_for_non_admin():
    r = app_with().get(f"/v1/platform-users/role?email={STUDENT}", headers=auth("admin"))
    assert r.json() == {"email": STUDENT, "platform_role": "OTHER", "matched_group": None, "relation": None}


def test_platform_admin_can_look_up_someone_else():
    r = app_with().get(f"/v1/platform-users/role?email={BU_USER.upper()}", headers=auth("admin"))
    assert r.status_code == 200
    assert r.json()["platform_role"] == "BU_ADMIN" and r.json()["email"] == BU_USER


def test_non_admin_cannot_call_it():
    r = app_with().get(f"/v1/platform-users/role?email={ADMIN}", headers=auth("student"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "PERMISSION_DENIED"


def test_bu_admin_own_role():
    r = app_with().get("/v1/platform-users/role", headers=auth("bu"))
    assert r.status_code == 200 and r.json()["platform_role"] == "BU_ADMIN" and r.json()["relation"] == "DIRECT"


def test_invalid_email():
    r = app_with().get("/v1/platform-users/role?email=not-an-email", headers=auth("admin"))
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_roster_not_loaded_is_500():
    r = app_with(loaded=False).get("/v1/platform-users/role", headers=auth("admin"))
    assert r.status_code == 500 and r.json()["error"]["code"] == "INTERNAL"


def test_student_own_role_is_other():
    r = app_with().get("/v1/platform-users/role", headers=auth("student"))
    assert r.status_code == 200 and r.json()["platform_role"] == "OTHER"
