"""Health domain tests (specs/tdd-apis/tdd-apis-health.md section 6), with fakes for token,
group membership and Firestore so they run without GCP."""

import pytest
from fastapi.testclient import TestClient

from lsb_api.context import Caller
from lsb_api.errors import ApiError
from lsb_api.main import create_app
from lsb_api.models.common import ErrorCode, TokenType
from lsb_api.models.health import CheckStatus, DatabaseCheck, DatabaseError, DatabaseRole
from lsb_api.settings import Settings

ADMIN = "lsb-it-admin1@shankyram.altostrat.com"
STUDENT = "lsb-student1@shankyram.altostrat.com"
BU_USER = "lsb-bu-biz1@shankyram.altostrat.com"
TOKEN = {"admin": "h.admin.s", "student": "h.student.s", "bu": "h.bu.s"}  # look like JWTs (3 parts)
AUD = "32555940559.apps.googleusercontent.com"


def settings(**over) -> Settings:
    base = dict(CT_PROJECT_ID="lsb-control-tower-e26", DOMAIN="shankyram.altostrat.com",
                FIRESTORE_CONFIG_DATABASE="lsb-control-tower-config-db", FIRESTORE_DATABASE="lsb-control-tower-db",
                IT_ADMINS_GROUP="grp-lsb-it-admins@shankyram.altostrat.com",
                BU_ADMINS_GROUP="grp-lsb-bu-admins@shankyram.altostrat.com", LSB_API_VERSION="test123")
    base.update(over)
    return Settings(**base)


class FakeVerifier:
    def verify(self, token):
        who = {TOKEN["admin"]: ADMIN, TOKEN["student"]: STUDENT, TOKEN["bu"]: BU_USER}.get(token)
        if not who:
            raise ApiError(ErrorCode.UNAUTHENTICATED, "Invalid ID token")
        return Caller(email=who, subject="123", token_type=TokenType.GOOGLE), AUD


class FakeRoster:
    """Admin roster for the fake users: ADMIN is in IT Admins (and BU Admins via nesting)."""

    GROUPS = {ADMIN: {"grp-lsb-it-admins@shankyram.altostrat.com": "DIRECT",
                      "grp-lsb-bu-admins@shankyram.altostrat.com": "INDIRECT"},
              "lsb-bu-biz1@shankyram.altostrat.com": {"grp-lsb-bu-admins@shankyram.altostrat.com": "DIRECT"}}

    def __init__(self, groups=None, loaded=True):
        self.groups_by_user = self.GROUPS if groups is None else groups
        self.loaded, self.refreshes, self.last_error = loaded, 0, None

    def refresh(self):
        self.refreshes += 1

    async def run(self):
        import asyncio
        await asyncio.Event().wait()

    def groups_of(self, email):
        from lsb_api.admin_roster import RosterNotLoaded
        if not self.loaded:
            raise RosterNotLoaded("not loaded")
        return dict(self.groups_by_user.get(email, {}))


class FakeDb:
    def __init__(self, fail_config: DatabaseError | None = None):
        self.fail_config, self.calls = fail_config, 0

    async def check_all(self, request_id):
        self.calls += 1
        cfg = (DatabaseCheck(database="lsb-control-tower-config-db", role=DatabaseRole.CONFIG,
                             status=CheckStatus.FAIL, latency_ms=3, error=self.fail_config)
               if self.fail_config else
               DatabaseCheck(database="lsb-control-tower-config-db", role=DatabaseRole.CONFIG,
                             status=CheckStatus.OK, latency_ms=41))
        rt = DatabaseCheck(database="lsb-control-tower-db", role=DatabaseRole.RUNTIME_JOBS,
                           status=CheckStatus.OK, latency_ms=38)
        return [cfg, rt]


def client(db=None, **over):
    app = create_app(settings(**over), verifier=FakeVerifier(), roster=FakeRoster(), db_checker=db or FakeDb())
    return TestClient(app), app


def auth(who):
    return {"Authorization": f"Bearer {TOKEN[who]}", "X-LSB-Session-Id": "s-test", "User-Agent": "lsb-cli/0.1.0"}


def test_health_api_ok_and_headers():
    c, _ = client()
    r = c.get("/v1/health/api", headers=auth("admin"))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "OK" and body["service"] == "lsb-api" and body["version"] == "test123"
    assert body["caller"] == ADMIN
    assert r.headers["X-Request-Id"].startswith("r-") and r.headers["X-LSB-Session-Id"] == "s-test"


def test_request_id_is_echoed():
    c, _ = client()
    r = c.get("/v1/health/api", headers={**auth("admin"), "X-Request-Id": "r-mine"})
    assert r.headers["X-Request-Id"] == "r-mine"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer"}, {"Authorization": "Bearer not-a-jwt-opaque-token"},
                                     {"Authorization": "Bearer a.b.c"}])
def test_unauthenticated(headers):
    c, _ = client()
    r = c.get("/v1/health/api", headers=headers)
    assert r.status_code == 401
    err = r.json()["error"]
    assert err["code"] == "UNAUTHENTICATED" and err["request_id"] == r.headers["X-Request-Id"]


def test_health_db_admin_ok():
    c, _ = client()
    r = c.get("/v1/health/db", headers=auth("admin"))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "OK"
    assert [d["role"] for d in body["databases"]] == ["CONFIG", "RUNTIME_JOBS"]
    assert all("error" not in d for d in body["databases"])


def test_health_db_forbidden_for_student():
    c, _ = client()
    r = c.get("/v1/health/db", headers=auth("student"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "PERMISSION_DENIED"


def test_health_db_failure_is_503_with_code():
    c, _ = client(db=FakeDb(fail_config=DatabaseError.DATABASE_NOT_FOUND))
    r = c.get("/v1/health/db", headers=auth("admin"))
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "FAIL" and body["databases"][0]["error"] == "DATABASE_NOT_FOUND"


def test_roster_loaded_at_startup():
    c, app = client()
    with c:
        c.get("/v1/health/api", headers=auth("admin"))
    assert app.state.roster.refreshes == 1


def test_platform_admin_persona_is_still_resolved_for_future_use():
    from lsb_api.context import personas_from_groups
    from lsb_api.models.common import Persona
    st = settings(LSB_PLATFORM_ADMIN_GROUPS="grp-ops@shankyram.altostrat.com")
    assert personas_from_groups(st, {"grp-ops@shankyram.altostrat.com"}) == {Persona.PLATFORM_ADMIN}
    assert Persona.PLATFORM_ADMIN in personas_from_groups(settings(), {"grp-lsb-bu-admins@shankyram.altostrat.com"})


def test_health_service_ok_and_no_db_details():
    c, _ = client()
    r = c.get("/v1/health/service", headers=auth("admin"))
    assert r.status_code == 200
    assert r.json() == {"status": "OK", "config": "OK", "runtime_jobs": "OK"}
    assert "lsb-control-tower" not in r.text and "latency" not in r.text


def test_health_service_not_ok_hides_error():
    c, _ = client(db=FakeDb(fail_config=DatabaseError.PERMISSION_DENIED))
    r = c.get("/v1/health/service", headers=auth("admin"))
    assert r.status_code == 503
    assert r.json() == {"status": "NOT_OK", "config": "NOT_OK", "runtime_jobs": "OK"}
    assert "PERMISSION_DENIED" not in r.text


def test_health_service_is_cached():
    db = FakeDb()
    c, _ = client(db=db)
    for _ in range(3):
        c.get("/v1/health/service", headers=auth("admin"))
    assert db.calls == 1


def test_health_service_cache_disabled():
    db = FakeDb()
    c, _ = client(db=db, LSB_HEALTH_SERVICE_CACHE_SECONDS=0)
    for _ in range(2):
        c.get("/v1/health/service", headers=auth("admin"))
    assert db.calls == 2


def test_settings_reject_same_databases():
    with pytest.raises(Exception):
        settings(FIRESTORE_DATABASE="lsb-control-tower-config-db")


def test_unknown_path_uses_error_shape():
    c, _ = client()
    r = c.get("/v1/nope", headers=auth("student"))
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


ACL_MATRIX = {   # path -> (admin = IT_ADMIN, bu = BU_ADMIN only, student = USER only)
    "/v1/health/api": (200, 200, 403),
    "/v1/health/db": (200, 403, 403),
    "/v1/health/service": (200, 200, 200),
    "/v1/platform-users/role": (200, 200, 200),
    "/v1/platform-users/role?email=lsb-it-admin1@shankyram.altostrat.com": (200, 200, 403),   # someone else
}


def test_acl_matrix():
    c, _ = client()
    for path, expected in ACL_MATRIX.items():
        got = tuple(c.get(path, headers=auth(who)).status_code for who in ("admin", "bu", "student"))
        assert got == expected, (path, got)


def test_acl_denied_message():
    c, _ = client()
    r = c.get("/v1/health/db", headers=auth("bu"))
    assert r.json()["error"]["message"] == "This operation needs one of these roles: IT_ADMIN"


def test_acl_from_settings_override():
    acl = {"health.api": ["USER"], "health.db": ["IT_ADMIN"], "health.service": ["USER"],
           "platform_users.role": ["USER"], "platform_users.role.other": ["IT_ADMIN"]}
    c, _ = client(LSB_ACL=acl)
    assert c.get("/v1/health/api", headers=auth("student")).status_code == 200


def test_acl_missing_operation_refuses_to_start():
    import pytest
    acl = {"health.api": ["USER"]}
    with pytest.raises(RuntimeError, match="operations without an ACL entry"):
        client(LSB_ACL=acl)


def test_acl_unknown_operation_refuses_to_start():
    import pytest
    from lsb_api.settings import DEFAULT_ACL
    acl = {**DEFAULT_ACL, "typo.op": ["USER"]}
    with pytest.raises(RuntimeError, match="unknown operations"):
        client(LSB_ACL=acl)


def test_acl_unknown_role_is_rejected_by_settings():
    import pytest
    with pytest.raises(Exception, match="unknown role"):
        settings(LSB_ACL={"health.api": ["SUPERUSER"]})


def test_user_role_does_not_need_the_roster():
    c, app = client()
    app.state.roster.loaded = False
    assert c.get("/v1/health/service", headers=auth("student")).status_code == 200
    assert c.get("/v1/health/api", headers=auth("admin")).status_code == 500
