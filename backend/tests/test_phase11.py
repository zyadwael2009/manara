"""Phase 11 — low-priority audit fixes regression guards.

Guards for L1-L5 + L7. Every test names its finding.
"""
from __future__ import annotations

import io
import sys

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

    for mod in [
        "config", "models",
        "utils.permissions", "utils.grading", "utils.quizzes",
        "utils.certificates", "utils.analytics", "utils.attendance", "utils.timetables", "utils.assignments", "utils.rate_limit",
        "routes", "routes.auth", "routes.users",
        "routes.sections", "routes.grades", "routes.classes",
        "routes.courses", "routes.modules", "routes.lessons",
        "routes.enrollments", "routes.students",
        "routes.department_leaders", "routes.uploads",
        "routes.progress", "routes.grading_admin",
        "routes.rubrics", "routes.grade_reports",
        "routes.quizzes", "routes.quiz_take", "routes.quiz_admin",
        "routes.certificates", "routes.dashboards", "routes.parents", "routes.attendance", "routes.timetables", "routes.assignments",
        "app",
    ]:
        sys.modules.pop(mod, None)

    from app import create_app
    from config import Config
    from models import User, db

    inst = tmp_path / "instance"
    inst.mkdir()
    (inst / "uploads").mkdir()

    class TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
        TESTING = True
        SQLALCHEMY_ENGINE_OPTIONS = {}
        MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    app = create_app(TestConfig)
    app.instance_path = str(inst)

    with app.app_context():
        db.drop_all()
        db.create_all()
        u = User(name="Root Admin", email="admin@t.local", role="admin")
        u.set_password("adminpass1")
        db.session.add(u)
        db.session.commit()

    # Reset any lingering rate-limit state from a previous test run.
    from utils.rate_limit import _reset_all
    _reset_all()

    with app.test_client() as c:
        c.application = app
        yield c


def _h(tok):
    return {"X-Session-Token": tok}


def _login(client, *, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.data
    return r.get_json()["sessionToken"]


def _login_admin(client):
    return _login(client, email="admin@t.local", password="adminpass1")


# ============================================================================
# L1 — cert number entropy 32 → 64 bit
# ============================================================================
def test_l1_new_cert_numbers_are_64_bit(client):
    from utils.certificates import _generate_cert_number
    # Sample a batch — every one should be `LMS-YYYY-<16 hex chars>`.
    with client.application.app_context():
        for _ in range(20):
            num = _generate_cert_number()
            prefix, year, suffix = num.split("-")
            assert prefix == "LMS"
            assert len(year) == 4 and year.isdigit()
            assert len(suffix) == 16, f"expected 16-hex suffix, got {suffix!r}"
            assert all(c in "0123456789ABCDEF" for c in suffix), suffix


# ============================================================================
# L2 — public /verify rate limit
# ============================================================================
def test_l2_verify_rate_limits_at_30_per_minute(client):
    # 30 requests should all pass (with 404 body since the cert doesn't exist).
    for i in range(30):
        r = client.get(f"/api/verify/x-{i}")
        assert r.status_code == 404, f"request {i} unexpectedly {r.status_code}: {r.data}"
    # The 31st must trip the limiter.
    r = client.get("/api/verify/x-30")
    assert r.status_code == 429, r.data
    assert r.headers.get("Retry-After") is not None
    body = r.get_json()
    assert "too many" in body["error"].lower()


def test_l2_verify_allows_burst_from_different_ips(client):
    """The limit is per-IP. Different `Remote-Addr`s should have independent
    quotas. (Simulated by patching request.remote_addr for these calls.)"""
    # 15 from one IP, 15 from another → neither trips the limit.
    for i in range(15):
        r = client.get(f"/api/verify/a-{i}", environ_overrides={"REMOTE_ADDR": "10.0.0.1"})
        assert r.status_code == 404
    for i in range(15):
        r = client.get(f"/api/verify/b-{i}", environ_overrides={"REMOTE_ADDR": "10.0.0.2"})
        assert r.status_code == 404


# ============================================================================
# L3 — admin_create_user refuses role='admin'
# ============================================================================
def test_l3_admin_cannot_create_peer_admin(client):
    admin_tok = _login_admin(client)
    r = client.post("/api/users", json={
        "name": "Sneaky Admin", "email": "sneak@t.local",
        "password": "password12", "role": "admin",
    }, headers=_h(admin_tok))
    assert r.status_code == 400, r.data
    # Message should reference the role field.
    body = r.get_json()
    assert "role" in body["error"].lower()


def test_l3_admin_can_still_create_parent(client):
    """Sanity: L3 only removed 'admin', not the other roles."""
    admin_tok = _login_admin(client)
    r = client.post("/api/users", json={
        "name": "Parent", "email": "p@t.local",
        "password": "password12", "role": "parent",
    }, headers=_h(admin_tok))
    assert r.status_code == 201, r.data


# ============================================================================
# L4 — X-Session-Token silent-clear removed
# ============================================================================
def test_l4_bad_session_header_does_not_nuke_cookie_session(client):
    """A stale/corrupt X-Session-Token used to wipe the browser's cookie
    session; now it should be ignored and the cookie session survives."""
    # Log in — this sets a Flask cookie session (test client keeps cookies).
    _login_admin(client)
    # First check: authed request works via the cookie session (no header).
    r = client.get("/api/auth/me")
    assert r.status_code == 200

    # Now send a request WITH a garbage X-Session-Token header. Old behaviour
    # would `session.clear()` and drop the cookie. New behaviour ignores the
    # bad header — the cookie session persists and this request stays authed.
    r = client.get("/api/auth/me", headers={"X-Session-Token": "not-a-real-token"})
    assert r.status_code == 200, (
        f"bad X-Session-Token nuked cookie session (regression): {r.status_code}"
    )


# ============================================================================
# L5 — response envelope consistency
# ============================================================================
def test_l5_unlink_parent_returns_message_shape(client):
    """DELETE /api/users/<sid>/parents/<pid> used to return {"ok": true};
    should now match the {"message": ...} envelope."""
    admin_tok = _login_admin(client)
    h = _h(admin_tok)
    # Set up a linked parent → student pair.
    r = client.post("/api/sections", json={"name": "High"}, headers=h)
    high = r.get_json()["id"]
    r = client.post("/api/grades",
                    json={"name": "Grade 9", "sectionId": high, "orderIndex": 9},
                    headers=h)
    g9 = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "9-A", "gradeId": g9}, headers=h)
    c9a = r.get_json()["id"]
    r = client.post("/api/auth/register", json={
        "name": "K", "email": "kid@t.local", "password": "password12", "role": "student",
    })
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class", json={"classId": c9a}, headers=h)
    r = client.post("/api/users", json={
        "name": "P", "email": "p@t.local",
        "password": "password12", "role": "parent",
    }, headers=h)
    pid = r.get_json()["id"]
    client.post(f"/api/users/{sid}/parents",
                json={"parentId": pid, "relationship": "guardian"}, headers=h)

    r = client.delete(f"/api/users/{sid}/parents/{pid}", headers=h)
    assert r.status_code == 200
    body = r.get_json()
    assert "message" in body, f"envelope drift — got {body}"
    assert body.get("ok") is None, "{'ok': true} envelope still present"


# ============================================================================
# L7 — file upload negative branches
# ============================================================================
def _upload(client, tok, *, kind, filename, content, content_type=None):
    data = {"kind": kind, "file": (io.BytesIO(content), filename, content_type)}
    return client.post(
        "/api/uploads",
        data=data,
        headers=_h(tok),
        content_type="multipart/form-data",
    )


def test_l7_upload_missing_file_returns_400(client):
    admin_tok = _login_admin(client)
    r = client.post(
        "/api/uploads",
        data={"kind": "pdf"},
        headers=_h(admin_tok),
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
    body = r.get_json()
    assert "file" in body["error"].lower()


def test_l7_upload_unknown_kind_returns_400(client):
    admin_tok = _login_admin(client)
    r = _upload(client, admin_tok, kind="totally-fake", filename="x.pdf",
                content=b"%PDF-1.4 test", content_type="application/pdf")
    assert r.status_code == 400
    assert "kind" in r.get_json()["error"].lower()


def test_l7_upload_wrong_extension_returns_400(client):
    admin_tok = _login_admin(client)
    # kind=pdf but the file is a .mp4 → extension check refuses.
    r = _upload(client, admin_tok, kind="pdf", filename="x.mp4",
                content=b"junk", content_type="application/pdf")
    assert r.status_code == 400
    assert "extension" in r.get_json()["error"].lower()


def test_l7_upload_wrong_mime_returns_400(client):
    admin_tok = _login_admin(client)
    # extension matches but content_type disagrees.
    r = _upload(client, admin_tok, kind="pdf", filename="x.pdf",
                content=b"junk", content_type="video/mp4")
    assert r.status_code == 400
    assert "content-type" in r.get_json()["error"].lower()


def test_l7_upload_student_role_refused(client):
    admin_tok = _login_admin(client)
    client.post("/api/auth/register", json={
        "name": "S", "email": "s@t.local", "password": "password12", "role": "student",
    })
    stu_tok = _login(client, email="s@t.local", password="password12")
    r = _upload(client, stu_tok, kind="pdf", filename="x.pdf",
                content=b"%PDF-1.4", content_type="application/pdf")
    assert r.status_code == 403
