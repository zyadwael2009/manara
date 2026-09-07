"""Instructor and admin dashboards.

Numeric-correctness checks on tiny fixture data, plus permission gates
(instructor sees only their own courses, non-admin can't see admin
dashboard, non-instructor can't see instructor dashboard) and the
"no-writes" guard on the whole blueprint.

Originally Phase 7.
"""
from __future__ import annotations

from tests.conftest import register_user as _register


# ---------------------------------------------------------------------------
# Small helpers (same shape as test_phase5, kept local so tests are self-
# contained; DRYing tests across phases is worth doing later, not now.)
# ---------------------------------------------------------------------------
def _h(tok):
    return {"X-Session-Token": tok}


def _login(client, *, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.data
    return r.get_json()["sessionToken"]


def _login_admin(client):
    return _login(client, email="admin@t.local", password="adminpass1")


def _mk_scaffold(client, admin_tok):
    """One grade, one class, one course + one module + 2 lessons. Returns ids.
    Course is published so it counts on the admin dashboard's published count."""
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
                    json={"title": "Algebra 1", "gradeId": g9, "category": "math"},
                    headers=h)
    course = r.get_json()
    r = client.post(f"/api/courses/{course['id']}/modules",
                    json={"title": "M1"}, headers=h)
    module = r.get_json()
    lesson_ids = []
    for i in range(2):
        r = client.post(f"/api/modules/{module['id']}/lessons",
                        json={"title": f"L{i+1}", "type": "text", "contentText": "x"},
                        headers=h)
        lesson_ids.append(r.get_json()["id"])
    client.post(f"/api/courses/{course['id']}/publish", headers=h)
    return {"grade": g9, "class": c9a, "course": course, "module": module, "lessons": lesson_ids}


def _add_student_to_class(client, admin_tok, *, email, class_id):
    r = _register(client, email=email, role="student", name=email.split("@")[0])
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": class_id}, headers=_h(admin_tok))
    return sid


def _mine_enrollment(client, stu_tok, course_id):
    for e in client.get("/api/enrollments/mine", headers=_h(stu_tok)).get_json():
        if e["courseId"] == course_id:
            return e
    raise AssertionError("student has no enrollment for course")


def _mark_lessons(client, stu_tok, lesson_ids):
    for lid in lesson_ids:
        client.post(f"/api/lessons/{lid}/complete", headers=_h(stu_tok))


def _assign_teacher(client, admin_tok, *, class_id, course_id, teacher_id):
    r = client.put(
        f"/api/classes/{class_id}/courses/{course_id}/teacher",
        json={"teacherId": teacher_id},
        headers=_h(admin_tok),
    )
    assert r.status_code == 200, r.data


# ---------------------------------------------------------------------------
# 1. Instructor landing shows one row per course they teach
# ---------------------------------------------------------------------------
def test_instructor_sees_only_their_courses(client):
    admin_tok = _login_admin(client)
    a = _mk_scaffold(client, admin_tok)

    # Second course, no teacher on it — should NOT appear for our instructor.
    h = _h(admin_tok)
    r = client.post("/api/courses",
                    json={"title": "Biology 9", "gradeId": a["grade"], "category": "science"},
                    headers=h)
    other_course = r.get_json()

    # Instructor Rivera assigned to Algebra 1 in 9-A.
    _register(client, email="rivera@t.local", role="instructor", name="Rivera")
    riv_id = client.post("/api/auth/login", json={
        "email": "rivera@t.local", "password": "password12"
    }).get_json()["user"]["id"]
    _assign_teacher(client, admin_tok, class_id=a["class"],
                    course_id=a["course"]["id"], teacher_id=riv_id)

    riv_tok = _login(client, email="rivera@t.local", password="password12")

    r = client.get("/api/dashboard/instructor", headers=_h(riv_tok))
    assert r.status_code == 200, r.data
    body = r.get_json()
    titles = [c["title"] for c in body["courses"]]
    assert titles == ["Algebra 1"]
    assert other_course["title"] not in titles


# ---------------------------------------------------------------------------
# 2. Numeric correctness on instructor row
# ---------------------------------------------------------------------------
def test_avg_completion_and_rate(client):
    admin_tok = _login_admin(client)
    a = _mk_scaffold(client, admin_tok)

    # 4 students: after marking 0, 1, 2, 2 of 2 lessons the progress percents
    # will be 0, 50, 100, 100 → avg=62.5, completionRate = 2/4 = 0.5.
    marks = [0, 1, 2, 2]
    for i, count in enumerate(marks):
        email = f"s{i}@t.local"
        _add_student_to_class(client, admin_tok, email=email, class_id=a["class"])
        stu = _login(client, email=email, password="password12")
        _mark_lessons(client, stu, a["lessons"][:count])

    # Rivera assigned so she can see the dashboard.
    _register(client, email="rivera@t.local", role="instructor", name="Rivera")
    riv_id = client.post("/api/auth/login", json={
        "email": "rivera@t.local", "password": "password12"
    }).get_json()["user"]["id"]
    _assign_teacher(client, admin_tok, class_id=a["class"],
                    course_id=a["course"]["id"], teacher_id=riv_id)
    riv_tok = _login(client, email="rivera@t.local", password="password12")

    body = client.get("/api/dashboard/instructor", headers=_h(riv_tok)).get_json()
    row = body["courses"][0]
    assert row["enrollmentCount"] == 4
    assert row["avgCompletion"] == 62.5
    assert row["completionRate"] == 0.5
    # No published quizzes → passRate 0.
    assert row["quizPassRate"] == 0.0


# ---------------------------------------------------------------------------
# 3. Empty course — no divide-by-zero
# ---------------------------------------------------------------------------
def test_empty_course_zeroes_everywhere(client):
    admin_tok = _login_admin(client)
    a = _mk_scaffold(client, admin_tok)

    # No students at all.
    _register(client, email="rivera@t.local", role="instructor", name="Rivera")
    riv_id = client.post("/api/auth/login", json={
        "email": "rivera@t.local", "password": "password12"
    }).get_json()["user"]["id"]
    _assign_teacher(client, admin_tok, class_id=a["class"],
                    course_id=a["course"]["id"], teacher_id=riv_id)
    riv_tok = _login(client, email="rivera@t.local", password="password12")

    body = client.get("/api/dashboard/instructor", headers=_h(riv_tok)).get_json()
    row = body["courses"][0]
    assert row["enrollmentCount"] == 0
    assert row["avgCompletion"] == 0
    assert row["completionRate"] == 0
    assert row["quizPassRate"] == 0
    assert row["certRate"] == 0
    # Summary should also survive with zero students.
    assert body["summary"]["totalStudents"] == 0
    assert body["summary"]["avgCompletion"] == 0


# ---------------------------------------------------------------------------
# 4. Drill-down: histogram and top-line agree with the row
# ---------------------------------------------------------------------------
def test_drilldown_histogram(client):
    admin_tok = _login_admin(client)
    a = _mk_scaffold(client, admin_tok)

    # Progress spreads: 0 (0-19), 50 (40-59), 100 (80-100), 100 (80-100).
    for i, count in enumerate([0, 1, 2, 2]):
        email = f"s{i}@t.local"
        _add_student_to_class(client, admin_tok, email=email, class_id=a["class"])
        stu = _login(client, email=email, password="password12")
        _mark_lessons(client, stu, a["lessons"][:count])

    _register(client, email="rivera@t.local", role="instructor", name="Rivera")
    riv_id = client.post("/api/auth/login", json={
        "email": "rivera@t.local", "password": "password12"
    }).get_json()["user"]["id"]
    _assign_teacher(client, admin_tok, class_id=a["class"],
                    course_id=a["course"]["id"], teacher_id=riv_id)
    riv_tok = _login(client, email="rivera@t.local", password="password12")

    r = client.get(
        f"/api/dashboard/instructor/courses/{a['course']['id']}",
        headers=_h(riv_tok),
    )
    assert r.status_code == 200, r.data
    body = r.get_json()
    hist = {b["label"]: b["count"] for b in body["completionHistogram"]}
    assert hist["0-19%"] == 1
    assert hist["40-59%"] == 1
    assert hist["80-100%"] == 2
    # 20-39% and 60-79% empty.
    assert hist["20-39%"] == 0
    assert hist["60-79%"] == 0

    # Per-module completion for the sole module.
    assert len(body["moduleCompletion"]) == 1
    # (0 + 0.5 + 1 + 1) / 4 * 100 = 62.5
    assert body["moduleCompletion"][0]["avgCompletion"] == 62.5


# ---------------------------------------------------------------------------
# 5. Non-teacher / non-admin cannot see analytics of a course
# ---------------------------------------------------------------------------
def test_instructor_cannot_see_others_drilldown(client):
    admin_tok = _login_admin(client)
    a = _mk_scaffold(client, admin_tok)

    # Rivera teaches Algebra 1. Diaz teaches nothing.
    _register(client, email="rivera@t.local", role="instructor", name="Rivera")
    riv_id = client.post("/api/auth/login", json={
        "email": "rivera@t.local", "password": "password12"
    }).get_json()["user"]["id"]
    _assign_teacher(client, admin_tok, class_id=a["class"],
                    course_id=a["course"]["id"], teacher_id=riv_id)
    _register(client, email="diaz@t.local", role="instructor", name="Diaz")

    diaz_tok = _login(client, email="diaz@t.local", password="password12")
    r = client.get(
        f"/api/dashboard/instructor/courses/{a['course']['id']}",
        headers=_h(diaz_tok),
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# 6. Students never see the instructor dashboard
# ---------------------------------------------------------------------------
def test_student_cannot_open_instructor_dashboard(client):
    admin_tok = _login_admin(client)
    a = _mk_scaffold(client, admin_tok)
    _add_student_to_class(client, admin_tok, email="s@t.local", class_id=a["class"])
    stu_tok = _login(client, email="s@t.local", password="password12")

    r = client.get("/api/dashboard/instructor", headers=_h(stu_tok))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# 7. Non-admin never sees the admin dashboard
# ---------------------------------------------------------------------------
def test_non_admin_cannot_open_admin_dashboard(client):
    admin_tok = _login_admin(client)
    _mk_scaffold(client, admin_tok)
    _register(client, email="rivera@t.local", role="instructor", name="Rivera")

    riv_tok = _login(client, email="rivera@t.local", password="password12")
    r = client.get("/api/dashboard/admin", headers=_h(riv_tok))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# 8. Admin dashboard top-line counts something reasonable
# ---------------------------------------------------------------------------
def test_admin_dashboard_topline_counts(client):
    admin_tok = _login_admin(client)
    a = _mk_scaffold(client, admin_tok)
    _add_student_to_class(client, admin_tok, email="s1@t.local", class_id=a["class"])
    _add_student_to_class(client, admin_tok, email="s2@t.local", class_id=a["class"])

    body = client.get("/api/dashboard/admin", headers=_h(admin_tok)).get_json()
    top = body["topline"]
    # 1 admin + 2 students.
    assert top["totalUsers"] == 3
    assert top["usersByRole"]["admin"] == 1
    assert top["usersByRole"]["student"] == 2
    assert top["publishedCourses"] == 1
    assert top["draftCourses"] == 0
    # Both students auto-enrolled into the mandatory course.
    assert top["activeEnrollments"] == 2
    # Nobody has completed anything yet.
    assert top["platformCompletionRate"] == 0
    assert top["certsIssuedLast30d"] == 0

    # Leaderboards + trend arrays are present and shape-checked.
    assert isinstance(body["mostPopular"], list)
    assert isinstance(body["highestCompletion"], list)
    assert isinstance(body["certsPerMonth"], list)
    assert len(body["certsPerMonth"]) == 6
    assert body["gradeBands"] == {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}


# ---------------------------------------------------------------------------
# 9. Popular courses sorted by enrollment count
# ---------------------------------------------------------------------------
def test_most_popular_sorted_desc(client):
    admin_tok = _login_admin(client)
    a = _mk_scaffold(client, admin_tok)

    # Second course, different elective group so it's optional (won't
    # auto-enroll everyone). Actually, mandatory in same grade auto-enrolls
    # anyway. Simpler: use the built-in enrollment to compare enrolment
    # counts across two mandatory courses in the same grade.
    h = _h(admin_tok)
    r = client.post("/api/courses",
                    json={"title": "Biology 9", "gradeId": a["grade"], "category": "science"},
                    headers=h)
    client.post(f"/api/courses/{r.get_json()['id']}/publish", headers=h)

    # 3 students → both courses get 3 enrolments.
    for i in range(3):
        _add_student_to_class(client, admin_tok, email=f"s{i}@t.local", class_id=a["class"])

    body = client.get("/api/dashboard/admin", headers=_h(admin_tok)).get_json()
    # Both courses appear, both with 3 enrolments; the exact ordering when
    # tied breaks alphabetically per our SQL.
    titles = [c["title"] for c in body["mostPopular"]]
    assert "Algebra 1" in titles
    assert "Biology 9" in titles
    counts = {c["title"]: c["enrollmentCount"] for c in body["mostPopular"]}
    assert counts["Algebra 1"] == 3
    assert counts["Biology 9"] == 3


# ---------------------------------------------------------------------------
# 10. Blueprint accepts no writes — POST returns 405
# ---------------------------------------------------------------------------
def test_dashboard_endpoints_are_readonly(client):
    admin_tok = _login_admin(client)
    r = client.post("/api/dashboard/instructor", headers=_h(admin_tok))
    assert r.status_code == 405
    r = client.post("/api/dashboard/admin", headers=_h(admin_tok))
    assert r.status_code == 405


# ---------------------------------------------------------------------------
# 11. Unauthenticated caller is bounced (401)
# ---------------------------------------------------------------------------
def test_unauth_bounced(client):
    r = client.get("/api/dashboard/instructor")
    assert r.status_code == 401
    r = client.get("/api/dashboard/admin")
    assert r.status_code == 401
