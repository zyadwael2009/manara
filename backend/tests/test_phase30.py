"""Phase 30 tests — fee notifications + KPI + summary + cohort CSV +
wider pagination.

* Fee create → student + parent get a bell notification.
* Fee payment → student + parent get a receipt notification.
* /api/fees/summary returns outstanding + overdue counts for a student
  and non-students see the empty-shape response.
* /api/dashboards/cohort-comparison.csv returns text/csv with the right
  header row.
* /api/users?role=student&page=1 returns the paged envelope.
* /api/assignments/my?page=1 returns the paged envelope.
* /api/courses/<cid>/question-bank?page=1 returns the paged envelope.
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
        "utils.push", "utils.pdf", "utils.pagination",
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
        "routes.question_bank",
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


def _link_parent(client, admin_tok, student_id):
    """Create + link a parent to the given student. Returns parent_id + token."""
    r = client.post("/api/users", json={
        "name": "Parent",
        "email": "parent@t.local",
        "password": "password12",
        "role": "parent",
    }, headers=_h(admin_tok))
    assert r.status_code == 201, r.data
    parent_id = r.get_json()["id"]
    r = client.post(f"/api/users/{student_id}/parents", json={
        "parentId": parent_id, "relationship": "guardian",
    }, headers=_h(admin_tok))
    assert r.status_code in (200, 201), r.data
    parent_tok = _login(client, "parent@t.local", "password12")
    return parent_id, parent_tok


# ============================================================================
# Fee-event notifications
# ============================================================================
def test_fee_create_notifies_student_and_parent(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    _, parent_tok = _link_parent(client, admin_tok, s["amira_id"])
    r = client.post(f"/api/students/{s['amira_id']}/fees", json={
        "label": "Term 1", "amount": "500.00",
    }, headers=_h(admin_tok))
    assert r.status_code == 201
    # Student sees it.
    stu_tok = _login(client, "amira@t.local", "password12")
    r = client.get("/api/notifications/mine", headers=_h(stu_tok))
    kinds = [n["kind"] for n in r.get_json()["items"]]
    assert "fee_created" in kinds
    # Parent sees it too.
    r = client.get("/api/notifications/mine", headers=_h(parent_tok))
    kinds = [n["kind"] for n in r.get_json()["items"]]
    assert "fee_created" in kinds


def test_fee_payment_notifies_student_and_parent(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    _, parent_tok = _link_parent(client, admin_tok, s["amira_id"])
    r = client.post(f"/api/students/{s['amira_id']}/fees",
                    json={"label": "T", "amount": "100.00"},
                    headers=_h(admin_tok))
    fid = r.get_json()["id"]
    r = client.post(f"/api/fees/{fid}/payments",
                    json={"amount": "40.00"}, headers=_h(admin_tok))
    assert r.status_code == 201
    stu_tok = _login(client, "amira@t.local", "password12")
    r = client.get("/api/notifications/mine", headers=_h(stu_tok))
    kinds = [n["kind"] for n in r.get_json()["items"]]
    assert "fee_payment" in kinds
    r = client.get("/api/notifications/mine", headers=_h(parent_tok))
    kinds = [n["kind"] for n in r.get_json()["items"]]
    assert "fee_payment" in kinds


# ============================================================================
# Fee summary + admin KPI
# ============================================================================
def test_fees_summary_for_student(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    stu_tok = _login(client, "amira@t.local", "password12")
    r = client.get("/api/fees/summary", headers=_h(stu_tok))
    assert r.status_code == 200
    assert r.get_json()["outstanding"] == 0.0
    # Add a fee, summary updates.
    client.post(f"/api/students/{s['amira_id']}/fees",
                json={"label": "T", "amount": "75.50"},
                headers=_h(admin_tok))
    r = client.get("/api/fees/summary", headers=_h(stu_tok))
    body = r.get_json()
    assert body["outstanding"] == 75.5
    assert body["overdueCount"] == 0


def test_fees_summary_non_student_returns_empty_shape(client):
    admin_tok = _login_admin(client)
    r = client.get("/api/fees/summary", headers=_h(admin_tok))
    assert r.status_code == 200
    assert r.get_json() == {
        "outstanding": 0.0, "overdueCount": 0, "currency": "USD",
    }


def test_admin_topline_includes_fee_kpis(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    client.post(f"/api/students/{s['amira_id']}/fees",
                json={"label": "T", "amount": "100.00"},
                headers=_h(admin_tok))
    r = client.get("/api/dashboard/admin", headers=_h(admin_tok))
    assert r.status_code == 200
    topline = r.get_json()["topline"]
    assert topline["feeOutstandingTotal"] == 100.0
    assert topline["studentsWithOverdueFees"] == 0


# ============================================================================
# Cohort CSV export
# ============================================================================
def test_cohort_csv_shape(client):
    admin_tok = _login_admin(client)
    _place_student(client, admin_tok)
    h = _h(admin_tok)
    yr = client.post("/api/school-years",
                     json={"name": "Y", "isCurrent": True}, headers=h)
    year_id = yr.get_json()["id"]
    a = client.post(f"/api/school-years/{year_id}/terms",
                    json={"name": "Q1", "orderIndex": 0}, headers=h)
    b = client.post(f"/api/school-years/{year_id}/terms",
                    json={"name": "Q2", "orderIndex": 1}, headers=h)
    a_id, b_id = a.get_json()["id"], b.get_json()["id"]
    r = client.get(
        f"/api/dashboards/cohort-comparison.csv?termAId={a_id}&termBId={b_id}",
        headers=h,
    )
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    body = r.data.decode()
    header = body.splitlines()[0]
    assert "classId" in header
    assert "Q1_avgPercent" in header
    assert "Q2_avgPercent" in header
    # Trailing OVERALL row.
    last = body.strip().splitlines()[-1]
    assert "OVERALL" in last


# ============================================================================
# Wider pagination sweep
# ============================================================================
def test_users_students_pagination_envelope(client):
    admin_tok = _login_admin(client)
    _place_student(client, admin_tok)
    r = client.get("/api/users?role=student&search=a&page=1&pageSize=5",
                   headers=_h(admin_tok))
    assert r.status_code == 200
    body = r.get_json()
    # New shape when `page`/`pageSize` supplied.
    assert isinstance(body, dict)
    assert set(body.keys()) >= {"items", "page", "pageSize", "hasMore"}


def test_users_students_bare_array_by_default(client):
    admin_tok = _login_admin(client)
    _place_student(client, admin_tok)
    r = client.get("/api/users?role=student&search=a", headers=_h(admin_tok))
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_assignments_my_pagination_envelope(client):
    admin_tok = _login_admin(client)
    _place_student(client, admin_tok)
    stu_tok = _login(client, "amira@t.local", "password12")
    r = client.get("/api/assignments/my?page=1&pageSize=5",
                   headers=_h(stu_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body, dict)
    assert body["pageSize"] == 5
    assert body["hasMore"] is False


def test_question_bank_pagination_envelope(client):
    admin_tok = _login_admin(client)
    _place_student(client, admin_tok)
    h = _h(admin_tok)
    # Create a course to have a question-bank scope.
    grade = client.post("/api/grades",
                        json={"name": "G2", "sectionId":
                            client.post("/api/sections", json={"name": "S2"},
                                        headers=h).get_json()["id"],
                            "orderIndex": 2},
                        headers=h).get_json()["id"]
    course = client.post("/api/courses",
                         json={"title": "C", "gradeId": grade,
                               "category": "general"},
                         headers=h).get_json()
    r = client.get(
        f"/api/courses/{course['id']}/question-bank?page=1&pageSize=10",
        headers=h,
    )
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body, dict)
    assert set(body.keys()) >= {"items", "page", "pageSize", "hasMore"}
