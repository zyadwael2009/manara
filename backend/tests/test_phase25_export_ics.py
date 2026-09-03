"""Phase 25 tests — admin CSV export + ICS calendar feed."""
from __future__ import annotations

import sys
from datetime import date as _date

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
        "utils.pdf",
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
        "routes.today", "routes.announcements", "routes.admin_import",
        "routes.notifications", "routes.messages", "routes.comments",
        "routes.homework", "routes.insight", "routes.report_cards",
        "routes.streak", "routes.search", "routes.question_bank",
        "routes.admin_export", "routes.calendar_feed",
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
        yield c


def _h(tok):
    return {"X-Session-Token": tok}


def _login(client, *, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.data
    return r.get_json()["sessionToken"]


def _login_admin(client):
    return _login(client, email="admin@t.local", password="adminpass1")


def _register(client, email, role="student", name="U"):
    return client.post("/api/auth/register", json={
        "name": name, "email": email, "password": "password12", "role": role,
    })


def _scaffold(client, admin_tok):
    h = _h(admin_tok)
    r = client.post("/api/sections", json={"name": "High"}, headers=h)
    high = r.get_json()["id"]
    r = client.post("/api/grades",
                    json={"name": "Grade 9", "sectionId": high, "orderIndex": 9},
                    headers=h)
    g9 = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "9-A", "gradeId": g9}, headers=h)
    c9a = r.get_json()["id"]
    r = client.post("/api/courses",
                    json={"title": "English 9", "gradeId": g9, "category": "english"},
                    headers=h)
    eng = r.get_json()
    r = client.post(f"/api/courses/{eng['id']}/modules",
                    json={"title": "M1"}, headers=h)
    module = r.get_json()
    client.post(f"/api/modules/{module['id']}/lessons",
                json={"title": "L", "type": "text", "contentText": "x"},
                headers=h)
    client.post(f"/api/courses/{eng['id']}/publish", headers=h)
    _register(client, "amira@t.local", role="student", name="Amira")
    amira_id = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/users/{amira_id}/class", json={"classId": c9a}, headers=h)
    return {
        "class_a": c9a, "amira_id": amira_id, "course": eng, "module": module,
    }


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
def test_users_csv_admin_only(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    r = client.get("/api/admin/export/users.csv", headers=_h(admin))
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("text/csv")
    body = r.data.decode()
    assert body.startswith("id,name,email,")
    assert "amira@t.local" in body


def test_users_csv_non_admin_forbidden(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    r = client.get("/api/admin/export/users.csv", headers=_h(stu))
    assert r.status_code in (401, 403)


def test_enrollments_csv_returns_rows(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    r = client.get("/api/admin/export/enrollments.csv", headers=_h(admin))
    assert r.status_code == 200
    lines = r.data.decode().strip().splitlines()
    assert lines[0].startswith("enrollmentId,studentId,")
    # At least one enrollment row (Amira auto-enrolled into English 9).
    assert len(lines) >= 2


def test_attendance_csv_respects_date_window(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    # Mark a couple of dates. Non-admin non-homeroom can't; admin can backdate.
    client.put(f"/api/classes/{s['class_a']}/attendance", json={
        "date": _date.today().isoformat(),
        "marks": [{"studentId": s["amira_id"], "status": "present"}],
    }, headers=_h(admin))
    # Full export.
    r = client.get("/api/admin/export/attendance.csv", headers=_h(admin))
    body = r.data.decode().strip().splitlines()
    assert body[0].startswith("id,date,")
    assert len(body) >= 2
    # Windowed to a range that excludes today.
    r = client.get(
        "/api/admin/export/attendance.csv?from=2001-01-01&to=2001-01-02",
        headers=_h(admin),
    )
    body = r.data.decode().strip().splitlines()
    assert len(body) == 1  # header only


def test_export_kinds_directory(client):
    admin = _login_admin(client)
    r = client.get("/api/admin/export/kinds", headers=_h(admin))
    ids = [k["id"] for k in r.get_json()["kinds"]]
    assert set(ids) == {"users", "enrollments", "grades", "attendance"}


# ---------------------------------------------------------------------------
# ICS feed
# ---------------------------------------------------------------------------
def test_token_lifecycle_and_feed_delivery(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")

    # First read creates a token.
    r = client.get("/api/calendar/mine/token", headers=_h(stu))
    assert r.status_code == 200
    t1 = r.get_json()["token"]
    assert len(t1) >= 20

    # Feed at that token returns a valid VCALENDAR.
    r = client.get(f"/api/calendar/{t1}.ics")
    assert r.status_code == 200
    body = r.data.decode()
    assert body.startswith("BEGIN:VCALENDAR")
    assert "END:VCALENDAR" in body
    assert "PRODID" in body
    # No auth header sent — the token IS the auth.

    # Rotate → old token dies.
    r2 = client.post("/api/calendar/mine/token", headers=_h(stu))
    t2 = r2.get_json()["token"]
    assert t2 != t1
    r = client.get(f"/api/calendar/{t1}.ics")
    assert r.status_code == 404

    # New token works.
    r = client.get(f"/api/calendar/{t2}.ics")
    assert r.status_code == 200

    # Revoke → 404 on any subsequent GET.
    r3 = client.delete("/api/calendar/mine/token", headers=_h(stu))
    assert r3.status_code == 204
    r = client.get(f"/api/calendar/{t2}.ics")
    assert r.status_code == 404


def test_student_ics_contains_period_events(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    # Add one Mon 09:00-09:45 period for English 9.
    client.put(
        f"/api/classes/{s['class_a']}/timetable/periods",
        json={"periods": [
            {"courseId": s["course"]["id"], "dayOfWeek": 0,
             "startTime": "09:00", "endTime": "09:45", "room": "9-A"},
        ]},
        headers=_h(admin),
    )
    stu = _login(client, email="amira@t.local", password="password12")
    token = client.get("/api/calendar/mine/token",
                       headers=_h(stu)).get_json()["token"]
    body = client.get(f"/api/calendar/{token}.ics").data.decode()
    # One weekly-recurring VEVENT for the period, summary contains course
    # + class name.
    assert "SUMMARY:English 9 · 9-A" in body
    assert "RRULE:FREQ=WEEKLY" in body


def test_ics_ignores_inactive_users(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    token = client.get("/api/calendar/mine/token",
                       headers=_h(stu)).get_json()["token"]
    # Withdraw Amira — feed should stop.
    client.post(f"/api/users/{s['amira_id']}/withdraw",
                json={"reason": "test"}, headers=_h(admin))
    r = client.get(f"/api/calendar/{token}.ics")
    assert r.status_code == 404
