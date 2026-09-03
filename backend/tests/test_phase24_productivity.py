"""Phase 24 tests — streak + badges + search + question bank."""
from __future__ import annotations

import sys
from datetime import date as _date, datetime, timedelta, timezone

import pytest


def _today_utc() -> _date:
    """Streak endpoint stamps `last_activity_date` from UTC (matches
    `utils.streak`), so tests must compare against the UTC date, not
    local `date.today()` — otherwise this file breaks at every UTC
    midnight rollover in non-UTC time zones. Repaired Phase 31 · T4."""
    return datetime.now(timezone.utc).date()


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
                json={"title": "Reading 1", "type": "text", "contentText": "x"},
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
# Streak
# ---------------------------------------------------------------------------
def test_streak_tick_first_time_sets_one(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    r = client.post("/api/streak/tick", headers=_h(stu))
    assert r.status_code == 200
    body = r.get_json()
    assert body["currentStreak"] == 1
    assert body["longestStreak"] == 1
    assert body["lastActivityDate"] == _today_utc().isoformat()


def test_streak_tick_same_day_is_noop(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    client.post("/api/streak/tick", headers=_h(stu))
    client.post("/api/streak/tick", headers=_h(stu))
    body = client.get("/api/streak/mine", headers=_h(stu)).get_json()
    assert body["currentStreak"] == 1


def test_streak_grows_on_consecutive_day(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    client.post("/api/streak/tick", headers=_h(stu))
    # Force yesterday's last_activity_date in the DB so today's tick counts.
    from models import StudentStreak, db
    row = db.session.get(StudentStreak, s["amira_id"])
    row.last_activity_date = _today_utc() - timedelta(days=1)
    db.session.commit()
    r = client.post("/api/streak/tick", headers=_h(stu))
    body = r.get_json()
    assert body["currentStreak"] == 2
    assert body["longestStreak"] >= 2


def test_streak_resets_on_gap(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    client.post("/api/streak/tick", headers=_h(stu))
    from models import StudentStreak, db
    row = db.session.get(StudentStreak, s["amira_id"])
    row.current_streak = 5
    row.longest_streak = 5
    row.last_activity_date = _today_utc() - timedelta(days=10)
    db.session.commit()
    r = client.post("/api/streak/tick", headers=_h(stu))
    body = r.get_json()
    assert body["currentStreak"] == 1
    assert body["longestStreak"] == 5  # kept


# ---------------------------------------------------------------------------
# Badges
# ---------------------------------------------------------------------------
def test_badges_all_default_to_unearned(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    body = client.get("/api/badges/mine", headers=_h(stu)).get_json()
    assert body["earnedCount"] == 0
    ids = {b["id"] for b in body["badges"]}
    assert ids == {"first_cert", "five_quiz_streak", "perfect_week", "ten_day_streak"}


def test_ten_day_streak_badge_earned_when_longest_hits_ten(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    # Seed a longest streak of 10 in the DB directly.
    from models import StudentStreak, db
    db.session.add(StudentStreak(
        user_id=s["amira_id"], current_streak=10, longest_streak=10,
        last_activity_date=_today_utc(),
    ))
    db.session.commit()
    body = client.get("/api/badges/mine", headers=_h(stu)).get_json()
    earned = [b for b in body["badges"] if b["earned"]]
    assert any(b["id"] == "ten_day_streak" for b in earned)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def test_search_finds_lesson_in_enrolled_course(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    r = client.get("/api/search?q=Reading", headers=_h(stu))
    assert r.status_code == 200
    results = r.get_json()["results"]
    kinds = {r["kind"] for r in results}
    assert "lesson" in kinds


def test_search_min_chars_returns_empty(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    r = client.get("/api/search?q=a", headers=_h(stu))
    body = r.get_json()
    assert body["results"] == []


def test_search_student_scope_is_admin_only(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    # Amira searches for "Amira" — she is a student but her own row
    # shouldn't appear via a student query (scope=student is admin-only).
    r = client.get("/api/search?q=Amira&scope=student", headers=_h(stu))
    assert r.status_code == 200
    assert r.get_json()["results"] == []
    r = client.get("/api/search?q=Amira&scope=student", headers=_h(admin))
    assert any(x["kind"] == "student" for x in r.get_json()["results"])


# ---------------------------------------------------------------------------
# Question bank
# ---------------------------------------------------------------------------
def test_bank_crud_and_adopt_into_quiz(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    # Add a bank item.
    r = client.post(f"/api/courses/{s['course']['id']}/question-bank", json={
        "type": "mc_single", "prompt": "Capital of France?", "points": 2,
        "options": [
            {"text": "Paris", "isCorrect": True},
            {"text": "Rome", "isCorrect": False},
        ],
    }, headers=_h(admin))
    assert r.status_code == 201, r.data
    item_id = r.get_json()["id"]

    # Listing returns it.
    rows = client.get(f"/api/courses/{s['course']['id']}/question-bank",
                      headers=_h(admin)).get_json()
    assert any(x["id"] == item_id for x in rows)

    # Create a quiz (empty), then adopt the item into it.
    r = client.post(f"/api/modules/{s['module']['id']}/quizzes",
                    json={"title": "Reused"}, headers=_h(admin))
    quiz_id = r.get_json()["id"]
    r = client.post(f"/api/quizzes/{quiz_id}/adopt-bank-items",
                    json={"itemIds": [item_id]}, headers=_h(admin))
    assert r.status_code == 200
    assert r.get_json()["adopted"] == 1

    # Confirm the quiz now has that question with its options.
    r = client.get(f"/api/quizzes/{quiz_id}", headers=_h(admin)).get_json()
    assert len(r["questions"]) == 1
    assert r["questions"][0]["prompt"] == "Capital of France?"
    assert r["questions"][0]["points"] == 2


def test_bank_delete_by_teacher_forbidden(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    r = client.post(f"/api/courses/{s['course']['id']}/question-bank", json={
        "type": "mc_single", "prompt": "x",
        "options": [{"text": "a", "isCorrect": True}],
    }, headers=_h(admin))
    item_id = r.get_json()["id"]
    # A random other student → 403.
    stu = _login(client, email="amira@t.local", password="password12")
    r = client.delete(f"/api/bank-items/{item_id}", headers=_h(stu))
    assert r.status_code == 403
