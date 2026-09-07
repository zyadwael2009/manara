"""Query-count budgets for the bulk endpoints.

An N+1 is invisible in a passing test suite: the endpoint returns the right
answer, just after several hundred round trips instead of a dozen. These
tests count the SQL actually issued, so a regression shows up as a failure
rather than as a slow admin screen nobody can explain.

The budgets are deliberately loose — they exist to catch "this now scales
with the number of students", not to freeze the exact query plan.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import event

from tests.conftest import register_user as _register


def _h(tok):
    return {"X-Session-Token": tok}


def _login_admin(client):
    return client.post(
        "/api/auth/login", json={"email": "admin@t.local", "password": "adminpass1"},
    ).get_json()["sessionToken"]


@contextmanager
def count_queries(app):
    """Count statements executed on the app's engine inside the block."""
    from models import db

    counter = {"n": 0}

    with app.app_context():
        engine = db.engine

    def _before(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def _scaffold_two_grades(client, admin_tok, *, student_count):
    """Grade 9 (with a class) -> Grade 10 (with a class), a shared mandatory
    course in each, and `student_count` students placed in the 9th-grade
    class."""
    h = _h(admin_tok)
    section = client.post("/api/sections", json={"name": "Upper"}, headers=h).get_json()

    grades = {}
    classes = {}
    # Promotion only allows a move to the *next* grade, which is decided by
    # `orderIndex`, not by the name.
    for name, order in (("G9", 9), ("G10", 10)):
        grade = client.post(
            "/api/grades",
            json={"name": name, "sectionId": section["id"], "orderIndex": order},
            headers=h,
        ).get_json()
        grades[name] = grade
        classes[name] = client.post(
            "/api/classes", json={"name": f"{name}-A", "gradeId": grade["id"]}, headers=h,
        ).get_json()
        # Three mandatory courses per grade, so auto-enrolment has real work.
        for subject in ("Math", "Science", "History"):
            course = client.post(
                "/api/courses",
                json={
                    "title": f"{subject} {name}",
                    "gradeId": grade["id"],
                    "category": subject.lower(),
                },
                headers=h,
            ).get_json()
            client.post(f"/api/courses/{course['id']}/publish", headers=h)

    for i in range(student_count):
        student = _register(
            client, email=f"s{i}@t.local", role="student", name=f"S{i}",
        ).get_json()["user"]
        client.put(
            f"/api/users/{student['id']}/class",
            json={"classId": classes["G9"]["id"]},
            headers=h,
        )

    return classes["G9"]["id"], classes["G10"]["id"]


@pytest.mark.parametrize("student_count", [2, 8])
def test_promote_class_query_count_does_not_scale_with_roster(
    app, client, student_count,
):
    """The promotion loop used to run ~5 queries per student plus one per
    mandatory course per student. Prefetching makes the cost flat."""
    admin_tok = _login_admin(client)
    src_id, dst_id = _scaffold_two_grades(
        client, admin_tok, student_count=student_count,
    )

    with count_queries(app) as counter:
        r = client.post(
            f"/api/classes/{src_id}/promote",
            json={"toClassId": dst_id},
            headers=_h(admin_tok),
        )
    assert r.status_code == 200, r.data
    assert r.get_json()["promoted"] == student_count

    # Measured against the pre-fix code: 36 queries for 2 students, 120 for
    # 8, 428 for 30. Batched it is 15 for all three.
    assert counter["n"] < 30, (
        f"{counter['n']} queries to promote {student_count} students — "
        "the prefetch in routes/classes.py::promote_class has regressed"
    )


def test_promotion_still_carries_electives_and_swaps_mandatory(client):
    """The batched rewrite must not change what promotion actually does."""
    admin_tok = _login_admin(client)
    h = _h(admin_tok)
    section = client.post("/api/sections", json={"name": "Upper"}, headers=h).get_json()

    g9 = client.post(
        "/api/grades",
        json={"name": "G9", "sectionId": section["id"], "orderIndex": 9},
        headers=h,
    ).get_json()
    g10 = client.post(
        "/api/grades",
        json={"name": "G10", "sectionId": section["id"], "orderIndex": 10},
        headers=h,
    ).get_json()
    c9 = client.post(
        "/api/classes", json={"name": "9-A", "gradeId": g9["id"]}, headers=h,
    ).get_json()
    c10 = client.post(
        "/api/classes", json={"name": "10-A", "gradeId": g10["id"]}, headers=h,
    ).get_json()

    math9 = client.post(
        "/api/courses",
        json={"title": "Math 9", "gradeId": g9["id"], "category": "math"},
        headers=h,
    ).get_json()
    art9 = client.post(
        "/api/courses",
        json={
            "title": "Art 9",
            "gradeId": g9["id"],
            "category": "arts",
            "electiveGroup": "creative",
        },
        headers=h,
    ).get_json()
    math10 = client.post(
        "/api/courses",
        json={"title": "Math 10", "gradeId": g10["id"], "category": "math"},
        headers=h,
    ).get_json()
    art10 = client.post(
        "/api/courses",
        json={
            "title": "Art 10",
            "gradeId": g10["id"],
            "category": "arts",
            "electiveGroup": "creative",
            "succeedsCourseId": art9["id"],
        },
        headers=h,
    ).get_json()
    for course in (math9, art9, math10, art10):
        client.post(f"/api/courses/{course['id']}/publish", headers=h)

    student = _register(client, email="amira@t.local", role="student").get_json()
    student_id = student["user"]["id"]
    client.put(
        f"/api/users/{student_id}/class", json={"classId": c9["id"]}, headers=h,
    )
    # Pick the Grade 9 elective.
    picked = client.put(
        f"/api/users/{student_id}/electives/creative",
        json={"courseId": art9["id"]},
        headers=h,
    )
    assert picked.status_code in (200, 201), picked.data

    r = client.post(
        f"/api/classes/{c9['id']}/promote",
        json={"toClassId": c10["id"]},
        headers=h,
    )
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body["promoted"] == 1
    assert body["carriedForwardElectives"] == 1, (
        "the Grade 10 successor elective was not carried"
    )

    enrollments = client.get(
        f"/api/users/{student_id}/enrollments", headers=h,
    ).get_json()
    active = {
        e["course"]["title"] for e in enrollments if e["status"] == "active"
    }
    assert active == {"Math 10", "Art 10"}, active


# =============================================================================
# Dashboards
# =============================================================================
def _scaffold_taught_course(client, admin_tok, *, student_count, module_count=3):
    """One course with `module_count` modules of two lessons each, taught by
    one instructor, with `student_count` students enrolled."""
    h = _h(admin_tok)
    section = client.post("/api/sections", json={"name": "Upper"}, headers=h).get_json()
    grade = client.post(
        "/api/grades",
        json={"name": "G9", "sectionId": section["id"], "orderIndex": 9},
        headers=h,
    ).get_json()
    klass = client.post(
        "/api/classes", json={"name": "9-A", "gradeId": grade["id"]}, headers=h,
    ).get_json()
    course = client.post(
        "/api/courses",
        json={"title": "Math", "gradeId": grade["id"], "category": "math"},
        headers=h,
    ).get_json()
    for m in range(module_count):
        module = client.post(
            f"/api/courses/{course['id']}/modules",
            json={"title": f"M{m}"},
            headers=h,
        ).get_json()
        for lesson in range(2):
            client.post(
                f"/api/modules/{module['id']}/lessons",
                json={"title": f"L{m}-{lesson}", "type": "text", "contentText": "x"},
                headers=h,
            )
    client.post(f"/api/courses/{course['id']}/publish", headers=h)

    teacher = _register(client, email="rivera@t.local", role="instructor").get_json()
    client.put(
        f"/api/classes/{klass['id']}/courses/{course['id']}/teacher",
        json={"teacherId": teacher["user"]["id"]},
        headers=h,
    )

    for i in range(student_count):
        student = _register(
            client, email=f"s{i}@t.local", role="student", name=f"S{i}",
        ).get_json()["user"]
        client.put(
            f"/api/users/{student['id']}/class",
            json={"classId": klass["id"]},
            headers=h,
        )

    return course["id"], teacher["sessionToken"]


@pytest.mark.parametrize("student_count", [2, 10])
def test_instructor_dashboard_query_count_is_flat(app, client, student_count):
    """`instructor_course_rows` lazy-loaded `enrollment.student` one row at a
    time purely to read `class_id`."""
    admin_tok = _login_admin(client)
    _, teacher_tok = _scaffold_taught_course(
        client, admin_tok, student_count=student_count,
    )

    with count_queries(app) as counter:
        r = client.get("/api/dashboard/instructor", headers=_h(teacher_tok))
    assert r.status_code == 200, r.data

    assert counter["n"] < 25, (
        f"{counter['n']} queries for {student_count} students — "
        "the prefetch in utils/analytics.py::instructor_course_rows has regressed"
    )


@pytest.mark.parametrize("student_count", [2, 10])
def test_course_drilldown_query_count_is_flat(app, client, student_count):
    """The per-module completion loop ran a COUNT per (module x enrollment)."""
    admin_tok = _login_admin(client)
    course_id, teacher_tok = _scaffold_taught_course(
        client, admin_tok, student_count=student_count, module_count=4,
    )

    with count_queries(app) as counter:
        r = client.get(f"/api/dashboard/instructor/courses/{course_id}", headers=_h(teacher_tok))
    assert r.status_code == 200, r.data

    # 4 modules x 10 students would have been 40+ COUNTs alone.
    assert counter["n"] < 30, (
        f"{counter['n']} queries for {student_count} students across 4 modules — "
        "the prefetch in utils/analytics.py::course_drilldown has regressed"
    )
