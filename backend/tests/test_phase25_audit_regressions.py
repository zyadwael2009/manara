"""Phase 25 hard-audit regressions — one test per fixed finding.

Guards against silent re-introduction of the CRITICAL + top HIGH bugs
the three-agent audit surfaced.
"""
from __future__ import annotations

import io
import sys
from datetime import date as _date, timedelta

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
        "utils.pdf", "utils.rate_limit",
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
    from utils.rate_limit import _reset_all
    _reset_all()

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
    return {"grade": g9, "class_a": c9a, "amira_id": amira_id, "course": eng,
            "module": module}


# ---------------------------------------------------------------------------
# C-1 · CSV import refuses role=admin
# ---------------------------------------------------------------------------
def test_csv_import_refuses_role_admin(client):
    admin = _login_admin(client)
    csv_text = (
        "email,name,role,gradeName,className\n"
        "sneaky@t.local,Sneaky,admin,,\n"
    )
    data = {"file": (io.BytesIO(csv_text.encode("utf-8")), "roster.csv")}
    r = client.post("/api/admin/users/import",
                    data=data, content_type="multipart/form-data",
                    headers=_h(admin))
    body = r.get_json()
    assert body["created"] == []
    assert len(body["errors"]) == 1
    assert "role must be one of" in body["errors"][0]["error"]
    from models import User
    assert User.query.filter_by(email="sneaky@t.local").first() is None


# ---------------------------------------------------------------------------
# H-1 · DMs — admin cannot spawn arbitrary threads
# ---------------------------------------------------------------------------
def test_admin_cannot_dm_student(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    r = client.post("/api/messages/threads", json={
        "recipientId": s["amira_id"],
        "subject": "test", "body": "hello",
    }, headers=_h(admin))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# H-2 · Search never surfaces unpublished quiz/assignment titles to students
# ---------------------------------------------------------------------------
def test_search_hides_unpublished_quiz_from_students(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    # Author two quizzes; publish one, leave the other draft.
    r = client.post(f"/api/modules/{s['module']['id']}/quizzes",
                    json={"title": "Midterm review"}, headers=_h(admin))
    published_id = r.get_json()["id"]
    # Publish requires at least one question.
    r = client.post(f"/api/quizzes/{published_id}/questions",
                    json={"type": "mc_single", "prompt": "?", "points": 1},
                    headers=_h(admin))
    qq = r.get_json()
    client.post(f"/api/quiz-questions/{qq['id']}/options",
                json={"text": "A", "isCorrect": True}, headers=_h(admin))
    r = client.post(f"/api/quizzes/{published_id}/publish", headers=_h(admin))
    assert r.status_code == 200, r.data
    client.post(f"/api/modules/{s['module']['id']}/quizzes",
                json={"title": "Midterm final answers"}, headers=_h(admin))

    stu = _login(client, email="amira@t.local", password="password12")
    # Sanity — Amira is enrolled in English 9, so the course itself
    # should be reachable via search.
    body = client.get("/api/search?q=English", headers=_h(stu)).get_json()
    kinds = {r["kind"] for r in body["results"]}
    assert "course" in kinds, f"student can't see enrolled course in search: {body}"
    body = client.get("/api/search?q=Midterm", headers=_h(stu)).get_json()
    titles = {r["title"] for r in body["results"]}
    assert "Midterm review" in titles
    assert "Midterm final answers" not in titles

    # Admin still sees drafts.
    body = client.get("/api/search?q=Midterm", headers=_h(admin)).get_json()
    titles = {r["title"] for r in body["results"]}
    assert {"Midterm review", "Midterm final answers"} <= titles


# ---------------------------------------------------------------------------
# H-3 / H-10 · Withdrawn child stays accessible to their linked parent
# ---------------------------------------------------------------------------
def test_parent_can_read_withdrawn_child_summary(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    h = _h(admin)
    # Admin-create parent + link.
    r = client.post("/api/users", json={
        "name": "Fatima", "email": "fatima@t.local",
        "password": "password12", "role": "parent",
    }, headers=h)
    par_id = r.get_json()["id"]
    client.post(f"/api/users/{s['amira_id']}/parents",
                json={"parentId": par_id}, headers=h)
    # Withdraw Amira.
    client.post(f"/api/users/{s['amira_id']}/withdraw",
                json={"reason": "moved"}, headers=h)
    par = _login(client, email="fatima@t.local", password="password12")
    # Historical drill-down should still work.
    r = client.get(f"/api/parents/mine/children/{s['amira_id']}/summary",
                   headers=_h(par))
    assert r.status_code == 200
    # And PDFs.
    r = client.get(f"/api/students/{s['amira_id']}/report-card.pdf",
                   headers=_h(par))
    assert r.status_code == 200
    assert r.data.startswith(b"%PDF-")
    # list_my_children badges the withdrawn state.
    rows = client.get("/api/parents/mine/children", headers=_h(par)).get_json()
    amira_row = [r for r in rows if r["studentId"] == s["amira_id"]][0]
    assert amira_row["isActive"] is False
    assert amira_row["withdrawnAt"] is not None


# ---------------------------------------------------------------------------
# H-5 · Attendance dedup includes date — day N+1 fires
# ---------------------------------------------------------------------------
def test_attendance_notification_fires_on_consecutive_days(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    from models import AttendanceMark, Notification, db
    today = _date.today()
    yesterday = today - timedelta(days=1)

    # Two absent marks on two different dates.
    for d in (yesterday, today):
        client.put(f"/api/classes/{s['class_a']}/attendance", json={
            "date": d.isoformat(),
            "marks": [{"studentId": s["amira_id"], "status": "absent"}],
        }, headers=_h(admin))

    # The student should have TWO attendance_marked notifications, not one.
    n = Notification.query.filter_by(
        user_id=s["amira_id"], kind="attendance_marked").count()
    assert n == 2


# ---------------------------------------------------------------------------
# H-11 · Search wildcard is escaped
# ---------------------------------------------------------------------------
def test_search_wildcard_is_escaped(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    # `%` no longer means "match everything".
    r = client.get("/api/search?q=%25", headers=_h(admin))  # `%` URL-encoded
    body = r.get_json()
    # The literal string '%' isn't in any of the seeded titles.
    assert body["results"] == []


# ---------------------------------------------------------------------------
# H-10 (H-10 rate limit) · Login endpoint rate-limits per IP burst
# ---------------------------------------------------------------------------
def test_login_rate_limit_kicks_in_after_burst(client):
    # The gate is skipped under TESTING (see routes/auth.py comment) so
    # every OTHER test in the suite doesn't self-lock. Flip TESTING off
    # for the duration of this test to prove the production path.
    from utils.rate_limit import _reset_all
    _reset_all()
    client.application.config["TESTING"] = False
    try:
        # 20 bad attempts in the window is the cap; 21st gets 429.
        for _ in range(20):
            client.post("/api/auth/login",
                        json={"email": "nope@t.local", "password": "x"})
        r = client.post("/api/auth/login",
                        json={"email": "nope@t.local", "password": "x"})
        assert r.status_code == 429
        assert "Retry-After" in r.headers
    finally:
        client.application.config["TESTING"] = True
        _reset_all()


# ---------------------------------------------------------------------------
# H-6 · question_bank adopt no longer silently returns adopted:0 on a
#      quiz whose module has a valid course
# ---------------------------------------------------------------------------
def test_adopt_bank_items_actually_copies(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    # Bank item.
    r = client.post(f"/api/courses/{s['course']['id']}/question-bank", json={
        "type": "mc_single", "prompt": "Q?",
        "options": [
            {"text": "A", "isCorrect": True},
            {"text": "B", "isCorrect": False},
        ],
    }, headers=_h(admin))
    item_id = r.get_json()["id"]
    # Empty quiz.
    r = client.post(f"/api/modules/{s['module']['id']}/quizzes",
                    json={"title": "Reuse"}, headers=_h(admin))
    quiz_id = r.get_json()["id"]
    r = client.post(f"/api/quizzes/{quiz_id}/adopt-bank-items",
                    json={"itemIds": [item_id]}, headers=_h(admin))
    body = r.get_json()
    assert body["adopted"] == 1


# ---------------------------------------------------------------------------
# H-8 · ICS emits floating times (no `Z` suffix) for period events
# ---------------------------------------------------------------------------
def test_ics_period_events_use_floating_times(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
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
    # DTSTART for the period is a floating time (no Z).
    for line in body.splitlines():
        if line.startswith("DTSTART:") and "T09" in line:
            assert not line.endswith("Z"), line
            break
    else:
        pytest.fail("Never saw a period DTSTART with T09")
    # And the misleading X-WR-TIMEZONE:UTC is gone.
    assert "X-WR-TIMEZONE:UTC" not in body


# ---------------------------------------------------------------------------
# Medium · CSV cross-grade move soft-drops old enrollments
# ---------------------------------------------------------------------------
def test_csv_cross_grade_move_soft_drops_old_enrollments(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    h = _h(admin)
    # Set up a second grade with its own class + one mandatory course.
    r = client.post("/api/grades",
                    json={"name": "Grade 10", "sectionId": None, "orderIndex": 10},
                    headers=h)
    # Grade needs a section — grab the first one.
    from models import Grade, Section, db
    high = Section.query.first()
    if r.status_code != 201:
        r = client.post("/api/grades",
                        json={"name": "Grade 10", "sectionId": high.id, "orderIndex": 10},
                        headers=h)
    g10 = r.get_json()["id"]
    r = client.post("/api/classes",
                    json={"name": "10-A", "gradeId": g10}, headers=h)
    c10a = r.get_json()["id"]
    r = client.post("/api/courses",
                    json={"title": "Algebra 1", "gradeId": g10, "category": "math"},
                    headers=h)
    alg = r.get_json()
    r = client.post(f"/api/courses/{alg['id']}/modules",
                    json={"title": "M1"}, headers=h)
    client.post(f"/api/modules/{r.get_json()['id']}/lessons",
                json={"title": "L", "type": "text", "contentText": "x"},
                headers=h)
    client.post(f"/api/courses/{alg['id']}/publish", headers=h)

    # Amira starts in Grade 9. Import moves her to Grade 10.
    from models import Enrollment
    before_active = Enrollment.query.filter_by(
        student_id=s["amira_id"], status="active").count()
    assert before_active >= 1

    csv_text = (
        "email,name,role,gradeName,className\n"
        "amira@t.local,Amira,student,Grade 10,10-A\n"
    )
    data = {"file": (io.BytesIO(csv_text.encode("utf-8")), "roster.csv")}
    client.post("/api/admin/users/import",
                data=data, content_type="multipart/form-data",
                headers=h)
    # Grade-9 mandatory enrollment must be dropped, not silently coexisting.
    from models import Course
    g9_courses = {c.id for c in Course.query.filter_by(grade_id=s["grade"]).all()}
    still_active_in_g9 = (
        Enrollment.query.filter_by(student_id=s["amira_id"], status="active")
        .filter(Enrollment.course_id.in_(g9_courses)).count()
    )
    assert still_active_in_g9 == 0
