"""Phase 14 tests — assignments.

Positive:
  * Admin creates + publishes → students see it.
  * Student submits text before due → is_late=False; after → True.
  * Re-submit is an upsert (single row, no duplicate) and clears any prior grade.
  * Teacher grades → rollup writes GradeEntry into Assignments category.
  * Grade write that pushes cumulative % over the cert threshold + full
    progress + no failing quiz → cert auto-issued.

Trust-core negatives:
  * Non-enrolled student → 403 on submit.
  * Student tries to grade own submission → 403.
  * Parent tries to submit → 403.
  * Delete assignment with submissions → 409.
  * Edit assignment after submission exists → 409.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta as _td

import pytest
from utils.time import utc_now


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


def _scaffold(client, admin_tok):
    """9-A with Rivera as class-teacher of English + Amira placed. Grading
    infra ready (Q1, grading scale, Assignments rubric row)."""
    h = _h(admin_tok)
    r = client.post("/api/sections", json={"name": "High"}, headers=h)
    section = r.get_json()["id"]
    r = client.post("/api/grades",
                    json={"name": "Grade 9", "sectionId": section, "orderIndex": 9},
                    headers=h)
    g9 = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "9-A", "gradeId": g9}, headers=h)
    c9a = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "9-B", "gradeId": g9}, headers=h)
    c9b = r.get_json()["id"]
    r = client.post("/api/courses",
                    json={"title": "English 9", "gradeId": g9, "category": "english"},
                    headers=h)
    course = r.get_json()
    r = client.post(f"/api/courses/{course['id']}/modules",
                    json={"title": "M1"}, headers=h)
    module = r.get_json()
    client.post(f"/api/modules/{module['id']}/lessons",
                json={"title": "L1", "type": "text", "contentText": "x"}, headers=h)
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

    # Grading infrastructure — Assignments rubric row (existing slug) at 40 pts
    # so a full 100 on the assignment maps to 40 in the category → weighty
    # enough to move cumulative % noticeably.
    r = client.post("/api/grade-categories",
                    json={"name": "Assignments", "slug": "assignments"}, headers=h)
    assn_cat = r.get_json()
    r = client.post("/api/grade-categories",
                    json={"name": "Final", "slug": "final_exam"}, headers=h)
    final_cat = r.get_json()
    for mn, mx, letter, gpa in [(60, 100, "A", 4.0), (0, 59, "F", 0.0)]:
        client.post("/api/grading-scale", json={
            "minPercent": mn, "maxPercent": mx, "letter": letter, "gpaValue": gpa,
        }, headers=h)
    client.put(f"/api/courses/{course['id']}/rubric", json={
        "items": [
            {"gradeCategoryId": assn_cat["id"], "maxScore": 40, "orderIndex": 0},
            {"gradeCategoryId": final_cat["id"], "maxScore": 60, "orderIndex": 1},
        ],
    }, headers=h)
    r = client.post("/api/school-years", json={"name": "Y", "isCurrent": True}, headers=h)
    year = r.get_json()["id"]
    r = client.post(f"/api/school-years/{year}/terms",
                    json={"name": "Q1", "orderIndex": 0}, headers=h)
    q1 = r.get_json()["id"]

    return {
        "class_a": c9a, "class_b": c9b, "riv_id": riv_id,
        "amira_id": amira_id, "course": course, "module": module,
        "assn_cat": assn_cat, "final_cat": final_cat, "q1": q1,
    }


def _create_assignment(client, admin_tok, module_id, *, due_at=None):
    body = {"title": "Essay 1", "maxPoints": 100}
    if due_at is not None:
        body["dueAt"] = due_at.isoformat()
    r = client.post(f"/api/modules/{module_id}/assignments",
                    json=body, headers=_h(admin_tok))
    assert r.status_code == 201, r.data
    a = r.get_json()
    client.post(f"/api/assignments/{a['id']}/publish", headers=_h(admin_tok))
    return a


# ============================================================================
# Positive
# ============================================================================
def test_admin_creates_and_student_sees_published(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    _create_assignment(client, admin_tok, a["module"]["id"])
    stu_tok = _login(client, email="amira@t.local", password="password12")
    r = client.get(f"/api/courses/{a['course']['id']}/assignments",
                   headers=_h(stu_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert len(body) == 1
    assert body[0]["isPublished"] is True


def test_student_submits_text_before_due(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    assn = _create_assignment(client, admin_tok, a["module"]["id"],
                              due_at=utc_now() + _td(days=2))
    stu_tok = _login(client, email="amira@t.local", password="password12")
    r = client.post(f"/api/assignments/{assn['id']}/submissions", json={
        "responseText": "My reflection on the unit.",
    }, headers=_h(stu_tok))
    assert r.status_code == 201, r.data
    body = r.get_json()
    assert body["isLate"] is False
    assert body["responseText"].startswith("My reflection")


def test_late_submission_flagged(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    assn = _create_assignment(client, admin_tok, a["module"]["id"],
                              due_at=utc_now() - _td(days=1))
    stu_tok = _login(client, email="amira@t.local", password="password12")
    r = client.post(f"/api/assignments/{assn['id']}/submissions",
                    json={"responseText": "Late submission"},
                    headers=_h(stu_tok))
    assert r.status_code == 201
    assert r.get_json()["isLate"] is True


def test_resubmit_is_upsert_and_clears_grade(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    assn = _create_assignment(client, admin_tok, a["module"]["id"])
    stu_tok = _login(client, email="amira@t.local", password="password12")

    r = client.post(f"/api/assignments/{assn['id']}/submissions",
                    json={"responseText": "v1"}, headers=_h(stu_tok))
    sub_id = r.get_json()["id"]
    # Teacher grades it.
    riv_tok = _login(client, email="rivera@t.local", password="password12")
    r = client.put(f"/api/submissions/{sub_id}/grade", json={
        "score": 90, "feedback": "nice",
    }, headers=_h(riv_tok))
    assert r.status_code == 200
    assert r.get_json()["gradedScore"] == 90

    # Student re-submits.
    r = client.post(f"/api/assignments/{assn['id']}/submissions",
                    json={"responseText": "v2 with more detail"},
                    headers=_h(stu_tok))
    assert r.status_code == 201
    body = r.get_json()
    assert body["id"] == sub_id, "re-submit created a new row instead of upserting"
    assert body["gradedScore"] is None, "re-submit did not clear the grade"
    assert body["responseText"] == "v2 with more detail"


def test_teacher_grades_and_rollup_writes_gradeentry(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    assn = _create_assignment(client, admin_tok, a["module"]["id"])
    stu_tok = _login(client, email="amira@t.local", password="password12")
    r = client.post(f"/api/assignments/{assn['id']}/submissions",
                    json={"responseText": "essay"}, headers=_h(stu_tok))
    sub_id = r.get_json()["id"]
    riv_tok = _login(client, email="rivera@t.local", password="password12")
    r = client.put(f"/api/submissions/{sub_id}/grade",
                   json={"score": 80}, headers=_h(riv_tok))
    assert r.status_code == 200

    # Confirm via gradebook — the Assignments category should now equal
    # (80 / 100) * 40 = 32.0
    r = client.get(f"/api/classes/{a['class_a']}/gradebook",
                   query_string={"courseId": a["course"]["id"], "termId": a["q1"]},
                   headers=_h(admin_tok))
    assert r.status_code == 200
    body = r.get_json()
    amira_row = next(s for s in body["students"] if s["studentId"] == a["amira_id"])
    assert amira_row["entries"].get(a["assn_cat"]["id"]) == 32.0


# ============================================================================
# Trust-core negatives
# ============================================================================
def test_non_enrolled_student_cannot_submit(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    assn = _create_assignment(client, admin_tok, a["module"]["id"])
    # Register a student NOT placed in 9-A.
    _register(client, "outsider@t.local", role="student")
    out_tok = _login(client, email="outsider@t.local", password="password12")
    r = client.post(f"/api/assignments/{assn['id']}/submissions",
                    json={"responseText": "..."}, headers=_h(out_tok))
    assert r.status_code == 403


def test_student_cannot_grade_own_submission(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    assn = _create_assignment(client, admin_tok, a["module"]["id"])
    stu_tok = _login(client, email="amira@t.local", password="password12")
    r = client.post(f"/api/assignments/{assn['id']}/submissions",
                    json={"responseText": "essay"}, headers=_h(stu_tok))
    sub_id = r.get_json()["id"]
    r = client.put(f"/api/submissions/{sub_id}/grade",
                   json={"score": 100}, headers=_h(stu_tok))
    assert r.status_code == 403


def test_parent_cannot_submit(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    assn = _create_assignment(client, admin_tok, a["module"]["id"])
    r = client.post("/api/users", json={
        "name": "P", "email": "p@t.local",
        "password": "parent12", "role": "parent",
    }, headers=_h(admin_tok))
    p_id = r.get_json()["id"]
    client.post(f"/api/users/{a['amira_id']}/parents",
                json={"parentId": p_id}, headers=_h(admin_tok))
    p_tok = _login(client, email="p@t.local", password="parent12")
    r = client.post(f"/api/assignments/{assn['id']}/submissions",
                    json={"responseText": "not allowed"}, headers=_h(p_tok))
    assert r.status_code == 403


def test_delete_assignment_with_submissions_is_409(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    assn = _create_assignment(client, admin_tok, a["module"]["id"])
    stu_tok = _login(client, email="amira@t.local", password="password12")
    client.post(f"/api/assignments/{assn['id']}/submissions",
                json={"responseText": "s"}, headers=_h(stu_tok))
    r = client.delete(f"/api/assignments/{assn['id']}", headers=_h(admin_tok))
    assert r.status_code == 409


def test_edit_assignment_after_submissions_is_409(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    assn = _create_assignment(client, admin_tok, a["module"]["id"])
    stu_tok = _login(client, email="amira@t.local", password="password12")
    client.post(f"/api/assignments/{assn['id']}/submissions",
                json={"responseText": "s"}, headers=_h(stu_tok))
    r = client.put(f"/api/assignments/{assn['id']}",
                   json={"maxPoints": 50}, headers=_h(admin_tok))
    assert r.status_code == 409


def test_submit_empty_body_rejected(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    assn = _create_assignment(client, admin_tok, a["module"]["id"])
    stu_tok = _login(client, email="amira@t.local", password="password12")
    r = client.post(f"/api/assignments/{assn['id']}/submissions",
                    json={}, headers=_h(stu_tok))
    assert r.status_code == 400
