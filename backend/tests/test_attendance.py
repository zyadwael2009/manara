"""Daily attendance marking and its roll-up into Commitment.

Positive:
  * Rivera (homeroom of 9-A) can mark + read today's attendance.
  * Admin can mark any class, any date.
  * Parent + student can read their own / linked child's history.
  * Attendance rollup writes the expected Commitment grade entry.
  * Rollup triggers cert issuance when it opens the gate.

Trust-core negatives:
  * Chen (course teacher of 9-A, NOT homeroom) → 403 on write.
  * Rivera cannot backdate — same-day only for non-admin.
  * Rivera cannot mark 9-B's students (not her homeroom).
  * Student cannot mark their own attendance.
  * Parent cannot mark linked child's attendance.

Originally Phase 12.
"""
from __future__ import annotations

from tests.conftest import register_user as _register

from datetime import date as _date, timedelta as _td


def _h(tok):
    return {"X-Session-Token": tok}


def _login(client, *, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.data
    return r.get_json()["sessionToken"]


def _login_admin(client):
    return _login(client, email="admin@t.local", password="adminpass1")


def _scaffold(client, admin_tok):
    """9-A (homeroom Rivera) with 2 students + Math course taught by Chen."""
    h = _h(admin_tok)
    r = client.post("/api/sections", json={"name": "High"}, headers=h)
    high = r.get_json()["id"]
    r = client.post("/api/grades",
                    json={"name": "Grade 9", "sectionId": high, "orderIndex": 9},
                    headers=h)
    g9 = r.get_json()["id"]
    # Rivera → homeroom 9-A.
    _register(client, "rivera@t.local", role="instructor", name="Rivera")
    riv_id = client.post("/api/auth/login", json={
        "email": "rivera@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    r = client.post("/api/classes",
                    json={"name": "9-A", "gradeId": g9, "homeroomTeacherId": riv_id},
                    headers=h)
    c9a = r.get_json()["id"]
    # 9-B homeroom Chen (control class).
    _register(client, "chen@t.local", role="instructor", name="Chen")
    chen_id = client.post("/api/auth/login", json={
        "email": "chen@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    r = client.post("/api/classes",
                    json={"name": "9-B", "gradeId": g9, "homeroomTeacherId": chen_id},
                    headers=h)
    c9b = r.get_json()["id"]
    # Math course, published, both classes.
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
    # Chen teaches Math in 9-A.
    client.put(f"/api/classes/{c9a}/courses/{math['id']}/teacher",
               json={"teacherId": chen_id}, headers=h)
    # Students.
    _register(client, "amira@t.local", role="student", name="Amira")
    amira_id = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    _register(client, "bilal@t.local", role="student", name="Bilal")
    bilal_id = client.post("/api/auth/login", json={
        "email": "bilal@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/users/{amira_id}/class", json={"classId": c9a}, headers=h)
    client.put(f"/api/users/{bilal_id}/class", json={"classId": c9a}, headers=h)
    # Rubric + grading scale + Q1 (for the rollup tests).
    r = client.post("/api/grade-categories", json={"name": "Commitment", "slug": "commitment"}, headers=h)
    commitment = r.get_json()
    r = client.post("/api/grade-categories", json={"name": "Final", "slug": "final_exam"}, headers=h)
    final = r.get_json()
    for mn, mx, letter, gpa in [(60, 100, "A", 4.0), (0, 59, "F", 0.0)]:
        client.post("/api/grading-scale", json={
            "minPercent": mn, "maxPercent": mx, "letter": letter, "gpaValue": gpa,
        }, headers=h)
    client.put(f"/api/courses/{math['id']}/rubric", json={
        "items": [
            {"gradeCategoryId": commitment["id"], "maxScore": 20, "orderIndex": 0},
            {"gradeCategoryId": final["id"], "maxScore": 80, "orderIndex": 1},
        ],
    }, headers=h)
    r = client.post("/api/school-years", json={"name": "Y", "isCurrent": True}, headers=h)
    year = r.get_json()["id"]
    r = client.post(f"/api/school-years/{year}/terms",
                    json={"name": "Q1", "orderIndex": 0}, headers=h)
    q1 = r.get_json()["id"]
    return {
        "class_a": c9a, "class_b": c9b, "riv_id": riv_id, "chen_id": chen_id,
        "amira_id": amira_id, "bilal_id": bilal_id,
        "course": math, "commitment": commitment, "final": final, "q1": q1,
    }


def _today() -> str:
    return _date.today().isoformat()


# ============================================================================
# Positive
# ============================================================================
def test_homeroom_can_mark_today_attendance(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    riv_tok = _login(client, email="rivera@t.local", password="password12")
    r = client.put(f"/api/classes/{a['class_a']}/attendance", json={
        "date": _today(),
        "marks": [
            {"studentId": a["amira_id"], "status": "present"},
            {"studentId": a["bilal_id"], "status": "absent"},
        ],
    }, headers=_h(riv_tok))
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body["marksWritten"] == 2


def test_homeroom_can_read_today_class_attendance(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    riv_tok = _login(client, email="rivera@t.local", password="password12")
    # Mark first.
    client.put(f"/api/classes/{a['class_a']}/attendance", json={
        "date": _today(),
        "marks": [{"studentId": a["amira_id"], "status": "present"}],
    }, headers=_h(riv_tok))
    r = client.get(f"/api/classes/{a['class_a']}/attendance", headers=_h(riv_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert body["date"] == _today()
    assert body["canWrite"] is True
    assert body["isToday"] is True
    assert len(body["rows"]) == 2  # Amira + Bilal


def test_admin_can_backdate_attendance(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    past = (_date.today() - _td(days=5)).isoformat()
    r = client.put(f"/api/classes/{a['class_a']}/attendance", json={
        "date": past,
        "marks": [{"studentId": a["amira_id"], "status": "excused",
                   "reason": "Doctor"}],
    }, headers=_h(admin_tok))
    assert r.status_code == 200, r.data


def test_parent_can_read_child_attendance(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    # Create parent + link to Amira.
    r = client.post("/api/users", json={
        "name": "P", "email": "p@t.local", "password": "parent12", "role": "parent",
    }, headers=_h(admin_tok))
    p_id = r.get_json()["id"]
    client.post(f"/api/users/{a['amira_id']}/parents",
                json={"parentId": p_id}, headers=_h(admin_tok))
    # Rivera marks Amira absent today.
    riv_tok = _login(client, email="rivera@t.local", password="password12")
    client.put(f"/api/classes/{a['class_a']}/attendance", json={
        "date": _today(),
        "marks": [{"studentId": a["amira_id"], "status": "absent"}],
    }, headers=_h(riv_tok))
    # Parent reads.
    p_tok = _login(client, email="p@t.local", password="parent12")
    r = client.get(f"/api/parents/mine/children/{a['amira_id']}/attendance",
                   headers=_h(p_tok))
    assert r.status_code == 200
    rows = r.get_json()
    assert len(rows) == 1 and rows[0]["status"] == "absent"
    # Parent home also reports today's status on the child card.
    r = client.get("/api/parents/mine/children", headers=_h(p_tok))
    kids = r.get_json()
    assert kids[0]["todayAttendanceStatus"] == "absent"


def test_student_can_read_own_attendance(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    riv_tok = _login(client, email="rivera@t.local", password="password12")
    client.put(f"/api/classes/{a['class_a']}/attendance", json={
        "date": _today(),
        "marks": [{"studentId": a["amira_id"], "status": "late",
                   "reason": "Bus late"}],
    }, headers=_h(riv_tok))
    stu_tok = _login(client, email="amira@t.local", password="password12")
    r = client.get("/api/attendance/mine", headers=_h(stu_tok))
    assert r.status_code == 200
    rows = r.get_json()
    assert len(rows) == 1
    assert rows[0]["status"] == "late" and rows[0]["reason"] == "Bus late"


# ============================================================================
# Rollup
# ============================================================================
def test_attendance_rolls_up_to_commitment(client):
    """Mark Amira present 8 out of 10 days → Commitment score should be
    0.8 × 20 = 16.0."""
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    riv_tok = _login(client, email="rivera@t.local", password="password12")

    # Admin backdates 10 days: 8 present, 2 absent.
    for i in range(10):
        day = (_date.today() - _td(days=i)).isoformat()
        status = "present" if i >= 2 else "absent"
        r = client.put(f"/api/classes/{a['class_a']}/attendance", json={
            "date": day,
            "marks": [{"studentId": a["amira_id"], "status": status}],
        }, headers=_h(admin_tok))
        assert r.status_code == 200, (day, r.data)

    # Read Amira's Math enrollment gradebook — Commitment score should be 16.
    r = client.get(f"/api/classes/{a['class_a']}/gradebook",
                   query_string={"courseId": a["course"]["id"], "termId": a["q1"]},
                   headers=_h(admin_tok))
    assert r.status_code == 200, r.data
    body = r.get_json()
    amira_row = next(s for s in body["students"] if s["studentId"] == a["amira_id"])
    # `entries` is a {gradeCategoryId: score} dict.
    commitment_score = amira_row["entries"].get(a["commitment"]["id"])
    assert commitment_score == 16.0, (
        f"expected 16.0 (0.8 × 20), got {commitment_score}"
    )


# ============================================================================
# Negative — trust core
# ============================================================================
def test_course_teacher_not_homeroom_cannot_mark(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    # Chen teaches Math in 9-A but does NOT homeroom 9-A (Rivera does).
    chen_tok = _login(client, email="chen@t.local", password="password12")
    r = client.put(f"/api/classes/{a['class_a']}/attendance", json={
        "date": _today(),
        "marks": [{"studentId": a["amira_id"], "status": "absent"}],
    }, headers=_h(chen_tok))
    assert r.status_code == 403


def test_homeroom_cannot_backdate(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    riv_tok = _login(client, email="rivera@t.local", password="password12")
    past = (_date.today() - _td(days=3)).isoformat()
    r = client.put(f"/api/classes/{a['class_a']}/attendance", json={
        "date": past,
        "marks": [{"studentId": a["amira_id"], "status": "absent"}],
    }, headers=_h(riv_tok))
    assert r.status_code == 403


def test_homeroom_of_A_cannot_mark_B(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    riv_tok = _login(client, email="rivera@t.local", password="password12")
    r = client.put(f"/api/classes/{a['class_b']}/attendance", json={
        "date": _today(),
        "marks": [],
    }, headers=_h(riv_tok))
    assert r.status_code == 403


def test_student_cannot_mark_attendance(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    stu_tok = _login(client, email="amira@t.local", password="password12")
    r = client.put(f"/api/classes/{a['class_a']}/attendance", json={
        "date": _today(),
        "marks": [{"studentId": a["amira_id"], "status": "present"}],
    }, headers=_h(stu_tok))
    assert r.status_code == 403


def test_parent_cannot_mark_attendance(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    r = client.post("/api/users", json={
        "name": "P", "email": "p@t.local", "password": "parent12", "role": "parent",
    }, headers=_h(admin_tok))
    p_id = r.get_json()["id"]
    client.post(f"/api/users/{a['amira_id']}/parents",
                json={"parentId": p_id}, headers=_h(admin_tok))
    p_tok = _login(client, email="p@t.local", password="parent12")
    r = client.put(f"/api/classes/{a['class_a']}/attendance", json={
        "date": _today(),
        "marks": [{"studentId": a["amira_id"], "status": "present"}],
    }, headers=_h(p_tok))
    assert r.status_code == 403


def test_marks_restricted_to_class_roster(client):
    """Even the homeroom can't write a mark for a student not in her class."""
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    # Register a student who's NOT placed in 9-A.
    _register(client, "outsider@t.local", role="student")
    outsider_id = client.post("/api/auth/login", json={
        "email": "outsider@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    riv_tok = _login(client, email="rivera@t.local", password="password12")
    r = client.put(f"/api/classes/{a['class_a']}/attendance", json={
        "date": _today(),
        "marks": [{"studentId": outsider_id, "status": "present"}],
    }, headers=_h(riv_tok))
    assert r.status_code == 400
    assert "not in this class" in r.get_json()["error"].lower()
