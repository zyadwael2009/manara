"""The student Today and Assignments hubs.

Guards three new read-only surfaces:
  * `GET /api/students/today` — today's periods + assignments due today +
    open quizzes with attempts remaining.
  * `GET /api/assignments/my`  — every published assignment across the
    caller's live enrollments, with per-row submission state.
  * `GET /api/courses/<id>`    — now attaches `myAttendance` for the
    enrolled student caller.

Trust-core: no writes, no rollups. Assignment/quiz submission flows are
untouched — these are pure projections.

Originally Phase 18.
"""
from __future__ import annotations

from tests.conftest import register_user as _register

from datetime import date as _date, datetime, timedelta

import pytest


def _h(tok):
    return {"X-Session-Token": tok}


def _login(client, *, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.data
    return r.get_json()["sessionToken"]


def _login_admin(client):
    return _login(client, email="admin@t.local", password="adminpass1")


def _scaffold(client, admin_tok):
    """Grade 9 / 9-A / Rivera homeroom / Amira placed / English 9 published."""
    h = _h(admin_tok)
    r = client.post("/api/sections", json={"name": "High"}, headers=h)
    high = r.get_json()["id"]
    r = client.post("/api/grades",
                    json={"name": "Grade 9", "sectionId": high, "orderIndex": 9},
                    headers=h)
    g9 = r.get_json()["id"]
    _register(client, "rivera@t.local", role="instructor", name="Rivera")
    riv_id = client.post("/api/auth/login", json={
        "email": "rivera@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    r = client.post("/api/classes",
                    json={"name": "9-A", "gradeId": g9, "homeroomTeacherId": riv_id},
                    headers=h)
    c9a = r.get_json()["id"]
    r = client.post("/api/courses",
                    json={"title": "English 9", "gradeId": g9, "category": "english"},
                    headers=h)
    eng = r.get_json()
    r = client.post(f"/api/courses/{eng['id']}/modules",
                    json={"title": "Unit 1"}, headers=h)
    module = r.get_json()
    client.post(f"/api/modules/{module['id']}/lessons",
                json={"title": "L1", "type": "text", "contentText": "x"},
                headers=h)
    client.post(f"/api/courses/{eng['id']}/publish", headers=h)
    _register(client, "amira@t.local", role="student", name="Amira")
    amira_id = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/users/{amira_id}/class", json={"classId": c9a}, headers=h)
    return {
        "class_a": c9a, "riv_id": riv_id, "amira_id": amira_id,
        "course": eng, "module": module, "grade": g9,
    }


def _iso_z(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


# ---------------------------------------------------------------------------
# /api/students/today
# ---------------------------------------------------------------------------
def test_today_returns_periods_assignments_and_open_quizzes(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    # A period today: 09:00-09:45 on today's weekday for 9-A.
    dow = _date.today().weekday()
    if dow > 4:
        pytest.skip("Runs Mon-Fri only (school days).")
    client.put(
        f"/api/classes/{s['class_a']}/timetable/periods",
        json={"periods": [
            {"courseId": s["course"]["id"], "dayOfWeek": dow,
             "startTime": "09:00", "endTime": "09:45", "room": "9-A"},
        ]},
        headers=_h(admin),
    )
    # An assignment due today at 23:59.
    day_end = datetime.combine(_date.today(), datetime.min.time()) + timedelta(hours=23, minutes=59)
    r = client.post(f"/api/modules/{s['module']['id']}/assignments", json={
        "title": "Essay draft", "maxPoints": 50, "dueAt": _iso_z(day_end),
    }, headers=_h(admin))
    aid = r.get_json()["id"]
    client.post(f"/api/assignments/{aid}/publish", headers=_h(admin))

    # A published quiz Amira hasn't taken.
    r = client.post(f"/api/modules/{s['module']['id']}/quizzes",
                    json={"title": "Q1", "passingScore": 60}, headers=_h(admin))
    qid = r.get_json()["id"]
    r = client.post(f"/api/quizzes/{qid}/questions",
                    json={"type": "mc_single", "prompt": "?", "points": 1},
                    headers=_h(admin))
    q1 = r.get_json()
    client.post(f"/api/quiz-questions/{q1['id']}/options",
                json={"text": "A", "isCorrect": True}, headers=_h(admin))
    client.post(f"/api/quizzes/{qid}/publish", headers=_h(admin))

    stu = _login(client, email="amira@t.local", password="password12")
    r = client.get("/api/students/today", headers=_h(stu))
    assert r.status_code == 200
    body = r.get_json()
    assert body["date"] == _date.today().isoformat()
    assert any(p.get("startTime") == "09:00" for p in body["periods"])
    titles = [a["title"] for a in body["assignmentsDueToday"]]
    assert "Essay draft" in titles
    quiz_titles = [q["title"] for q in body["openQuizzes"]]
    assert "Q1" in quiz_titles


def test_today_empty_for_non_students(client):
    admin = _login_admin(client)
    r = client.get("/api/students/today", headers=_h(admin))
    assert r.status_code == 200
    body = r.get_json()
    assert body["periods"] == []
    assert body["assignmentsDueToday"] == []
    assert body["openQuizzes"] == []


def test_today_excludes_unpublished_or_capped_quizzes(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    # Draft quiz — never returned.
    r = client.post(f"/api/modules/{s['module']['id']}/quizzes",
                    json={"title": "draft"}, headers=_h(admin))
    # Capped quiz — one attempt allowed, we'll use it up.
    r = client.post(f"/api/modules/{s['module']['id']}/quizzes",
                    json={"title": "capped", "passingScore": 60, "maxAttempts": 1},
                    headers=_h(admin))
    capped_id = r.get_json()["id"]
    r = client.post(f"/api/quizzes/{capped_id}/questions",
                    json={"type": "mc_single", "prompt": "?", "points": 1},
                    headers=_h(admin))
    q = r.get_json()
    r = client.post(f"/api/quiz-questions/{q['id']}/options",
                    json={"text": "A", "isCorrect": True}, headers=_h(admin))
    opt = r.get_json()
    client.post(f"/api/quizzes/{capped_id}/publish", headers=_h(admin))
    stu = _login(client, email="amira@t.local", password="password12")
    # Amira takes + submits (uses her only attempt).
    r = client.post(f"/api/quizzes/{capped_id}/start", headers=_h(stu))
    attempt = r.get_json()["attempt"]
    client.post(f"/api/quiz-attempts/{attempt['id']}/submit", json={
        "answers": [{"questionId": q["id"], "selectedOptionIds": [opt["id"]]}],
    }, headers=_h(stu))
    r = client.get("/api/students/today", headers=_h(stu))
    titles = [q["title"] for q in r.get_json()["openQuizzes"]]
    assert "draft" not in titles
    assert "capped" not in titles


# ---------------------------------------------------------------------------
# /api/assignments/my
# ---------------------------------------------------------------------------
def test_assignments_my_returns_published_in_my_enrollments(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    for title in ["A1", "A2"]:
        r = client.post(f"/api/modules/{s['module']['id']}/assignments",
                        json={"title": title, "maxPoints": 50},
                        headers=_h(admin))
        client.post(f"/api/assignments/{r.get_json()['id']}/publish",
                    headers=_h(admin))
    # A draft — never returned.
    client.post(f"/api/modules/{s['module']['id']}/assignments",
                json={"title": "draft"}, headers=_h(admin))

    stu = _login(client, email="amira@t.local", password="password12")
    r = client.get("/api/assignments/my", headers=_h(stu))
    assert r.status_code == 200
    titles = [x["title"] for x in r.get_json()]
    assert "A1" in titles and "A2" in titles
    assert "draft" not in titles
    for row in r.get_json():
        assert row["course"]["title"] == "English 9"
        assert row["moduleTitle"] == "Unit 1"
        assert "mySubmission" in row


def test_assignments_my_empty_for_non_students(client):
    admin = _login_admin(client)
    r = client.get("/api/assignments/my", headers=_h(admin))
    assert r.status_code == 200
    assert r.get_json() == []


# ---------------------------------------------------------------------------
# Course-detail attendance decoration
# ---------------------------------------------------------------------------
def test_course_detail_decorates_myattendance_for_student(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    riv = _login(client, email="rivera@t.local", password="password12")
    # Mark Amira present today.
    client.put(f"/api/classes/{s['class_a']}/attendance", json={
        "date": _date.today().isoformat(),
        "marks": [{"studentId": s["amira_id"], "status": "present"}],
    }, headers=_h(riv))

    stu = _login(client, email="amira@t.local", password="password12")
    r = client.get(f"/api/courses/{s['course']['id']}", headers=_h(stu))
    assert r.status_code == 200
    body = r.get_json()
    att = body["myAttendance"]
    assert att["present"] == 1
    assert att["absent"] == 0
    assert att["total"] == 1
    assert att["percent"] == 100.0


def test_course_detail_omits_myattendance_for_non_student(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    r = client.get(f"/api/courses/{s['course']['id']}", headers=_h(admin))
    assert r.status_code == 200
    assert "myAttendance" not in r.get_json()
