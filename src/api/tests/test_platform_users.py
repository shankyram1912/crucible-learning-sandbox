"""Platform users domain tests: GET /v1/platform-users/me/roles and /{email}/roles (admin roster)."""

from tests.test_health import ADMIN, STUDENT, FakeRoster, auth, client

IT = "grp-lsb-it-admins@shankyram.altostrat.com"
BU = "grp-lsb-bu-admins@shankyram.altostrat.com"
BU_USER = "lsb-bu-biz1@shankyram.altostrat.com"
GROUPS = {ADMIN: {IT: "DIRECT", BU: "INDIRECT"}, BU_USER: {BU: "DIRECT"}}


def app_with(groups=GROUPS, loaded=True):
    c, app = client()
    app.state.roster = FakeRoster(groups, loaded)
    return c


def test_it_admin_holds_all_roles():
    r = app_with().get("/v1/platform-users/me/roles", headers=auth("admin"))
    assert r.status_code == 200
    assert r.json() == {"email": ADMIN, "roles": ["USER", "BU_ADMIN", "IT_ADMIN", "PLATFORM_ADMIN"],
                        "groups": [{"group": BU, "relation": "INDIRECT"}, {"group": IT, "relation": "DIRECT"}]}


def test_bu_admin_roles():
    r = app_with().get("/v1/platform-users/me/roles", headers=auth("bu"))
    assert r.json()["roles"] == ["USER", "BU_ADMIN", "PLATFORM_ADMIN"]


def test_student_is_user_only():
    r = app_with().get("/v1/platform-users/me/roles", headers=auth("student"))
    assert r.status_code == 200
    assert r.json() == {"email": STUDENT, "roles": ["USER"], "groups": []}


def test_admin_can_look_up_someone_else():
    r = app_with().get(f"/v1/platform-users/{BU_USER.upper()}/roles", headers=auth("admin"))
    assert r.status_code == 200 and r.json()["email"] == BU_USER and "BU_ADMIN" in r.json()["roles"]


def test_student_cannot_look_up_someone_else():
    r = app_with().get(f"/v1/platform-users/{ADMIN}/roles", headers=auth("student"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "PERMISSION_DENIED"


def test_invalid_email():
    r = app_with().get("/v1/platform-users/not-an-email/roles", headers=auth("admin"))
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_roster_not_loaded_is_500():
    r = app_with(loaded=False).get("/v1/platform-users/me/roles", headers=auth("student"))
    assert r.status_code == 500 and r.json()["error"]["code"] == "INTERNAL"


def test_student_cannot_use_email_route_even_for_self():
    r = app_with().get(f"/v1/platform-users/{STUDENT}/roles", headers=auth("student"))
    assert r.status_code == 403   # own roles go through /me/roles


def test_admin_email_route_for_self():
    r = app_with().get(f"/v1/platform-users/{ADMIN}/roles", headers=auth("admin"))
    assert r.status_code == 200 and r.json()["email"] == ADMIN



def test_acl_and_roles_api_use_the_same_roles(monkeypatch):
    """One implementation (context.roles_of): the roles the API returns are the roles the ACL decides with."""
    from lsb_api import acl
    seen = {}
    real = acl.personas

    def spy(request, ctx, **kw):
        seen[ctx.caller.email] = real(request, ctx, **kw)
        return seen[ctx.caller.email]

    monkeypatch.setattr(acl, "personas", spy)
    c = app_with()
    for who in ("admin", "bu"):
        c.get("/v1/health/db", headers=auth(who))   # IT_ADMIN route, so the ACL reads roles
    assert len(seen) == 2
    for email, held in seen.items():
        api = c.get(f"/v1/platform-users/{email}/roles", headers=auth("admin")).json()
        assert set(api["roles"]) == held, email


def test_caller_roles_computed_once_per_request(monkeypatch):
    """Admin asking for their own email: the ACL and the API share the per-request cache."""
    from lsb_api import context
    calls = []
    real = context.roles_of
    monkeypatch.setattr(context, "roles_of", lambda request, email, **kw: calls.append(email) or real(request, email, **kw))
    r = app_with().get(f"/v1/platform-users/{ADMIN}/roles", headers=auth("admin"))
    assert r.status_code == 200 and calls == [ADMIN]
