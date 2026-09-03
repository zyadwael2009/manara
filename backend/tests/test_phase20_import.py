"""Phase 20 tests — admin CSV bulk import.

Covers:
  * Happy path: two new students + a teacher, placed + mandatory-enrolled.
  * Idempotency: re-uploading the same CSV updates in place (no dupes).
  * Row errors: bad role, malformed email, unknown grade/class, missing fields.
  * Role-change refusal: cannot flip an existing student to admin via CSV.
  * Non-admin blocked (401 or 403 — anything <400 would be a leak).
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
        "routes.today", "routes.announcements", "routes.admin_import",
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


def _scaffold(client, admin_tok):
    """One section, Grade 9, one class 9-A, one mandatory course (English 9)."""
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
    return {"class_a": c9a, "grade": g9, "course": eng}


def _upload(client, tok, csv_text: str):
    data = {"file": (io.BytesIO(csv_text.encode("utf-8")), "roster.csv")}
    return client.post(
        "/api/admin/users/import",
        data=data,
        content_type="multipart/form-data",
        headers=_h(tok),
    )


# ---------------------------------------------------------------------------
# Happy path + idempotency
# ---------------------------------------------------------------------------
def test_bulk_import_creates_places_and_enrolls_students(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    csv_text = (
        "email,name,role,gradeName,className\n"
        "amira@t.local,Amira Al-Farsi,student,Grade 9,9-A\n"
        "bilal@t.local,Bilal Haddad,student,Grade 9,9-A\n"
        "rivera@t.local,Ms. Rivera,instructor,,\n"
    )
    r = _upload(client, admin, csv_text)
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert len(body["created"]) == 3
    assert body["errors"] == []
    assert body["updated"] == []
    # Amira must have her class + at least one mandatory enrollment.
    from models import Enrollment, User
    amira = User.query.filter_by(email="amira@t.local").first()
    assert amira is not None
    assert amira.class_id is not None
    assert Enrollment.query.filter_by(student_id=amira.id).count() >= 1


def test_bulk_import_is_idempotent_on_second_run(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    csv_text = (
        "email,name,role,gradeName,className\n"
        "amira@t.local,Amira Al-Farsi,student,Grade 9,9-A\n"
    )
    r1 = _upload(client, admin, csv_text).get_json()
    r2 = _upload(client, admin, csv_text).get_json()
    assert len(r1["created"]) == 1
    assert len(r2["updated"]) == 1
    assert len(r2["created"]) == 0
    from models import User
    assert User.query.filter_by(email="amira@t.local").count() == 1


# ---------------------------------------------------------------------------
# Row errors
# ---------------------------------------------------------------------------
def test_bad_rows_land_in_errors_not_created(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    csv_text = (
        "email,name,role,gradeName,className\n"
        "no-at-symbol,Bad Email,student,,\n"
        "x@t.local,No Role,,,\n"
        "y@t.local,Bad Role,principal,,\n"
        "z@t.local,Missing Grade,student,,9-A\n"
        "w@t.local,Ghost Class,student,Grade 9,9-Z\n"
        "ok@t.local,Fine,student,Grade 9,9-A\n"
    )
    body = _upload(client, admin, csv_text).get_json()
    errored_rows = {e["row"] for e in body["errors"]}
    # Rows 2..6 in the CSV are bad; row 7 is the only good one.
    assert errored_rows == {2, 3, 4, 5, 6}
    assert len(body["created"]) == 1
    assert body["created"][0]["email"] == "ok@t.local"


def test_role_change_via_csv_refused(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    _upload(client, admin, (
        "email,name,role,gradeName,className\n"
        "amira@t.local,Amira,student,Grade 9,9-A\n"
    ))
    # Now try to flip her to admin.
    #
    # Phase 25 hard-audit fix C-1 changed the semantics: role="admin"
    # is refused at the role-validation step for EVERY row (not just
    # role-change), because the CSV importer must never mint admins.
    # So the sneaky row lands in `errors[]`, not `skipped[]`.
    body = _upload(client, admin, (
        "email,name,role,gradeName,className\n"
        "amira@t.local,Amira Sneaky,admin,,\n"
    )).get_json()
    assert body["created"] == []
    assert body["updated"] == []
    assert len(body["errors"]) == 1
    assert "role must be one of" in body["errors"][0]["error"]
    # Confirm role really didn't flip in the DB.
    from models import User
    amira = User.query.filter_by(email="amira@t.local").first()
    assert amira.role == "student"

    # And a legitimate role change (student → parent) still lands in
    # skipped with the original "refusing to change" reason.
    body = _upload(client, admin, (
        "email,name,role,gradeName,className\n"
        "amira@t.local,Amira Retry,parent,,\n"
    )).get_json()
    assert len(body["skipped"]) == 1
    assert "refusing to change" in body["skipped"][0]["reason"]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_non_admin_cannot_import(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    # Create a student + log them in.
    client.post("/api/auth/register", json={
        "name": "S", "email": "s@t.local", "password": "password12", "role": "student",
    })
    stu = _login(client, email="s@t.local", password="password12")
    r = _upload(client, stu, "email,name,role\nx@t.local,X,student\n")
    assert r.status_code in (401, 403)


def test_empty_csv_and_missing_file_get_400(client):
    admin = _login_admin(client)
    # No file at all.
    r = client.post("/api/admin/users/import", headers=_h(admin))
    assert r.status_code == 400
    # Empty file.
    r = _upload(client, admin, "")
    assert r.status_code == 400
    # Header but no data — succeeds with empty envelope.
    r = _upload(client, admin, "email,name,role\n")
    assert r.status_code == 200
    body = r.get_json()
    assert body["created"] == []
    assert body["errors"] == []
