"""Phase 6 tests — parent portal.

Positive cases prove a linked parent can read their child's data. Trust-
core negatives prove a parent session can never write anywhere — Rule #7.
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


def _register_student(client, *, email, name="U"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": "password12", "role": "student", "name": name},
    )


def _admin_make_parent(client, admin_tok, *, email, name="Parent"):
    r = client.post("/api/users", json={
        "name": name, "email": email, "password": "parent12", "role": "parent",
    }, headers=_h(admin_tok))
    assert r.status_code == 201, r.data
    return r.get_json()["id"]


def _link(client, admin_tok, *, student_id, parent_id, relationship="guardian"):
    r = client.post(
        f"/api/users/{student_id}/parents",
        json={"parentId": parent_id, "relationship": relationship},
        headers=_h(admin_tok),
    )
    assert r.status_code == 201, r.data


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
                    json={"title": "Algebra 1", "gradeId": g9, "category": "math"},
                    headers=h)
    course = r.get_json()
    r = client.post(f"/api/courses/{course['id']}/modules",
                    json={"title": "M1"}, headers=h)
    module = r.get_json()
    lesson_ids = []
    for i in range(2):
        r = client.post(f"/api/modules/{module['id']}/lessons",
                        json={"title": f"L{i+1}", "type": "text", "contentText": "x"},
                        headers=h)
        lesson_ids.append(r.get_json()["id"])
    client.post(f"/api/courses/{course['id']}/publish", headers=h)
    return {"grade": g9, "class": c9a, "course": course, "module": module, "lessons": lesson_ids}


def _add_student(client, admin_tok, *, email, class_id, name=None):
    r = _register_student(client, email=email, name=name or email.split("@")[0])
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": class_id}, headers=_h(admin_tok))
    return sid


# ---------------------------------------------------------------------------
# Registration guard — role='parent' is refused on the self-service path.
# ---------------------------------------------------------------------------
def test_self_register_as_parent_is_refused(client):
    r = client.post("/api/auth/register", json={
        "name": "Sneaky", "email": "s@t.local", "password": "password12",
        "role": "parent",
    })
    assert r.status_code == 400, r.data
    body = r.get_json()
    assert "role" in body["error"].lower()


# ---------------------------------------------------------------------------
# Admin can create a parent + link, and list them
# ---------------------------------------------------------------------------
def test_admin_creates_parent_and_links(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    kid_id = _add_student(client, admin_tok, email="kid@t.local", class_id=a["class"])
    parent_id = _admin_make_parent(client, admin_tok, email="p@t.local")
    _link(client, admin_tok, student_id=kid_id, parent_id=parent_id)

    # Admin can list a student's parents.
    r = client.get(f"/api/users/{kid_id}/parents", headers=_h(admin_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert len(body) == 1
    assert body[0]["parentId"] == parent_id
    assert body[0]["relationship"] == "guardian"


def test_duplicate_link_conflicts(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    kid_id = _add_student(client, admin_tok, email="kid@t.local", class_id=a["class"])
    parent_id = _admin_make_parent(client, admin_tok, email="p@t.local")
    _link(client, admin_tok, student_id=kid_id, parent_id=parent_id)
    r = client.post(f"/api/users/{kid_id}/parents",
                    json={"parentId": parent_id},
                    headers=_h(admin_tok))
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Parent GETs their children and reads their data
# ---------------------------------------------------------------------------
def test_parent_reads_child_summary(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    kid_id = _add_student(client, admin_tok, email="kid@t.local",
                          class_id=a["class"], name="Kid")
    parent_id = _admin_make_parent(client, admin_tok, email="p@t.local")
    _link(client, admin_tok, student_id=kid_id, parent_id=parent_id)

    parent_tok = _login(client, email="p@t.local", password="parent12")

    r = client.get("/api/parents/mine/children", headers=_h(parent_tok))
    assert r.status_code == 200
    kids = r.get_json()
    assert len(kids) == 1
    assert kids[0]["studentId"] == kid_id
    assert kids[0]["name"] == "Kid"

    r = client.get(f"/api/parents/mine/children/{kid_id}/summary",
                   headers=_h(parent_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert body["student"]["id"] == kid_id
    # Child auto-enrolled in Algebra 1.
    titles = [e["course"]["title"] for e in body["enrollments"]]
    assert "Algebra 1" in titles


def test_parent_reads_child_enrollments_and_certs(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    kid_id = _add_student(client, admin_tok, email="kid@t.local", class_id=a["class"])
    parent_id = _admin_make_parent(client, admin_tok, email="p@t.local")
    _link(client, admin_tok, student_id=kid_id, parent_id=parent_id)
    parent_tok = _login(client, email="p@t.local", password="parent12")

    r = client.get(f"/api/parents/mine/children/{kid_id}/enrollments",
                   headers=_h(parent_tok))
    assert r.status_code == 200
    assert len(r.get_json()) >= 1

    r = client.get(f"/api/parents/mine/children/{kid_id}/certificates",
                   headers=_h(parent_tok))
    assert r.status_code == 200
    assert r.get_json() == []  # no completions yet


def test_parent_can_view_course_content(client):
    """Parent linked to enrolled child can hit course/lesson content the
    same way an enrolled student can. Verified via `can_view_content`."""
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    kid_id = _add_student(client, admin_tok, email="kid@t.local", class_id=a["class"])
    parent_id = _admin_make_parent(client, admin_tok, email="p@t.local")
    _link(client, admin_tok, student_id=kid_id, parent_id=parent_id)
    parent_tok = _login(client, email="p@t.local", password="parent12")

    # Fetch the course as the parent — includes modules + lessons.
    r = client.get(f"/api/courses/{a['course']['id']}", headers=_h(parent_tok))
    assert r.status_code == 200
    body = r.get_json()
    # Content is present (content-view gate opened for parent).
    lesson = body["modules"][0]["lessons"][0]
    assert lesson.get("contentText") == "x"


# ---------------------------------------------------------------------------
# Cross-parent isolation — parent A cannot see parent B's kid
# ---------------------------------------------------------------------------
def test_unlinked_parent_gets_403(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    kid_a = _add_student(client, admin_tok, email="kida@t.local", class_id=a["class"])
    kid_b = _add_student(client, admin_tok, email="kidb@t.local", class_id=a["class"])
    parent_a = _admin_make_parent(client, admin_tok, email="pa@t.local")
    parent_b = _admin_make_parent(client, admin_tok, email="pb@t.local")
    _link(client, admin_tok, student_id=kid_a, parent_id=parent_a)
    _link(client, admin_tok, student_id=kid_b, parent_id=parent_b)

    pa_tok = _login(client, email="pa@t.local", password="parent12")
    # parent_a asking for kid_b → 403.
    r = client.get(f"/api/parents/mine/children/{kid_b}/summary",
                   headers=_h(pa_tok))
    assert r.status_code == 403


def test_unknown_child_gets_404(client):
    admin_tok = _login_admin(client)
    _scaffold(client, admin_tok)
    parent_id = _admin_make_parent(client, admin_tok, email="p@t.local")
    parent_tok = _login(client, email="p@t.local", password="parent12")
    r = client.get(
        "/api/parents/mine/children/00000000-0000-0000-0000-000000000000/summary",
        headers=_h(parent_tok),
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Non-parent can't hit parent endpoints
# ---------------------------------------------------------------------------
def test_student_gets_403_on_parent_endpoint(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    _add_student(client, admin_tok, email="kid@t.local", class_id=a["class"])
    stu_tok = _login(client, email="kid@t.local", password="password12")
    r = client.get("/api/parents/mine/children", headers=_h(stu_tok))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# TRUST-CORE NEGATIVES — parent session cannot write anywhere
# ---------------------------------------------------------------------------
def test_parent_cannot_complete_lessons(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    kid_id = _add_student(client, admin_tok, email="kid@t.local", class_id=a["class"])
    parent_id = _admin_make_parent(client, admin_tok, email="p@t.local")
    _link(client, admin_tok, student_id=kid_id, parent_id=parent_id)
    parent_tok = _login(client, email="p@t.local", password="parent12")

    r = client.post(f"/api/lessons/{a['lessons'][0]}/complete",
                    headers=_h(parent_tok))
    assert r.status_code == 403


def test_parent_cannot_grade(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    kid_id = _add_student(client, admin_tok, email="kid@t.local", class_id=a["class"])
    parent_id = _admin_make_parent(client, admin_tok, email="p@t.local")
    _link(client, admin_tok, student_id=kid_id, parent_id=parent_id)
    parent_tok = _login(client, email="p@t.local", password="parent12")

    # Find child's enrollment.
    r = client.get(f"/api/parents/mine/children/{kid_id}/enrollments",
                   headers=_h(parent_tok))
    enrollment_id = r.get_json()[0]["id"]

    r = client.put(
        f"/api/enrollments/{enrollment_id}/grades",
        json={"termId": "any", "entries": []},
        headers=_h(parent_tok),
    )
    # Might be 400/403/404 depending on validation order, but never a 2xx.
    assert r.status_code >= 400


def test_parent_bp_refuses_non_get(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    kid_id = _add_student(client, admin_tok, email="kid@t.local", class_id=a["class"])
    parent_id = _admin_make_parent(client, admin_tok, email="p@t.local")
    _link(client, admin_tok, student_id=kid_id, parent_id=parent_id)
    parent_tok = _login(client, email="p@t.local", password="parent12")

    # POST to a parent GET path — before_request refuses.
    r = client.post("/api/parents/mine/children", headers=_h(parent_tok))
    assert r.status_code == 405


def test_parent_bp_allows_cors_preflight(client):
    """OPTIONS must pass so Flask-CORS can answer the browser preflight.
    Regression guard against the "Failed to fetch" bug — parent portal was
    broken on Flutter web when this ran through _forbid_non_get and got 405."""
    r = client.open(
        "/api/parents/mine/children",
        method="OPTIONS",
        headers={
            "Origin": "http://localhost:56123",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-session-token",
        },
    )
    # Flask-CORS returns 200 for a valid preflight.
    assert r.status_code < 300, f"preflight rejected with {r.status_code}"
    assert r.headers.get("Access-Control-Allow-Origin") is not None


def test_parent_cannot_revoke_cert(client):
    admin_tok = _login_admin(client)
    _scaffold(client, admin_tok)
    parent_id = _admin_make_parent(client, admin_tok, email="p@t.local")
    parent_tok = _login(client, email="p@t.local", password="parent12")
    # Non-existent id is fine; the point is the permission check happens first
    # and rejects parent role either way.
    r = client.post(
        "/api/certificates/00000000-0000-0000-0000-000000000000/revoke",
        json={"reason": "x"},
        headers=_h(parent_tok),
    )
    # 403 (require_admin) or 404 (cert not found after admin check) — either
    # is acceptable, so long as parent didn't succeed.
    assert r.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Admin can unlink
# ---------------------------------------------------------------------------
def test_admin_can_unlink(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    kid_id = _add_student(client, admin_tok, email="kid@t.local", class_id=a["class"])
    parent_id = _admin_make_parent(client, admin_tok, email="p@t.local")
    _link(client, admin_tok, student_id=kid_id, parent_id=parent_id)

    r = client.delete(
        f"/api/users/{kid_id}/parents/{parent_id}",
        headers=_h(admin_tok),
    )
    assert r.status_code == 200
    r = client.get(f"/api/users/{kid_id}/parents", headers=_h(admin_tok))
    assert r.get_json() == []
