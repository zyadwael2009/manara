"""At-risk flagging, grade history, and attendance patterns.

Originally Phase 22.
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
    """Grade 9, class 9-A (Rivera homeroom), Amira student."""
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
                    json={"title": "M1"}, headers=h)
    module = r.get_json()
    client.post(f"/api/modules/{module['id']}/lessons",
                json={"title": "L", "type": "text", "contentText": "x"},
                headers=h)
    client.post(f"/api/courses/{eng['id']}/publish", headers=h)
    _register(client, "amira@t.local", role="student", name="Amira")
    amira_id = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/users/{amira_id}/class", json={"classId": c9a}, headers=h)
    return {
        "class_a": c9a, "riv_id": riv_id, "amira_id": amira_id,
        "course": eng, "module": module,
    }


# ---------------------------------------------------------------------------
# At-risk
# ---------------------------------------------------------------------------
def test_at_risk_shape_for_fresh_student_is_empty(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    r = client.get(f"/api/classes/{s['class_a']}/at-risk", headers=_h(admin))
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body, list)
    amira = [row for row in body if row["studentId"] == s["amira_id"]][0]
    assert amira["atRisk"] is False
    assert amira["reasons"] == []


def test_at_risk_flags_low_attendance(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    riv = _login(client, email="rivera@t.local", password="password12")
    # Mark absent today → attendance % = 0 → below 80% threshold.
    client.put(f"/api/classes/{s['class_a']}/attendance", json={
        "date": _date.today().isoformat(),
        "marks": [{"studentId": s["amira_id"], "status": "absent"}],
    }, headers=_h(riv))
    r = client.get(f"/api/classes/{s['class_a']}/at-risk", headers=_h(admin))
    amira = [row for row in r.get_json() if row["studentId"] == s["amira_id"]][0]
    assert amira["atRisk"] is True
    assert "low_attendance" in amira["reasons"]


def test_at_risk_needs_admin_or_homeroom(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    # A random other teacher — should 403.
    _register(client, "other@t.local", role="instructor", name="Other")
    other = _login(client, email="other@t.local", password="password12")
    r = client.get(f"/api/classes/{s['class_a']}/at-risk", headers=_h(other))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Grade history
# ---------------------------------------------------------------------------
def test_grade_history_starts_empty(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    r = client.get("/api/students/mine/grade-history", headers=_h(stu))
    assert r.status_code == 200
    body = r.get_json()
    # No grade entries written yet → the writer wasn't triggered → empty.
    assert body["series"] == []


def test_grade_history_point_appended_when_cache_recomputes(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    h = _h(admin)
    # Term + rubric + grading scale so the cache actually populates.
    r = client.post("/api/school-years",
                    json={"name": "Y", "isCurrent": True}, headers=h)
    year = r.get_json()["id"]
    r = client.post(f"/api/school-years/{year}/terms",
                    json={"name": "Q1", "orderIndex": 0}, headers=h)
    q1 = r.get_json()["id"]
    r = client.post("/api/grade-categories",
                    json={"name": "Final", "slug": "final_exam"}, headers=h)
    final_cat = r.get_json()
    for mn, mx, letter, gpa in [(60, 100, "A", 4.0), (0, 59, "F", 0.0)]:
        client.post("/api/grading-scale", json={
            "minPercent": mn, "maxPercent": mx, "letter": letter, "gpaValue": gpa,
        }, headers=h)
    client.put(f"/api/courses/{s['course']['id']}/rubric", json={
        "items": [
            {"gradeCategoryId": final_cat["id"], "maxScore": 100, "orderIndex": 0},
        ],
    }, headers=h)
    # Write a grade entry → cache recompute → history point appended.
    from models import Enrollment
    e = Enrollment.query.filter_by(
        student_id=s["amira_id"], course_id=s["course"]["id"],
    ).first()
    client.put(f"/api/enrollments/{e.id}/grades", json={
        "termId": q1,
        "entries": [
            {"gradeCategoryId": final_cat["id"], "score": 87.5},
        ],
    }, headers=h)

    stu = _login(client, email="amira@t.local", password="password12")
    body = client.get("/api/students/mine/grade-history",
                      headers=_h(stu)).get_json()
    assert body["series"], "expected at least one course series"
    pts = body["series"][0]["points"]
    assert len(pts) >= 1
    assert pts[0]["percent"] == 87.5


# ---------------------------------------------------------------------------
# Attendance patterns
# ---------------------------------------------------------------------------
def test_patterns_admin_only(client):
    admin = _login_admin(client)
    _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    r = client.get("/api/attendance/patterns", headers=_h(stu))
    assert r.status_code in (401, 403)
    r = client.get("/api/attendance/patterns", headers=_h(admin))
    assert r.status_code == 200


def test_patterns_reports_chronic_absentees_and_classes(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    riv = _login(client, email="rivera@t.local", password="password12")
    # Mark Amira absent → she's the only student → 0% class attendance,
    # and she should appear as a chronic absentee.
    client.put(f"/api/classes/{s['class_a']}/attendance", json={
        "date": _date.today().isoformat(),
        "marks": [{"studentId": s["amira_id"], "status": "absent"}],
    }, headers=_h(riv))
    body = client.get("/api/attendance/patterns", headers=_h(admin)).get_json()
    names = [r["name"] for r in body["chronicAbsentees"]]
    assert "Amira" in names
    class_names = [r["name"] for r in body["classes"]]
    assert "9-A" in class_names
