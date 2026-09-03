"""Phase 1 residual tests — auth invariants that survive Phase 2's rules
change.

Phase 2 rewrote course/module/lesson permissions (curriculum is admin-owned,
per-class teachers are tracked separately). The auth flow itself (register /
login / me / logout / signed-session token / role decorators) is unchanged
and stays covered here. Phase 2's own test file (test_phase2.py) covers
the broader trust-core surface.
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
        "utils.permissions", "utils.grading", "utils.quizzes", "utils.certificates",
        "utils.analytics", "utils.attendance", "utils.timetables", "utils.assignments",
        "routes.dashboards", "routes.parents", "routes.attendance", "routes.timetables", "routes.assignments",
        "routes", "routes.auth", "routes.users",
        "routes.sections", "routes.grades", "routes.classes",
        "routes.courses", "routes.modules", "routes.lessons",
        "routes.enrollments", "routes.students",
        "routes.department_leaders", "routes.uploads",
        "app",
    ]:
        sys.modules.pop(mod, None)

    from app import create_app
    from config import Config
    from models import db

    class TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
        TESTING = True
        SQLALCHEMY_ENGINE_OPTIONS = {}

    app = create_app(TestConfig)
    from models import User  # local so the pop above has already run.
    with app.app_context():
        db.drop_all()
        db.create_all()
        # Phase 6: seed a root admin so tests that need admin-only endpoints
        # (parent account creation, etc.) have a signer available.
        u = User(name="Root Admin", email="admin@t.local", role="admin")
        u.set_password("adminpass1")
        db.session.add(u)
        db.session.commit()

    with app.test_client() as c:
        yield c


def _login(client, *, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.data
    return r.get_json()["sessionToken"]


def _login_admin(client):
    return _login(client, email="admin@t.local", password="adminpass1")


def _register(client, *, email, password="password12", role="student", name="U"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "role": role, "name": name},
    )


def _h(tok):
    return {"X-Session-Token": tok}


# ---------------------------------------------------------------------------
# Auth roundtrips (unchanged from Phase 1)
# ---------------------------------------------------------------------------
def test_register_login_me_roundtrip(client):
    r = _register(client, email="alice@example.com", role="instructor", name="Alice")
    assert r.status_code == 201, r.data
    body = r.get_json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["role"] == "instructor"
    token = body["sessionToken"]

    r = client.get("/api/auth/me", headers=_h(token))
    assert r.status_code == 200
    assert r.get_json()["user"]["email"] == "alice@example.com"

    r = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "password12"},
    )
    assert r.status_code == 200


def test_login_wrong_password_returns_401(client):
    _register(client, email="bob@example.com")
    r = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "wrong-password"},
    )
    assert r.status_code == 401


def test_me_requires_authentication(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_logout_bumps_token_version(client):
    tok = _register(client, email="c@example.com").get_json()["sessionToken"]
    r = client.post("/api/auth/logout", headers=_h(tok))
    assert r.status_code == 200
    # Old token no longer works.
    r = client.get("/api/auth/me", headers=_h(tok))
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Role decorators still guard the new endpoints
# ---------------------------------------------------------------------------
def test_non_admin_cannot_create_grade(client):
    """Grade CRUD is admin-only; a plain instructor is refused."""
    tok = _register(client, email="ins@example.com", role="instructor").get_json()["sessionToken"]
    r = client.post("/api/grades", json={"name": "Grade 1"}, headers=_h(tok))
    assert r.status_code == 403


def test_non_admin_cannot_create_course(client):
    """Course creation is admin-only in Phase 2 (was instructor+admin in P1)."""
    tok = _register(client, email="ins2@example.com", role="instructor").get_json()["sessionToken"]
    r = client.post(
        "/api/courses",
        json={"title": "T", "gradeId": "nonexistent"},
        headers=_h(tok),
    )
    assert r.status_code == 403


def test_parent_cannot_hit_admin_endpoints(client):
    # Phase 6: self-register with role='parent' is refused. Admin creates
    # the account via POST /api/users.
    admin_tok = _login_admin(client)
    r = client.post(
        "/api/users",
        json={
            "name": "P", "email": "parent@example.com",
            "password": "password12", "role": "parent",
        },
        headers=_h(admin_tok),
    )
    assert r.status_code == 201, r.data
    tok = _login(client, email="parent@example.com", password="password12")
    r = client.post("/api/sections", json={"name": "S"}, headers=_h(tok))
    assert r.status_code == 403


def test_student_can_hit_own_me(client):
    tok = _register(client, email="stu@example.com", role="student").get_json()["sessionToken"]
    r = client.get("/api/auth/me", headers=_h(tok))
    assert r.status_code == 200
