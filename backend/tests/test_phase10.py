"""Phase 10 — coverage gap tests from the post-audit medium pass.

Regression guards for:
  M8  · Dept-leaders CRUD (auth pivot for `can_edit_course_content`)
  M9  · Quiz-authoring "locked-after-attempts" 409 guards
  M12 · Admin manual enroll + mandatory-drop guard
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
        "utils.certificates", "utils.analytics", "utils.attendance", "utils.timetables", "utils.assignments",
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
    """One section, one grade, one class (9-A), one course (Math) with a
    module + one lesson. Returns everything the tests need."""
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
                    json={"title": "Math", "gradeId": g9, "category": "math"},
                    headers=h)
    math = r.get_json()
    r = client.post(f"/api/courses/{math['id']}/modules",
                    json={"title": "M1"}, headers=h)
    module = r.get_json()
    r = client.post(f"/api/modules/{module['id']}/lessons",
                    json={"title": "L1", "type": "text", "contentText": "x"},
                    headers=h)
    lesson = r.get_json()
    client.post(f"/api/courses/{math['id']}/publish", headers=h)
    return {
        "section": high, "grade": g9, "class": c9a,
        "course": math, "module": module, "lesson": lesson,
    }


# ============================================================================
# M8 — Dept-leaders CRUD
# ============================================================================
def test_m8_admin_can_set_and_clear_dept_leader(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    _register(client, "rivera@t.local", role="instructor")
    riv_id = client.post("/api/auth/login", json={
        "email": "rivera@t.local", "password": "password12",
    }).get_json()["user"]["id"]

    # Set
    r = client.post("/api/department-leaders", json={
        "department": "math", "sectionId": a["section"], "teacherId": riv_id,
    }, headers=_h(admin_tok))
    assert r.status_code == 200, r.data
    leader = r.get_json()
    assert leader["teacherId"] == riv_id
    assert leader["department"] == "math"

    # List
    r = client.get("/api/department-leaders", headers=_h(admin_tok))
    assert r.status_code == 200
    assert any(l["id"] == leader["id"] for l in r.get_json())

    # Clear
    r = client.delete(f"/api/department-leaders/{leader['id']}", headers=_h(admin_tok))
    assert r.status_code == 200


def test_m8_non_admin_cannot_set_dept_leader(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    _register(client, "rivera@t.local", role="instructor")
    riv_id = client.post("/api/auth/login", json={
        "email": "rivera@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    riv_tok = _login(client, email="rivera@t.local", password="password12")

    r = client.post("/api/department-leaders", json={
        "department": "math", "sectionId": a["section"], "teacherId": riv_id,
    }, headers=_h(riv_tok))
    assert r.status_code == 403


def test_m8_dept_leader_can_edit_course_they_dont_teach(client):
    """Dept-leader pivot: assigning Rivera as math dept-leader for High
    section should let her edit Math course content even without a
    class-course-teacher row."""
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    _register(client, "rivera@t.local", role="instructor")
    riv_id = client.post("/api/auth/login", json={
        "email": "rivera@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    riv_tok = _login(client, email="rivera@t.local", password="password12")

    # BEFORE assignment: Rivera can't edit the course.
    r = client.put(f"/api/courses/{a['course']['id']}", json={
        "title": "Math (attempted rename)",
    }, headers=_h(riv_tok))
    assert r.status_code == 403

    # Assign her as dept leader.
    client.post("/api/department-leaders", json={
        "department": "math", "sectionId": a["section"], "teacherId": riv_id,
    }, headers=_h(admin_tok))

    # AFTER assignment: Rivera can edit.
    r = client.put(f"/api/courses/{a['course']['id']}", json={
        "title": "Math II",
    }, headers=_h(riv_tok))
    assert r.status_code == 200, r.data
    assert r.get_json()["title"] == "Math II"


# ============================================================================
# M9 — Quiz-authoring locked-after-attempts guards
# ============================================================================
def _seed_quiz_with_attempts(client, admin_tok, a):
    """Set up a quiz with one option-per-answer and one student attempt so
    the "locked-after-attempts" branch of each mutating endpoint can be hit."""
    h = _h(admin_tok)
    r = client.post(f"/api/modules/{a['module']['id']}/quizzes", json={
        "title": "Q1", "passingScore": 60,
    }, headers=h)
    quiz = r.get_json()
    r = client.post(f"/api/quizzes/{quiz['id']}/questions", json={
        "type": "mc_single", "prompt": "?", "points": 1,
    }, headers=h)
    question = r.get_json()
    r = client.post(f"/api/quiz-questions/{question['id']}/options", json={
        "text": "A", "isCorrect": True,
    }, headers=h)
    opt_a = r.get_json()
    r = client.post(f"/api/quiz-questions/{question['id']}/options", json={
        "text": "B", "isCorrect": False,
    }, headers=h)
    opt_b = r.get_json()
    client.post(f"/api/quizzes/{quiz['id']}/publish", headers=h)

    _register(client, "amira@t.local", role="student")
    sid = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class", json={"classId": a["class"]}, headers=h)
    stu_tok = _login(client, email="amira@t.local", password="password12")
    r = client.post(f"/api/quizzes/{quiz['id']}/start", headers=_h(stu_tok))
    attempt = r.get_json()["attempt"]
    client.post(f"/api/quiz-attempts/{attempt['id']}/submit", json={
        "answers": [{"questionId": question["id"], "selectedOptionIds": [opt_a["id"]]}],
    }, headers=_h(stu_tok))
    return quiz, question, opt_a, opt_b


def test_m9_cannot_change_question_type_after_attempts(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    quiz, question, _, _ = _seed_quiz_with_attempts(client, admin_tok, a)
    r = client.put(f"/api/quiz-questions/{question['id']}", json={
        "type": "essay",
    }, headers=_h(admin_tok))
    assert r.status_code == 409


def test_m9_cannot_delete_question_after_attempts(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    _, question, _, _ = _seed_quiz_with_attempts(client, admin_tok, a)
    r = client.delete(f"/api/quiz-questions/{question['id']}", headers=_h(admin_tok))
    assert r.status_code == 409


def test_m9_cannot_delete_option_after_attempts(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    _, _, opt_a, _ = _seed_quiz_with_attempts(client, admin_tok, a)
    r = client.delete(f"/api/quiz-options/{opt_a['id']}", headers=_h(admin_tok))
    assert r.status_code == 409


def test_m9_cannot_flip_option_correctness_after_attempts(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    _, _, opt_a, _ = _seed_quiz_with_attempts(client, admin_tok, a)
    r = client.put(f"/api/quiz-options/{opt_a['id']}", json={
        "isCorrect": False,
    }, headers=_h(admin_tok))
    assert r.status_code == 409


# ============================================================================
# M12 — Admin manual enroll + mandatory-drop guard
# ============================================================================
def test_m12_admin_can_manual_enroll(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    _register(client, "bob@t.local", role="student")
    sid = client.post("/api/auth/login", json={
        "email": "bob@t.local", "password": "password12",
    }).get_json()["user"]["id"]

    # Bob's not placed in a class → not auto-enrolled. Admin manually enrolls.
    r = client.post(f"/api/courses/{a['course']['id']}/enrollments", json={
        "studentId": sid,
    }, headers=_h(admin_tok))
    assert r.status_code == 201, r.data
    assert r.get_json()["studentId"] == sid


def test_m12_drop_mandatory_current_grade_refuses(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    _register(client, "amira@t.local", role="student")
    sid = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    # Place her in 9-A → auto-enrolls in Math (mandatory).
    client.put(f"/api/users/{sid}/class", json={"classId": a["class"]}, headers=_h(admin_tok))
    stu_tok = _login(client, email="amira@t.local", password="password12")
    enr_id = client.get("/api/enrollments/mine", headers=_h(stu_tok)).get_json()[0]["id"]

    r = client.delete(f"/api/enrollments/{enr_id}", headers=_h(admin_tok))
    # Should refuse — mandatory course of the student's current grade.
    assert r.status_code == 409, r.data
    body = r.get_json()
    assert "mandatory" in body.get("error", "").lower()


def test_m12_drop_elective_soft_drops_ok(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    h = _h(admin_tok)

    # Add an elective course + pick it for Amira.
    r = client.post("/api/courses", json={
        "title": "French I", "gradeId": a["grade"],
        "category": "languages", "electiveGroup": "language",
    }, headers=h)
    fr = r.get_json()
    r = client.post(f"/api/courses/{fr['id']}/modules", json={"title": "M"}, headers=h)
    fr_mod = r.get_json()
    client.post(f"/api/modules/{fr_mod['id']}/lessons",
                json={"title": "L", "type": "text", "contentText": "x"}, headers=h)
    client.post(f"/api/courses/{fr['id']}/publish", headers=h)

    _register(client, "amira@t.local", role="student")
    sid = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class", json={"classId": a["class"]}, headers=h)
    client.put(f"/api/users/{sid}/electives/language", json={"courseId": fr["id"]},
               headers=h)

    stu_tok = _login(client, email="amira@t.local", password="password12")
    enrs = client.get("/api/enrollments/mine", headers=_h(stu_tok)).get_json()
    fr_enr = next(e for e in enrs if e["courseId"] == fr["id"])

    r = client.delete(f"/api/enrollments/{fr_enr['id']}", headers=_h(admin_tok))
    assert r.status_code == 200, r.data
