"""Phase 27 tests — video checkpoints + group assignments + Meet URL.

Video checkpoints:
  * Owner creates a checkpoint; student sees it WITHOUT correctOptionId.
  * Owner sees correctOptionId.
  * Non-owner student cannot create.
  * Options with duplicate id → 400.

Group assignments:
  * Admin creates is_group assignment with maxGroupSize=2.
  * Student A creates group → auto-member.
  * Student B joins → 2 members.
  * Student C hits size cap → 409.
  * Student A submits → both A and B get shared submission rows.
  * Teacher grades A's submission → B's grade appears too, both
    enrollments have rolled-up entries.
  * Student A tries to create a 2nd group → 409.

Meet URL:
  * Bulk-PUT periods accepts meetingUrl and rejects javascript: URIs.
  * PATCH /meeting-url as course teacher (not admin) succeeds; a
    stranger teacher gets 403.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta as _td

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

    for mod in [
        "config", "models",
        "utils.permissions", "utils.grading", "utils.quizzes",
        "utils.certificates", "utils.analytics", "utils.attendance",
        "utils.timetables", "utils.assignments",
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


def _scaffold(client, admin_tok, *, extra_students: list[str] | None = None):
    """9-A with Rivera teacher and Amira placed. Optional extra students
    are all placed in 9-A so they auto-enroll into the same course."""
    h = _h(admin_tok)
    r = client.post("/api/sections", json={"name": "High"}, headers=h)
    section = r.get_json()["id"]
    r = client.post("/api/grades",
                    json={"name": "Grade 9", "sectionId": section, "orderIndex": 9},
                    headers=h)
    g9 = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "9-A", "gradeId": g9}, headers=h)
    c9a = r.get_json()["id"]
    r = client.post("/api/courses",
                    json={"title": "English 9", "gradeId": g9, "category": "english"},
                    headers=h)
    course = r.get_json()
    r = client.post(f"/api/courses/{course['id']}/modules",
                    json={"title": "M1"}, headers=h)
    module = r.get_json()
    r = client.post(f"/api/modules/{module['id']}/lessons",
                    json={"title": "Video L1", "type": "video",
                          "contentUrl": "https://x/y.mp4"},
                    headers=h)
    lesson = r.get_json()
    client.post(f"/api/courses/{course['id']}/publish", headers=h)

    _register(client, "rivera@t.local", role="instructor", name="Rivera")
    riv_id = client.post("/api/auth/login", json={
        "email": "rivera@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/classes/{c9a}/courses/{course['id']}/teacher",
               json={"teacherId": riv_id}, headers=h)

    _register(client, "amira@t.local", role="student", name="Amira")
    amira_id = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/users/{amira_id}/class", json={"classId": c9a}, headers=h)

    extra_ids: dict[str, str] = {}
    for email in extra_students or []:
        _register(client, email, role="student", name=email.split("@")[0])
        uid = client.post("/api/auth/login", json={
            "email": email, "password": "password12",
        }).get_json()["user"]["id"]
        client.put(f"/api/users/{uid}/class", json={"classId": c9a}, headers=h)
        extra_ids[email] = uid

    # Assignments rubric so grade fan-out has somewhere to land.
    r = client.post("/api/grade-categories",
                    json={"name": "Assignments", "slug": "assignments"}, headers=h)
    assn_cat = r.get_json()
    for mn, mx, letter, gpa in [(60, 100, "A", 4.0), (0, 59, "F", 0.0)]:
        client.post("/api/grading-scale", json={
            "minPercent": mn, "maxPercent": mx, "letter": letter, "gpaValue": gpa,
        }, headers=h)
    client.put(f"/api/courses/{course['id']}/rubric", json={
        "items": [{"gradeCategoryId": assn_cat["id"], "maxScore": 100, "orderIndex": 0}],
    }, headers=h)
    r = client.post("/api/school-years", json={"name": "Y", "isCurrent": True}, headers=h)
    year = r.get_json()["id"]
    r = client.post(f"/api/school-years/{year}/terms",
                    json={"name": "Q1", "orderIndex": 0}, headers=h)
    q1 = r.get_json()["id"]

    return {
        "class_a": c9a, "riv_id": riv_id, "amira_id": amira_id,
        "course": course, "module": module, "lesson": lesson,
        "assn_cat": assn_cat, "q1": q1, "extra_ids": extra_ids,
    }


# ============================================================================
# Video checkpoints
# ============================================================================
def test_owner_creates_checkpoint_student_reads_without_answer(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    lid = a["lesson"]["id"]
    r = client.post(f"/api/lessons/{lid}/checkpoints", json={
        "positionSeconds": 30,
        "prompt": "Who wrote it?",
        "options": [
            {"id": "opt-1", "text": "Newton"},
            {"id": "opt-2", "text": "Einstein"},
        ],
        "correctOptionId": "opt-1",
    }, headers=_h(admin_tok))
    assert r.status_code == 201, r.data
    cp = r.get_json()
    assert cp["correctOptionId"] == "opt-1"

    stu_tok = _login(client, email="amira@t.local", password="password12")
    r = client.get(f"/api/lessons/{lid}/checkpoints", headers=_h(stu_tok))
    assert r.status_code == 200
    rows = r.get_json()
    assert len(rows) == 1
    assert "correctOptionId" not in rows[0], "student should not see the answer"
    assert rows[0]["prompt"] == "Who wrote it?"
    assert len(rows[0]["options"]) == 2


def test_owner_sees_answer_on_list(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    lid = a["lesson"]["id"]
    client.post(f"/api/lessons/{lid}/checkpoints", json={
        "positionSeconds": 10, "prompt": "x",
        "options": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
        "correctOptionId": "b",
    }, headers=_h(admin_tok))
    r = client.get(f"/api/lessons/{lid}/checkpoints", headers=_h(admin_tok))
    assert r.status_code == 200
    assert r.get_json()[0]["correctOptionId"] == "b"


def test_student_cannot_create_checkpoint(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    stu_tok = _login(client, email="amira@t.local", password="password12")
    r = client.post(f"/api/lessons/{a['lesson']['id']}/checkpoints", json={
        "positionSeconds": 5, "prompt": "x",
        "options": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
        "correctOptionId": "a",
    }, headers=_h(stu_tok))
    assert r.status_code == 403


def test_checkpoint_duplicate_option_id_rejected(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    r = client.post(f"/api/lessons/{a['lesson']['id']}/checkpoints", json={
        "positionSeconds": 5, "prompt": "x",
        "options": [{"id": "same", "text": "A"}, {"id": "same", "text": "B"}],
        "correctOptionId": "same",
    }, headers=_h(admin_tok))
    assert r.status_code == 400


def test_checkpoint_only_on_video_lessons(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    # Add a text lesson to the same module.
    r = client.post(f"/api/modules/{a['module']['id']}/lessons",
                    json={"title": "Text L2", "type": "text", "contentText": "x"},
                    headers=_h(admin_tok))
    text_lid = r.get_json()["id"]
    r = client.post(f"/api/lessons/{text_lid}/checkpoints", json={
        "positionSeconds": 5, "prompt": "x",
        "options": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
        "correctOptionId": "a",
    }, headers=_h(admin_tok))
    assert r.status_code == 400


# ============================================================================
# Group assignments
# ============================================================================
def _create_group_assignment(client, admin_tok, module_id, *, max_size=2):
    r = client.post(f"/api/modules/{module_id}/assignments", json={
        "title": "Group Essay", "maxPoints": 100,
        "isGroup": True, "maxGroupSize": max_size,
    }, headers=_h(admin_tok))
    assert r.status_code == 201, r.data
    a = r.get_json()
    client.post(f"/api/assignments/{a['id']}/publish", headers=_h(admin_tok))
    return a


def test_group_create_join_and_size_cap(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok, extra_students=["bilal@t.local", "cyra@t.local"])
    assn = _create_group_assignment(client, admin_tok, a["module"]["id"], max_size=2)

    a_tok = _login(client, email="amira@t.local", password="password12")
    b_tok = _login(client, email="bilal@t.local", password="password12")
    c_tok = _login(client, email="cyra@t.local", password="password12")

    r = client.post(f"/api/assignments/{assn['id']}/groups",
                    json={"name": "Team Alpha"}, headers=_h(a_tok))
    assert r.status_code == 201, r.data
    gid = r.get_json()["id"]
    assert r.get_json()["memberCount"] == 1

    r = client.post(f"/api/assignment-groups/{gid}/join", headers=_h(b_tok))
    assert r.status_code == 200
    assert r.get_json()["memberCount"] == 2

    # Third student runs into the cap.
    r = client.post(f"/api/assignment-groups/{gid}/join", headers=_h(c_tok))
    assert r.status_code == 409


def test_group_submission_fans_out_to_all_members(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok, extra_students=["bilal@t.local"])
    assn = _create_group_assignment(client, admin_tok, a["module"]["id"], max_size=3)
    a_tok = _login(client, email="amira@t.local", password="password12")
    b_tok = _login(client, email="bilal@t.local", password="password12")

    r = client.post(f"/api/assignments/{assn['id']}/groups",
                    json={"name": "Duo"}, headers=_h(a_tok))
    gid = r.get_json()["id"]
    client.post(f"/api/assignment-groups/{gid}/join", headers=_h(b_tok))

    # A submits.
    r = client.post(f"/api/assignments/{assn['id']}/submissions",
                    json={"responseText": "shared essay"}, headers=_h(a_tok))
    assert r.status_code == 201, r.data

    # Every member should now have a submission with the same content.
    r = client.get(f"/api/assignments/{assn['id']}/submissions",
                   headers=_h(admin_tok))
    assert r.status_code == 200
    rows = r.get_json()
    assert len(rows) == 2
    assert {r["responseText"] for r in rows} == {"shared essay"}
    assert len({r["groupId"] for r in rows}) == 1


def test_group_grade_fans_out(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok, extra_students=["bilal@t.local"])
    assn = _create_group_assignment(client, admin_tok, a["module"]["id"], max_size=3)
    a_tok = _login(client, email="amira@t.local", password="password12")
    b_tok = _login(client, email="bilal@t.local", password="password12")

    r = client.post(f"/api/assignments/{assn['id']}/groups",
                    json={"name": "Duo"}, headers=_h(a_tok))
    gid = r.get_json()["id"]
    client.post(f"/api/assignment-groups/{gid}/join", headers=_h(b_tok))
    r = client.post(f"/api/assignments/{assn['id']}/submissions",
                    json={"responseText": "shared essay"}, headers=_h(a_tok))
    a_sub_id = r.get_json()["id"]

    # Teacher grades A's submission → B's grade should follow.
    riv_tok = _login(client, email="rivera@t.local", password="password12")
    r = client.put(f"/api/submissions/{a_sub_id}/grade",
                   json={"score": 85, "feedback": "Great teamwork!"},
                   headers=_h(riv_tok))
    assert r.status_code == 200

    r = client.get(f"/api/assignments/{assn['id']}/submissions",
                   headers=_h(admin_tok))
    rows = r.get_json()
    assert len(rows) == 2
    scores = {r["studentId"]: r["gradedScore"] for r in rows}
    assert scores[a["amira_id"]] == 85.0
    assert scores[a["extra_ids"]["bilal@t.local"]] == 85.0


def test_student_cannot_be_in_two_groups(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    assn = _create_group_assignment(client, admin_tok, a["module"]["id"])
    a_tok = _login(client, email="amira@t.local", password="password12")
    r = client.post(f"/api/assignments/{assn['id']}/groups",
                    json={"name": "G1"}, headers=_h(a_tok))
    assert r.status_code == 201
    r = client.post(f"/api/assignments/{assn['id']}/groups",
                    json={"name": "G2"}, headers=_h(a_tok))
    assert r.status_code == 409


def test_group_assignment_requires_group_before_submit(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    assn = _create_group_assignment(client, admin_tok, a["module"]["id"])
    a_tok = _login(client, email="amira@t.local", password="password12")
    r = client.post(f"/api/assignments/{assn['id']}/submissions",
                    json={"responseText": "solo"}, headers=_h(a_tok))
    assert r.status_code == 409


# ============================================================================
# Meeting URL
# ============================================================================
def test_bulk_put_periods_accepts_meeting_url(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    r = client.put(f"/api/classes/{a['class_a']}/timetable/periods", json={
        "periods": [{
            "courseId": a["course"]["id"],
            "dayOfWeek": 0,
            "startTime": "09:00",
            "endTime": "10:00",
            "meetingUrl": "https://meet.example.com/xyz",
        }],
    }, headers=_h(admin_tok))
    assert r.status_code == 200, r.data
    periods = r.get_json()["periods"]
    assert periods[0]["meetingUrl"] == "https://meet.example.com/xyz"


def test_bulk_put_rejects_javascript_url(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    r = client.put(f"/api/classes/{a['class_a']}/timetable/periods", json={
        "periods": [{
            "courseId": a["course"]["id"],
            "dayOfWeek": 0,
            "startTime": "09:00",
            "endTime": "10:00",
            "meetingUrl": "javascript:alert(1)",
        }],
    }, headers=_h(admin_tok))
    assert r.status_code == 400


def test_teacher_can_patch_own_period_meeting_url(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    # Seed one period.
    r = client.put(f"/api/classes/{a['class_a']}/timetable/periods", json={
        "periods": [{
            "courseId": a["course"]["id"],
            "dayOfWeek": 0,
            "startTime": "09:00",
            "endTime": "10:00",
        }],
    }, headers=_h(admin_tok))
    period_id = r.get_json()["periods"][0]["id"]

    riv_tok = _login(client, email="rivera@t.local", password="password12")
    r = client.put(
        f"/api/classes/{a['class_a']}/timetable/periods/{period_id}/meeting-url",
        json={"meetingUrl": "https://zoom.us/j/1234"},
        headers=_h(riv_tok),
    )
    assert r.status_code == 200, r.data
    assert r.get_json()["meetingUrl"] == "https://zoom.us/j/1234"


def test_stranger_teacher_cannot_patch_meeting_url(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    r = client.put(f"/api/classes/{a['class_a']}/timetable/periods", json={
        "periods": [{
            "courseId": a["course"]["id"],
            "dayOfWeek": 0,
            "startTime": "09:00",
            "endTime": "10:00",
        }],
    }, headers=_h(admin_tok))
    period_id = r.get_json()["periods"][0]["id"]

    _register(client, "stranger@t.local", role="instructor", name="Stranger")
    s_tok = _login(client, email="stranger@t.local", password="password12")
    r = client.put(
        f"/api/classes/{a['class_a']}/timetable/periods/{period_id}/meeting-url",
        json={"meetingUrl": "https://evil.example/xxx"},
        headers=_h(s_tok),
    )
    assert r.status_code == 403
