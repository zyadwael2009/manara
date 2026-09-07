"""Notifications, direct messages, lesson comments, homework board.

One consolidated file (four features share the same scaffold and are
small enough that four separate files would be over-organized).

Originally Phase 21.
"""
from __future__ import annotations

from tests.conftest import register_user as _register

from datetime import date as _date


def _h(tok):
    return {"X-Session-Token": tok}


def _login(client, *, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.data
    return r.get_json()["sessionToken"]


def _login_admin(client):
    return _login(client, email="admin@t.local", password="adminpass1")


def _scaffold(client, admin_tok):
    """Grade 9, class 9-A (Rivera homeroom, Chen teaches Math), Amira
    student, Fatima parent-linked to Amira."""
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
    _register(client, "chen@t.local", role="instructor", name="Chen")
    chen_id = client.post("/api/auth/login", json={
        "email": "chen@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    r = client.post("/api/classes",
                    json={"name": "9-A", "gradeId": g9, "homeroomTeacherId": riv_id},
                    headers=h)
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
    client.put(f"/api/classes/{c9a}/courses/{math['id']}/teacher",
               json={"teacherId": chen_id}, headers=h)
    _register(client, "amira@t.local", role="student", name="Amira")
    amira_id = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/users/{amira_id}/class", json={"classId": c9a}, headers=h)
    # Parents are admin-created (self-registration refuses role=parent).
    r = client.post("/api/users", json={
        "name": "Fatima", "email": "fatima@t.local",
        "password": "password12", "role": "parent",
    }, headers=h)
    fatima_id = r.get_json()["id"]
    client.post(f"/api/users/{amira_id}/parents",
                json={"parentId": fatima_id}, headers=h)
    return {
        "class_a": c9a, "riv_id": riv_id, "chen_id": chen_id,
        "amira_id": amira_id, "fatima_id": fatima_id,
        "course": math, "module": module, "lesson": lesson,
    }


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
def test_announcement_writes_notifications_for_targeted_students(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    # School-wide announcement → Amira gets a notification.
    r = client.post("/api/announcements", json={
        "audience": "school", "title": "Hello school", "body": "morning",
    }, headers=_h(admin))
    assert r.status_code == 201
    stu = _login(client, email="amira@t.local", password="password12")
    body = client.get("/api/notifications/mine", headers=_h(stu)).get_json()
    kinds = [n["kind"] for n in body["notifications"]]
    assert "announcement" in kinds
    assert body["unreadCount"] >= 1


def test_mark_read_zeroes_unread_count(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    client.post("/api/announcements", json={
        "audience": "school", "title": "Hi",
    }, headers=_h(admin))
    stu = _login(client, email="amira@t.local", password="password12")
    before = client.get("/api/notifications/mine", headers=_h(stu)).get_json()
    assert before["unreadCount"] >= 1
    r = client.post("/api/notifications/mark-read",
                    json={"all": True}, headers=_h(stu))
    assert r.status_code == 200
    assert r.get_json()["unreadCount"] == 0


def test_attendance_absent_notifies_student_and_parent(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    riv = _login(client, email="rivera@t.local", password="password12")
    client.put(f"/api/classes/{s['class_a']}/attendance", json={
        "date": _date.today().isoformat(),
        "marks": [{"studentId": s["amira_id"], "status": "absent"}],
    }, headers=_h(riv))
    stu = _login(client, email="amira@t.local", password="password12")
    par = _login(client, email="fatima@t.local", password="password12")
    n_stu = client.get("/api/notifications/mine", headers=_h(stu)).get_json()
    n_par = client.get("/api/notifications/mine", headers=_h(par)).get_json()
    assert any(n["kind"] == "attendance_marked" for n in n_stu["notifications"])
    assert any(n["kind"] == "attendance_marked" for n in n_par["notifications"])


# ---------------------------------------------------------------------------
# Direct messages
# ---------------------------------------------------------------------------
def test_parent_can_dm_teacher_who_reaches_their_child(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    par = _login(client, email="fatima@t.local", password="password12")
    r = client.post("/api/messages/threads", json={
        "recipientId": s["chen_id"],  # Chen teaches Math in Amira's class
        "subject": "Math homework help",
        "body": "Can you spare 10 minutes?",
    }, headers=_h(par))
    assert r.status_code == 201, r.data


def test_parent_cannot_dm_unrelated_teacher(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    # A totally unrelated teacher.
    _register(client, "outsider@t.local", role="instructor", name="Outsider")
    out_id = client.post("/api/auth/login", json={
        "email": "outsider@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    par = _login(client, email="fatima@t.local", password="password12")
    r = client.post("/api/messages/threads", json={
        "recipientId": out_id, "subject": "Hi", "body": "Should fail.",
    }, headers=_h(par))
    assert r.status_code == 403


def test_message_notifies_recipient_bell(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    par = _login(client, email="fatima@t.local", password="password12")
    client.post("/api/messages/threads", json={
        "recipientId": s["chen_id"], "subject": "Hi", "body": "First msg",
    }, headers=_h(par))
    chen = _login(client, email="chen@t.local", password="password12")
    n = client.get("/api/notifications/mine", headers=_h(chen)).get_json()
    assert any(x["kind"] == "message" for x in n["notifications"])


# ---------------------------------------------------------------------------
# Lesson comments
# ---------------------------------------------------------------------------
def test_student_can_post_comment_and_teacher_answer_notifies(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    r = client.post(f"/api/lessons/{s['lesson']['id']}/comments",
                    json={"body": "What does paragraph 2 mean?"},
                    headers=_h(stu))
    assert r.status_code == 201
    q_id = r.get_json()["id"]

    chen = _login(client, email="chen@t.local", password="password12")
    r = client.post(f"/api/lessons/{s['lesson']['id']}/comments", json={
        "body": "It means…", "parentCommentId": q_id,
    }, headers=_h(chen))
    assert r.status_code == 201

    # Amira should have a comment_reply notification.
    n = client.get("/api/notifications/mine", headers=_h(stu)).get_json()
    assert any(x["kind"] == "comment_reply" for x in n["notifications"])


def test_comment_depth_capped_at_one_level(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    r = client.post(f"/api/lessons/{s['lesson']['id']}/comments",
                    json={"body": "Q"}, headers=_h(stu))
    q_id = r.get_json()["id"]
    chen = _login(client, email="chen@t.local", password="password12")
    r = client.post(f"/api/lessons/{s['lesson']['id']}/comments", json={
        "body": "A1", "parentCommentId": q_id,
    }, headers=_h(chen))
    a_id = r.get_json()["id"]
    # Now try to reply-to-reply.
    r = client.post(f"/api/lessons/{s['lesson']['id']}/comments", json={
        "body": "A1.1", "parentCommentId": a_id,
    }, headers=_h(stu))
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Homework board
# ---------------------------------------------------------------------------
def test_homeroom_can_upsert_and_students_read_homework(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    riv = _login(client, email="rivera@t.local", password="password12")
    today = _date.today().isoformat()
    r = client.put(f"/api/classes/{s['class_a']}/homework/{today}", json={
        "title": "Read pages 12-15",
        "body": "Answer questions 1-4 in your notebook.",
    }, headers=_h(riv))
    assert r.status_code in (200, 201), r.data
    stu = _login(client, email="amira@t.local", password="password12")
    rows = client.get(f"/api/classes/{s['class_a']}/homework",
                      headers=_h(stu)).get_json()
    titles = [row["title"] for row in rows]
    assert "Read pages 12-15" in titles


def test_non_homeroom_cannot_write_homework(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    chen = _login(client, email="chen@t.local", password="password12")  # not homeroom
    today = _date.today().isoformat()
    r = client.put(f"/api/classes/{s['class_a']}/homework/{today}", json={
        "title": "Nope",
    }, headers=_h(chen))
    assert r.status_code == 403


def test_homework_post_notifies_students_and_parents(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    riv = _login(client, email="rivera@t.local", password="password12")
    today = _date.today().isoformat()
    client.put(f"/api/classes/{s['class_a']}/homework/{today}",
               json={"title": "Do stuff"}, headers=_h(riv))
    par = _login(client, email="fatima@t.local", password="password12")
    n = client.get("/api/notifications/mine", headers=_h(par)).get_json()
    kinds = [x["kind"] for x in n["notifications"]]
    assert "announcement" in kinds  # homework uses the announcement bucket
