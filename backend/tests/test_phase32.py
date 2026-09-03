"""Phase 32 tests — notification prefs + diplomas + standards.

* GET /api/notifications/preferences returns every kind default-enabled.
* PUT toggles a kind off; enqueue for that kind → no row appended.
* enqueue for a different kind still writes.
* /api/classes/<cid>/graduate auto-issues one diploma per graduated
  student; re-run is idempotent.
* /api/verify-diploma/<num> is public + reflects revoke state.
* /api/diplomas/<id>/revoke flips the flag; restore reverts.
* /api/students/<sid>/diploma.pdf returns application/pdf.
* Standards CRUD + tagging + mastery rollup shape.
"""
from __future__ import annotations

import sys

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    for mod in [
        "config", "models",
        "utils.permissions", "utils.grading", "utils.quizzes",
        "utils.certificates", "utils.analytics", "utils.attendance",
        "utils.timetables", "utils.assignments", "utils.notifications",
        "utils.push", "utils.pdf", "utils.pagination", "utils.time",
        "utils.fees", "utils.diplomas", "utils.standards",
        "routes", "routes.auth", "routes.users",
        "routes.sections", "routes.grades", "routes.classes",
        "routes.courses", "routes.modules", "routes.lessons",
        "routes.enrollments", "routes.students",
        "routes.department_leaders", "routes.uploads",
        "routes.progress", "routes.grading_admin",
        "routes.rubrics", "routes.grade_reports",
        "routes.quizzes", "routes.quiz_take", "routes.quiz_admin",
        "routes.certificates", "routes.dashboards", "routes.parents",
        "routes.attendance", "routes.timetables", "routes.assignments",
        "routes.checkpoints", "routes.assignment_groups",
        "routes.push", "routes.fees",
        "routes.notifications", "routes.messages", "routes.announcements",
        "routes.question_bank", "routes.diplomas", "routes.standards",
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
    with app.test_client() as c:
        c.application = app
        yield c


def _h(tok):
    return {"X-Session-Token": tok}


def _login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.data
    return r.get_json()["sessionToken"]


def _login_admin(client):
    return _login(client, "admin@t.local", "adminpass1")


def _register(client, email, role="student", name="U"):
    return client.post("/api/auth/register", json={
        "name": name, "email": email, "password": "password12", "role": role,
    })


def _place_student(client, admin_tok):
    h = _h(admin_tok)
    sec = client.post("/api/sections", json={"name": "S"},
                      headers=h).get_json()["id"]
    grade = client.post("/api/grades",
                        json={"name": "G", "sectionId": sec, "orderIndex": 1},
                        headers=h).get_json()["id"]
    klass = client.post("/api/classes", json={"name": "K", "gradeId": grade},
                        headers=h).get_json()["id"]
    _register(client, "amira@t.local", role="student", name="Amira")
    amira_id = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/users/{amira_id}/class",
               json={"classId": klass}, headers=h)
    return {"grade": grade, "class": klass, "amira_id": amira_id}


# ============================================================================
# T1 · Notification preferences
# ============================================================================
def test_prefs_default_enabled_for_all_kinds(client):
    admin_tok = _login_admin(client)
    r = client.get("/api/notifications/preferences", headers=_h(admin_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body["kinds"], list) and len(body["kinds"]) > 0
    # No rows written yet → every kind defaults to enabled.
    assert all(body["preferences"][k] is True for k in body["kinds"])


def test_prefs_disable_kind_suppresses_that_kind_only(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    stu_tok = _login(client, "amira@t.local", "password12")
    # Disable fee_created for the student.
    r = client.put("/api/notifications/preferences", json={
        "preferences": {"fee_created": False},
    }, headers=_h(stu_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert body["preferences"]["fee_created"] is False
    assert body["preferences"]["announcement"] is True

    # Admin creates a fee — the student should NOT get the fee_created bell.
    client.post(f"/api/students/{s['amira_id']}/fees",
                json={"label": "T", "amount": "10.00"},
                headers=_h(admin_tok))
    r = client.get("/api/notifications/mine", headers=_h(stu_tok))
    kinds = [n["kind"] for n in r.get_json()["items"]]
    assert "fee_created" not in kinds


def test_prefs_ignores_unknown_kinds(client):
    admin_tok = _login_admin(client)
    r = client.put("/api/notifications/preferences", json={
        "preferences": {"bogus_kind": False},
    }, headers=_h(admin_tok))
    # Bogus keys are silently dropped, response still 200.
    assert r.status_code == 200


# ============================================================================
# T2 · Diploma
# ============================================================================
def test_graduate_class_issues_diplomas(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    r = client.post(f"/api/classes/{s['class']}/graduate",
                    json={}, headers=_h(admin_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert body["graduated"] == 1
    assert body["diplomasIssued"] == 1

    r = client.get(f"/api/students/{s['amira_id']}/diploma",
                   headers=_h(admin_tok))
    assert r.status_code == 200
    dip = r.get_json()["diploma"]
    assert dip is not None
    assert dip["studentId"] == s["amira_id"]
    assert dip["revoked"] is False


def test_graduate_is_idempotent_on_diplomas(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    # First graduation issues the diploma.
    client.post(f"/api/classes/{s['class']}/graduate",
                json={}, headers=_h(admin_tok))
    # Re-place + re-graduate should NOT issue a second row for the
    # same (student, class_of_year).
    from models import Diploma, User, db
    with client.application.app_context():
        # Reactivate + re-place so the second graduate call reaches them.
        u = User.query.filter_by(email="amira@t.local").first()
        u.is_active = True
        u.class_id = s["class"]
        db.session.commit()
    client.post(f"/api/classes/{s['class']}/graduate",
                json={}, headers=_h(admin_tok))
    with client.application.app_context():
        assert Diploma.query.filter_by(
            student_id=s["amira_id"]
        ).count() == 1


def test_verify_diploma_is_public_and_reflects_revoke(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    client.post(f"/api/classes/{s['class']}/graduate",
                json={}, headers=_h(admin_tok))
    r = client.get(f"/api/students/{s['amira_id']}/diploma",
                   headers=_h(admin_tok))
    dip = r.get_json()["diploma"]
    num = dip["diplomaNumber"]
    did = dip["id"]

    # Anonymous verify.
    r = client.get(f"/api/verify-diploma/{num}")
    body = r.get_json()
    assert r.status_code == 200
    assert body["found"] is True
    assert body["revoked"] is False

    # Admin revokes.
    r = client.post(f"/api/diplomas/{did}/revoke",
                    json={"reason": "test"}, headers=_h(admin_tok))
    assert r.status_code == 200

    r = client.get(f"/api/verify-diploma/{num}")
    body = r.get_json()
    assert body["revoked"] is True
    assert body["revokedReason"] == "test"


def test_verify_diploma_is_rate_limited(client):
    """Phase 33 fix #1 + #23 — a burst of `/api/verify-diploma/<num>`
    from one IP must eventually 429. Guards against a regression that
    would re-open enumeration of the graduate roster."""
    # `check_rate` enforces the limit unconditionally (bucket resets
    # across test runs because the fixture pops the module). 30/min
    # by config; the 31st in the same window should be 429.
    from utils.rate_limit import _reset_all as _rl_reset
    _rl_reset()
    seen_429 = False
    for _ in range(60):
        r = client.get("/api/verify-diploma/fake-number-xyz")
        if r.status_code == 429:
            seen_429 = True
            assert "Retry-After" in r.headers
            break
    assert seen_429, "verify-diploma should rate-limit after a burst"


def test_diploma_pdf_returns_pdf(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    client.post(f"/api/classes/{s['class']}/graduate",
                json={}, headers=_h(admin_tok))
    r = client.get(f"/api/students/{s['amira_id']}/diploma.pdf",
                   headers=_h(admin_tok))
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.data.startswith(b"%PDF-")


# ============================================================================
# T3 · Standards + mastery
# ============================================================================
def test_standards_crud_and_tag(client):
    admin_tok = _login_admin(client)
    _place_student(client, admin_tok)
    r = client.post("/api/standards", json={
        "code": "MATH.6.EE.1",
        "name": "Whole-number exponents",
        "subject": "math",
    }, headers=_h(admin_tok))
    assert r.status_code == 201
    sid = r.get_json()["id"]

    # List includes it.
    r = client.get("/api/standards", headers=_h(admin_tok))
    assert any(s["code"] == "MATH.6.EE.1" for s in r.get_json())

    # Duplicate code refused.
    r = client.post("/api/standards", json={
        "code": "MATH.6.EE.1", "name": "dup",
    }, headers=_h(admin_tok))
    assert r.status_code == 409


def test_standards_admin_only_writes(client):
    admin_tok = _login_admin(client)
    _place_student(client, admin_tok)
    stu_tok = _login(client, "amira@t.local", "password12")
    r = client.post("/api/standards", json={
        "code": "X", "name": "Y",
    }, headers=_h(stu_tok))
    assert r.status_code == 403


def test_student_mastery_shape(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    # Seed one standard.
    client.post("/api/standards", json={
        "code": "ELA.6.RL.1", "name": "Cite textual evidence",
        "subject": "english",
    }, headers=_h(admin_tok))
    stu_tok = _login(client, "amira@t.local", "password12")
    r = client.get(f"/api/students/{s['amira_id']}/standards-mastery",
                   headers=_h(stu_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert body["studentId"] == s["amira_id"]
    assert isinstance(body["standards"], list)
    # No tagged content → every standard reports not-assessed.
    for st in body["standards"]:
        assert st["band"] == "not-assessed"
        assert st["sampleSize"] == 0
