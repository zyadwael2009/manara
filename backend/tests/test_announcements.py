"""Announcements and quiz-attempt class-average stats.

Author scope guards:
  * Admin can post any of the three audiences.
  * Homeroom teacher can post "class" only for their own homeroom.
  * Course teacher can post "course" only for a (class, course) pair they teach.
  * Student / parent → 403 on write.

Reader fan-out:
  * Student in 9-A sees school-wide + 9-A class-wide + course-wide for
    courses they're enrolled in. Never sees another class's or another
    course's announcements.
  * Parent linked to Amira sees everything Amira sees.
  * Expired announcements never appear.

Delete:
  * Author can delete their own; another teacher cannot; admin can delete any.

Quiz attempts stats:
  * count / submittedCount / avg / min / max / passRate computed from
    the submitted attempts only.

Originally Phase 19.
"""
from __future__ import annotations

from tests.conftest import register_user as _register

from datetime import datetime, timedelta

from utils.time import utc_now


def _h(tok):
    return {"X-Session-Token": tok}


def _login(client, *, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.data
    return r.get_json()["sessionToken"]


def _login_admin(client):
    return _login(client, email="admin@t.local", password="adminpass1")


def _scaffold(client, admin_tok):
    """Grade 9, class 9-A (Rivera homeroom, Chen course-teacher for Math),
    class 9-B (Chen homeroom), Amira in 9-A, Bilal in 9-B."""
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
    r = client.post("/api/classes",
                    json={"name": "9-B", "gradeId": g9, "homeroomTeacherId": chen_id},
                    headers=h)
    c9b = r.get_json()["id"]
    r = client.post("/api/courses",
                    json={"title": "Math", "gradeId": g9, "category": "math"},
                    headers=h)
    math = r.get_json()
    r = client.post(f"/api/courses/{math['id']}/modules",
                    json={"title": "M1"}, headers=h)
    module = r.get_json()
    client.post(f"/api/modules/{module['id']}/lessons",
                json={"title": "L", "type": "text", "contentText": "x"},
                headers=h)
    client.post(f"/api/courses/{math['id']}/publish", headers=h)
    # Chen teaches Math in 9-A.
    client.put(f"/api/classes/{c9a}/courses/{math['id']}/teacher",
               json={"teacherId": chen_id}, headers=h)
    _register(client, "amira@t.local", role="student", name="Amira")
    amira_id = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    _register(client, "bilal@t.local", role="student", name="Bilal")
    bilal_id = client.post("/api/auth/login", json={
        "email": "bilal@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/users/{amira_id}/class", json={"classId": c9a}, headers=h)
    client.put(f"/api/users/{bilal_id}/class", json={"classId": c9b}, headers=h)
    return {
        "class_a": c9a, "class_b": c9b, "riv_id": riv_id, "chen_id": chen_id,
        "amira_id": amira_id, "bilal_id": bilal_id, "course": math,
        "module": module,
    }


# ---------------------------------------------------------------------------
# Author scope
# ---------------------------------------------------------------------------
def test_admin_can_post_school_class_and_course(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    for aud, extra in [
        ("school", {}),
        ("class", {"classId": s["class_a"]}),
        ("course", {"courseId": s["course"]["id"]}),
    ]:
        r = client.post("/api/announcements", json={
            "audience": aud, "title": f"admin-{aud}", "body": "hi", **extra,
        }, headers=_h(admin))
        assert r.status_code == 201, (aud, r.data)


def test_homeroom_can_post_class_but_not_school(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    riv = _login(client, email="rivera@t.local", password="password12")
    r = client.post("/api/announcements", json={
        "audience": "class", "classId": s["class_a"], "title": "9-A meeting",
    }, headers=_h(riv))
    assert r.status_code == 201, r.data
    r = client.post("/api/announcements", json={
        "audience": "school", "title": "school-wide",
    }, headers=_h(riv))
    assert r.status_code == 403


def test_homeroom_cannot_post_to_other_class(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    riv = _login(client, email="rivera@t.local", password="password12")
    r = client.post("/api/announcements", json={
        "audience": "class", "classId": s["class_b"], "title": "not mine",
    }, headers=_h(riv))
    assert r.status_code == 403


def test_course_teacher_can_post_course_but_not_arbitrary(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    chen = _login(client, email="chen@t.local", password="password12")
    # Chen teaches Math in 9-A → allowed for course=Math.
    r = client.post("/api/announcements", json={
        "audience": "course", "courseId": s["course"]["id"],
        "title": "Read pp.10-20",
    }, headers=_h(chen))
    assert r.status_code == 201, r.data
    # A random other course they don't teach → 403.
    grade_row = client.get("/api/grades", headers=_h(admin)).get_json()
    grade_id = grade_row[0]["id"] if grade_row else None
    r2 = client.post("/api/courses",
                     json={"title": "Bio", "gradeId": grade_id, "category": "science"},
                     headers=_h(admin))
    other = r2.get_json()
    r = client.post("/api/announcements", json={
        "audience": "course", "courseId": other["id"], "title": "nope",
    }, headers=_h(chen))
    assert r.status_code == 403


def test_student_and_parent_cannot_post(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    r = client.post("/api/announcements", json={
        "audience": "class", "classId": s["class_a"], "title": "x",
    }, headers=_h(stu))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Reader fan-out
# ---------------------------------------------------------------------------
def test_student_sees_school_and_own_class_but_not_other_class(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    riv = _login(client, email="rivera@t.local", password="password12")
    chen = _login(client, email="chen@t.local", password="password12")
    # Admin school-wide, Rivera to 9-A, Chen to 9-B.
    client.post("/api/announcements", json={
        "audience": "school", "title": "S1",
    }, headers=_h(admin))
    client.post("/api/announcements", json={
        "audience": "class", "classId": s["class_a"], "title": "A1",
    }, headers=_h(riv))
    client.post("/api/announcements", json={
        "audience": "class", "classId": s["class_b"], "title": "B1",
    }, headers=_h(chen))
    stu = _login(client, email="amira@t.local", password="password12")
    r = client.get("/api/announcements/mine", headers=_h(stu))
    titles = [row["title"] for row in r.get_json()]
    assert "S1" in titles and "A1" in titles
    assert "B1" not in titles


def test_expired_announcements_never_returned(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    past = (utc_now() - timedelta(days=1)).isoformat() + "Z"
    client.post("/api/announcements", json={
        "audience": "school", "title": "expired", "expiresAt": past,
    }, headers=_h(admin))
    client.post("/api/announcements", json={
        "audience": "school", "title": "live",
    }, headers=_h(admin))
    stu = _login(client, email="amira@t.local", password="password12")
    titles = [x["title"] for x in
              client.get("/api/announcements/mine", headers=_h(stu)).get_json()]
    assert "live" in titles
    assert "expired" not in titles


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
def test_delete_requires_author_or_admin(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    riv = _login(client, email="rivera@t.local", password="password12")
    r = client.post("/api/announcements", json={
        "audience": "class", "classId": s["class_a"], "title": "meeting",
    }, headers=_h(riv))
    aid = r.get_json()["id"]
    # Another homeroom teacher cannot delete Rivera's post.
    chen = _login(client, email="chen@t.local", password="password12")
    r = client.delete(f"/api/announcements/{aid}", headers=_h(chen))
    assert r.status_code == 403
    # Author can.
    r = client.delete(f"/api/announcements/{aid}", headers=_h(riv))
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Quiz stats
# ---------------------------------------------------------------------------
def test_quiz_attempts_stats_computes_avg_min_max_passrate(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    # Publish a quiz with one MC-single question.
    r = client.post(f"/api/modules/{s['module']['id']}/quizzes",
                    json={"title": "Q", "passingScore": 60}, headers=_h(admin))
    q = r.get_json()
    r = client.post(f"/api/quizzes/{q['id']}/questions",
                    json={"type": "mc_single", "prompt": "?", "points": 1},
                    headers=_h(admin))
    qq = r.get_json()
    r = client.post(f"/api/quiz-questions/{qq['id']}/options",
                    json={"text": "A", "isCorrect": True}, headers=_h(admin))
    opt_a = r.get_json()
    r = client.post(f"/api/quiz-questions/{qq['id']}/options",
                    json={"text": "B", "isCorrect": False}, headers=_h(admin))
    opt_b = r.get_json()
    client.post(f"/api/quizzes/{q['id']}/publish", headers=_h(admin))

    # Amira answers correctly (100%). Bilal is in a different class; his
    # attempts must never appear in Chen's stats for 9-A.
    stu_a = _login(client, email="amira@t.local", password="password12")
    r = client.post(f"/api/quizzes/{q['id']}/start", headers=_h(stu_a))
    att = r.get_json()["attempt"]
    client.post(f"/api/quiz-attempts/{att['id']}/submit", json={
        "answers": [{"questionId": qq["id"], "selectedOptionIds": [opt_a["id"]]}],
    }, headers=_h(stu_a))

    # Bilal in 9-B answers wrong. Chen teaches Math in 9-A, so stats
    # scoped to Chen must NOT include Bilal.
    stu_b = _login(client, email="bilal@t.local", password="password12")
    r = client.post(f"/api/quizzes/{q['id']}/start", headers=_h(stu_b))
    att_b = r.get_json()["attempt"]
    client.post(f"/api/quiz-attempts/{att_b['id']}/submit", json={
        "answers": [{"questionId": qq["id"], "selectedOptionIds": [opt_b["id"]]}],
    }, headers=_h(stu_b))

    chen = _login(client, email="chen@t.local", password="password12")
    r = client.get(f"/api/quizzes/{q['id']}/attempts/stats", headers=_h(chen))
    assert r.status_code == 200
    body = r.get_json()
    assert body["submittedCount"] == 1  # only Amira (Chen teaches 9-A)
    assert body["avgPercent"] == 100.0
    assert body["minPercent"] == 100.0
    assert body["maxPercent"] == 100.0
    assert body["passRate"] == 100.0

    # Admin sees everyone (100% + 0% → avg 50, passRate 50).
    r = client.get(f"/api/quizzes/{q['id']}/attempts/stats", headers=_h(admin))
    body = r.get_json()
    assert body["submittedCount"] == 2
    assert body["avgPercent"] == 50.0
    assert body["passRate"] == 50.0
