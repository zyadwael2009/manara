"""Weekly class timetables and per-date overrides.

Read: any class stakeholder can GET.
Write: admin-only PUT / POST / DELETE.
Business rules: overlap → 409, missing periodId on canceled → 400.
Now/Next: returns the right period given a clock time; overrides apply.

Originally Phase 13.
"""
from __future__ import annotations

from tests.conftest import register_user as _register

from datetime import date as _date, datetime, time as _time, timedelta as _td

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
    """9-A (Rivera homeroom, Chen teaches Math) + 9-B (control) + Amira."""
    h = _h(admin_tok)
    r = client.post("/api/sections", json={"name": "High"}, headers=h)
    section_id = r.get_json()["id"]
    r = client.post("/api/grades",
                    json={"name": "Grade 9", "sectionId": section_id, "orderIndex": 9},
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
    r = client.post("/api/classes", json={"name": "9-B", "gradeId": g9}, headers=h)
    c9b = r.get_json()["id"]
    r = client.post("/api/courses",
                    json={"title": "Math", "gradeId": g9, "category": "math"},
                    headers=h)
    math = r.get_json()
    r = client.post(f"/api/courses/{math['id']}/modules",
                    json={"title": "M1"}, headers=h)
    module = r.get_json()
    client.post(f"/api/modules/{module['id']}/lessons",
                json={"title": "L1", "type": "text", "contentText": "x"},
                headers=h)
    client.post(f"/api/courses/{math['id']}/publish", headers=h)
    client.put(f"/api/classes/{c9a}/courses/{math['id']}/teacher",
               json={"teacherId": riv_id}, headers=h)
    _register(client, "amira@t.local", role="student", name="Amira")
    amira_id = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/users/{amira_id}/class", json={"classId": c9a}, headers=h)
    return {
        "class_a": c9a, "class_b": c9b,
        "riv_id": riv_id, "amira_id": amira_id,
        "course": math, "grade": g9,
    }


# ============================================================================
# Read scope
# ============================================================================
def test_student_in_class_can_read_timetable(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    stu_tok = _login(client, email="amira@t.local", password="password12")
    r = client.get(f"/api/classes/{a['class_a']}/timetable", headers=_h(stu_tok))
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body["classId"] == a["class_a"]
    assert body["periods"] == []  # empty until admin PUTs periods.


def test_random_student_cannot_read_other_class_timetable(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    stu_tok = _login(client, email="amira@t.local", password="password12")
    # 9-B is a class Amira is not in.
    r = client.get(f"/api/classes/{a['class_b']}/timetable", headers=_h(stu_tok))
    assert r.status_code == 403


def test_admin_can_read_any_class_timetable(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    r = client.get(f"/api/classes/{a['class_b']}/timetable", headers=_h(admin_tok))
    assert r.status_code == 200


# ============================================================================
# Write scope
# ============================================================================
def _period(course_id, day, start, end, room=None):
    return {
        "courseId": course_id, "dayOfWeek": day,
        "startTime": start, "endTime": end,
        "room": room,
    }


def test_admin_can_put_periods(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    r = client.put(f"/api/classes/{a['class_a']}/timetable/periods", json={
        "periods": [
            _period(a["course"]["id"], 0, "09:00", "09:45", "12"),
            _period(a["course"]["id"], 1, "10:00", "10:45", "12"),
        ],
    }, headers=_h(admin_tok))
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert len(body["periods"]) == 2


def test_non_admin_cannot_put_periods(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    riv_tok = _login(client, email="rivera@t.local", password="password12")
    r = client.put(f"/api/classes/{a['class_a']}/timetable/periods", json={
        "periods": [_period(a["course"]["id"], 0, "09:00", "09:45")],
    }, headers=_h(riv_tok))
    assert r.status_code == 403


def test_overlapping_periods_return_409(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    r = client.put(f"/api/classes/{a['class_a']}/timetable/periods", json={
        "periods": [
            _period(a["course"]["id"], 0, "09:00", "09:45"),
            _period(a["course"]["id"], 0, "09:00", "09:45"),  # duplicate slot
        ],
    }, headers=_h(admin_tok))
    assert r.status_code == 409


def test_end_before_start_returns_400(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    r = client.put(f"/api/classes/{a['class_a']}/timetable/periods", json={
        "periods": [_period(a["course"]["id"], 0, "10:00", "09:00")],
    }, headers=_h(admin_tok))
    assert r.status_code == 400


# ============================================================================
# Overrides
# ============================================================================
def test_admin_can_add_and_delete_custom_override(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    tomorrow = (_date.today() + _td(days=1)).isoformat()
    r = client.post(f"/api/classes/{a['class_a']}/timetable/overrides", json={
        "date": tomorrow,
        "kind": "custom",
        "startTime": "09:00",
        "endTime": "10:00",
        "room": "Auditorium",
        "note": "Assembly",
    }, headers=_h(admin_tok))
    assert r.status_code == 201, r.data
    ov = r.get_json()

    # Round-trip via GET.
    r = client.get(f"/api/classes/{a['class_a']}/timetable", headers=_h(admin_tok))
    body = r.get_json()
    assert any(o["id"] == ov["id"] for o in body["overridesInWindow"])

    # Delete.
    r = client.delete(f"/api/timetable/overrides/{ov['id']}", headers=_h(admin_tok))
    assert r.status_code == 200
    r = client.get(f"/api/classes/{a['class_a']}/timetable", headers=_h(admin_tok))
    body = r.get_json()
    assert not any(o["id"] == ov["id"] for o in body["overridesInWindow"])


def test_canceled_override_requires_period_id(client):
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    tomorrow = (_date.today() + _td(days=1)).isoformat()
    r = client.post(f"/api/classes/{a['class_a']}/timetable/overrides", json={
        "date": tomorrow, "kind": "canceled",
    }, headers=_h(admin_tok))
    assert r.status_code == 400
    assert "period" in r.get_json()["error"].lower()


# ============================================================================
# Now/Next
# ============================================================================
def test_now_next_returns_current_period(client):
    """Set up a period 09:00-09:45 on today's weekday, hit compute_now_next
    at 09:30 → returns the period as 'now' and no next (single-period week)."""
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    dow = _date.today().weekday()
    # Skip on weekends — this test only runs Mon-Fri (0-4). Emit a period
    # on today's weekday if it's a school day; otherwise seed both Mon+Tue
    # so at least one is "today or later".
    if dow > 4:
        pytest.skip("Runs Mon-Fri only.")
    client.put(f"/api/classes/{a['class_a']}/timetable/periods", json={
        "periods": [
            _period(a["course"]["id"], dow, "09:00", "09:45", "12"),
            _period(a["course"]["id"], dow, "10:00", "10:45", "12"),
        ],
    }, headers=_h(admin_tok))

    from utils.timetables import compute_now_next
    from models import User
    with client.application.app_context():
        amira = User.query.filter_by(email="amira@t.local").first()
        # 09:30 today
        now = datetime.combine(_date.today(), _time(9, 30))
        out = compute_now_next(amira, now=now)
    assert out["now"] is not None
    assert out["now"]["period"]["startTime"] == "09:00"
    assert out["next"] is not None
    assert out["next"]["period"]["startTime"] == "10:00"


def test_custom_override_appears_in_now_next(client):
    """When a custom override sits on today at the query time, it wins."""
    admin_tok = _login_admin(client)
    a = _scaffold(client, admin_tok)
    dow = _date.today().weekday()
    if dow > 4:
        pytest.skip("Runs Mon-Fri only.")
    # Base period: Math 09:00-09:45.
    client.put(f"/api/classes/{a['class_a']}/timetable/periods", json={
        "periods": [_period(a["course"]["id"], dow, "09:00", "09:45", "12")],
    }, headers=_h(admin_tok))
    # Custom override on today: 09:00-10:00 assembly.
    client.post(f"/api/classes/{a['class_a']}/timetable/overrides", json={
        "date": _date.today().isoformat(),
        "kind": "custom",
        "startTime": "09:00",
        "endTime": "10:00",
        "note": "Assembly",
    }, headers=_h(admin_tok))

    from utils.timetables import compute_now_next
    from models import User
    with client.application.app_context():
        amira = User.query.filter_by(email="amira@t.local").first()
        now = datetime.combine(_date.today(), _time(9, 30))
        out = compute_now_next(amira, now=now)
    assert out["now"] is not None
    # The override + base period both cover 09:30; the override's note
    # should surface because we sort by start_time and both start at 09:00
    # but override entries carry `isOverride: true`.
    all_at_930 = [out["now"]["period"]]
    assert any(p.get("note") == "Assembly" or p.get("isOverride")
               for p in all_at_930), (
        f"expected assembly override in now-slot, got: {out['now']}"
    )
